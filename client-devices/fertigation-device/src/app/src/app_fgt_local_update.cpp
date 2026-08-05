#include "app_fgt_local_update.h"

#include <Arduino.h>
#include <ArduinoJson.h>
#include <ESPAsyncWebServer.h>
#include <Update.h>
#include <string.h>

#include "app_def.h"
#include "app_initial_setting.h"
#include "esp_ota_ops.h"
#include "fgt_firmware_manifest_validator.h"

namespace
{

constexpr uint32_t kUploadingLedIntervalMs = 100;
constexpr uint32_t kCompleteLedIntervalMs = 50;
constexpr uint32_t kFailedLedIntervalMs = 1000;
constexpr uint32_t kRestartDelayMs = 2000;
constexpr uint32_t kUploadTimeoutMs = 60000;

enum class LocalUpdatePhase : uint8_t
{
    idle,
    preparing,
    uploading,
    complete,
    failed,
};

struct LocalUpdateState
{
    volatile LocalUpdatePhase phase =
        LocalUpdatePhase::idle;
    volatile uint32_t bytes_written = 0;
    volatile uint32_t partition_size = 0;
    volatile uint32_t restart_at_ms = 0;
    volatile uint32_t last_activity_ms = 0;
    bool update_started = false;
    bool header_checked = false;
    AsyncWebServerRequest *active_request = nullptr;
    char filename[96] = {};
    char error[64] = {};
    fgt::FirmwareManifestScanner manifest;
};

LocalUpdateState s_state;
app_fgt_local_update_prepare_callback_t
    s_prepare_callback = nullptr;

const char kUpdatePage[] PROGMEM = R"HTML(
<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>FGT ファームウェア更新</title>
  <style>
    :root{color-scheme:light;--ink:#17202a;--muted:#5c6b73;--line:#d9e2e8;--bg:#f3f7f5;--card:#fff;--green:#176b52;--red:#b42318;--amber:#9a6700}
    *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:system-ui,-apple-system,"Segoe UI",sans-serif}
    main{max-width:720px;margin:0 auto;padding:22px 16px 64px}h1{font-size:26px;margin:12px 0 6px}p{line-height:1.6;color:var(--muted)}
    a{color:var(--green)}.card{margin-top:18px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;box-shadow:0 2px 8px rgba(15,23,42,.04)}
    .notice{border:1px solid #f2cc8f;background:#fff8e8;border-radius:12px;padding:14px 16px;margin:16px 0}.notice strong{color:#7a4b00}
    label{display:block;font-weight:700;margin:12px 0 6px}input{width:100%;padding:10px;border:1px solid #b8c4cb;border-radius:7px;background:#fff}
    button{border:0;border-radius:7px;padding:11px 15px;background:var(--green);color:#fff;font:inherit;font-weight:700;cursor:pointer;margin-top:14px}
    button:disabled{opacity:.45;cursor:not-allowed}.status{margin-top:14px;padding:12px;border-radius:8px;background:#eef2f4}.ok{background:#e7f6ef;color:#125b46}.warn{background:#fff2cc;color:#7a4b00}.error{background:#feeceb;color:#8f1d18}
    progress{width:100%;height:22px;margin-top:14px}code{overflow-wrap:anywhere}.hint{font-size:13px;color:var(--muted);margin:7px 0 0}
    details{margin-top:14px;border:1px solid var(--line);border-radius:9px;padding:10px 12px}summary{cursor:pointer;font-weight:700}
    .browser-link{display:inline-block;margin-top:10px;padding:10px 12px;border-radius:7px;background:#52616b;color:#fff;text-decoration:none;font-weight:700}
  </style>
</head>
<body><main>
  <a href="/fgt/commissioning">← 出荷動作確認へ戻る</a>
  <h1>ファームウェア更新</h1>
  <p>Wi-FiやMQTTを使わず、このAPへ接続したブラウザからFGTのアプリファームウェアを更新します。</p>
  <section class="notice">
    <strong>更新中は12V電源とUSB電源を切らないでください。</strong>
    MOSFET出力とセンサー電源は更新開始時にOFFになります。対象は展開済みの
    <code>firmware.bin</code>です。<code>.inasfw</code>やZIPはそのままアップロードできません。
  </section>
  <section class="card">
    <label for="firmware">FGT firmware.bin</label>
    <input id="firmware" name="firmware" type="file" aria-describedby="fileHelp">
    <p id="fileHelp" class="hint">安全確認はアップロード時に行います。ファイル一覧にはすべての種類が表示されるため、必ず展開済みのfirmware.binを選択してください。</p>
    <details id="pickerHelp">
      <summary>「ファイルを選択」が反応しない場合</summary>
      <ol>
        <li>AP接続時に自動表示されたログイン画面を閉じます。</li>
        <li><code>INAS-FGT-setup</code>へのWi-Fi接続は維持します。</li>
        <li>SafariまたはChromeを通常起動し、<code>http://192.168.4.1/fgt/firmware-update</code>を直接開きます。</li>
        <li>事前にスマホ本体の「ファイル」または「ダウンロード」へ保存した<code>firmware.bin</code>を選びます。</li>
      </ol>
      <a class="browser-link" href="http://192.168.4.1/fgt/firmware-update" target="_blank" rel="noopener">標準ブラウザでこの画面を開く</a>
    </details>
    <button id="updateButton" onclick="startUpdate()">更新を開始</button>
    <progress id="progress" max="100" value="0"></progress>
    <div id="status" class="status">ファイルを選択してください。</div>
  </section>
  <section class="card">
    <p>LED表示</p>
    <ul>
      <li>通常のAPモード: 500ms間隔</li>
      <li>更新中: 100ms間隔</li>
      <li>更新完了・再起動待ち: 50ms間隔</li>
      <li>更新失敗: 1000ms間隔</li>
    </ul>
  </section>
<script>
const fileInput=document.getElementById('firmware');
const button=document.getElementById('updateButton');
const progress=document.getElementById('progress');
const statusBox=document.getElementById('status');
const pickerHelp=document.getElementById('pickerHelp');
let pickerAttempt=0;
function show(message,type=''){statusBox.className=`status ${type}`;statusBox.textContent=message}
function errorText(code){
  const messages={
    firmware_bin_required:'展開済みのfirmware.binを選択してください。',
    filename_too_long:'ファイル名が長すぎます。',
    commissioning_busy:'別の安全処理が実行中です。少し待ってから再試行してください。',
    ota_partition_not_found:'更新先の領域が見つかりません。このF/Wの構成を確認してください。',
    update_begin_failed:'更新領域を準備できませんでした。',
    invalid_esp_image:'ESP32-C6用のアプリF/Wではありません。',
    firmware_too_large:'F/Wが更新領域より大きいため書き込めません。',
    flash_write_failed:'F/Wの書き込みに失敗しました。',
    empty_firmware:'F/Wファイルが空です。',
    firmware_manifest_missing:'INASの機器情報がないF/Wです。',
    firmware_target_mismatch:'FGT/XIAO ESP32-C6用ではないF/Wです。',
    firmware_finalize_failed:'F/Wの検証または更新確定に失敗しました。',
    upload_timeout:'アップロードが60秒以上中断されたため更新を取り消しました。',
    upload_in_progress:'別のF/Wアップロードが実行中です。'
  };
  return messages[code]||code||'原因不明のエラー';
}
function startUpdate(){
  const file=fileInput.files[0];
  if(!file){show('firmware.binを選択してください。','error');return}
  if(!file.name.toLowerCase().endsWith('.bin')){show('.inasfwやZIPではなく、展開済みのfirmware.binを選択してください。','error');return}
  if(!confirm('更新中は電源を切れません。ファームウェア更新を開始しますか？'))return;
  button.disabled=true;fileInput.disabled=true;progress.value=0;show('アップロードを開始しています…');
  const data=new FormData();data.append('firmware',file,file.name);
  const xhr=new XMLHttpRequest();
  xhr.open('POST','/api/fgt/firmware-update/upload');
  xhr.upload.onprogress=event=>{
    if(!event.lengthComputable)return;
    const value=Math.round(event.loaded*100/event.total);
    progress.value=value;show(`アップロード・書き込み中 ${value}% — 電源を切らないでください。`);
  };
  xhr.onload=()=>{
    let body={};try{body=JSON.parse(xhr.responseText)}catch(error){}
    if(xhr.status>=200&&xhr.status<300&&body.ok){
      progress.value=100;show('更新が完了しました。約2秒後に自動再起動します。','ok');
      return;
    }
    show(`更新に失敗しました: ${body.message||errorText(body.error)||xhr.statusText}`,'error');
    button.disabled=false;fileInput.disabled=false;
  };
  xhr.onerror=()=>{show('APとの通信が切断されました。LEDが高速点滅している場合は再起動を待ってください。','error')};
  xhr.send(data);
}
fileInput.addEventListener('click',()=>{
  if(fileInput.disabled)return;
  const attempt=++pickerAttempt;
  window.setTimeout(()=>{
    if(attempt!==pickerAttempt||fileInput.files.length>0||document.hidden)return;
    pickerHelp.open=true;
    show('端末のファイル画面が開かない場合は、APの簡易ログイン画面を閉じ、SafariまたはChromeからこのURLを直接開いてください。','warn');
  },1500);
});
fileInput.addEventListener('change',()=>{
  ++pickerAttempt;
  const file=fileInput.files[0];
  if(!file){
    show('ファイルは選択されていません。','warn');
    return;
  }
  show(`選択済み: ${file.name}（${file.size} bytes）`);
});
async function refresh(){
  try{
    const response=await fetch('/api/fgt/firmware-update/status',{cache:'no-store'});
    const body=await response.json();
    if(body.state==='preparing'||body.state==='uploading'){button.disabled=true;fileInput.disabled=true}
    if(body.state==='idle'){button.disabled=false;fileInput.disabled=false}
    if(body.state==='failed'&&body.error){
      show(`更新に失敗しました: ${errorText(body.error)}`,'error');
      button.disabled=false;fileInput.disabled=false;
    }
  }catch(error){}
}
refresh();setInterval(refresh,1000);
</script>
</main></body></html>
)HTML";

const char *phase_name(LocalUpdatePhase phase)
{
    switch (phase)
    {
    case LocalUpdatePhase::idle:
        return "idle";
    case LocalUpdatePhase::preparing:
        return "preparing";
    case LocalUpdatePhase::uploading:
        return "uploading";
    case LocalUpdatePhase::complete:
        return "complete";
    case LocalUpdatePhase::failed:
        return "failed";
    }
    return "failed";
}

bool filename_is_bin(const String &filename)
{
    String lower = filename;
    lower.toLowerCase();
    return lower.endsWith(".bin");
}

void reset_state()
{
    s_state.phase = LocalUpdatePhase::idle;
    s_state.bytes_written = 0;
    s_state.partition_size = 0;
    s_state.restart_at_ms = 0;
    s_state.last_activity_ms = 0;
    s_state.update_started = false;
    s_state.header_checked = false;
    s_state.active_request = nullptr;
    memset(s_state.filename, 0, sizeof(s_state.filename));
    memset(s_state.error, 0, sizeof(s_state.error));
    s_state.manifest.reset();
}

void fail_update(const char *error)
{
    if (s_state.update_started)
    {
        Update.abort();
    }
    s_state.update_started = false;
    s_state.phase = LocalUpdatePhase::failed;
    strncpy(
        s_state.error,
        error != nullptr ? error : "update_failed",
        sizeof(s_state.error) - 1);
    s_state.error[sizeof(s_state.error) - 1] = '\0';
    app_initial_setting_set_status_led_blink_interval(
        kFailedLedIntervalMs);
    Serial.printf(
        "FGT local firmware update failed: error=%s bytes=%lu\n",
        s_state.error,
        static_cast<unsigned long>(s_state.bytes_written));
}

bool begin_update(
    AsyncWebServerRequest *request,
    const String &filename)
{
    if (app_fgt_local_update_busy())
    {
        return false;
    }
    reset_state();
    if (!filename_is_bin(filename))
    {
        fail_update("firmware_bin_required");
        return false;
    }
    if (filename.length() >= sizeof(s_state.filename))
    {
        fail_update("filename_too_long");
        return false;
    }
    s_state.active_request = request;
    s_state.phase = LocalUpdatePhase::preparing;
    s_state.last_activity_ms = millis();
    app_initial_setting_set_status_led_blink_interval(
        kUploadingLedIntervalMs);
    if (s_prepare_callback != nullptr &&
        !s_prepare_callback())
    {
        fail_update("commissioning_busy");
        return false;
    }

    const esp_partition_t *partition =
        esp_ota_get_next_update_partition(nullptr);
    if (partition == nullptr || partition->size == 0)
    {
        fail_update("ota_partition_not_found");
        return false;
    }
    s_state.partition_size = partition->size;
    if (!Update.begin(partition->size, U_FLASH))
    {
        Serial.printf(
            "FGT local Update.begin failed: %s\n",
            Update.errorString());
        fail_update("update_begin_failed");
        return false;
    }

    memcpy(
        s_state.filename,
        filename.c_str(),
        filename.length() + 1);
    s_state.update_started = true;
    s_state.phase = LocalUpdatePhase::uploading;
    s_state.last_activity_ms = millis();
    Serial.printf(
        "FGT local firmware update started: file=%s partition=%s max=%lu\n",
        s_state.filename,
        partition->label,
        static_cast<unsigned long>(partition->size));
    return true;
}

void handle_upload_chunk(
    AsyncWebServerRequest *request,
    const String &filename,
    size_t index,
    uint8_t *data,
    size_t length,
    bool final)
{
    if (index == 0 &&
        !begin_update(request, filename))
    {
        return;
    }
    if (s_state.active_request != request)
    {
        return;
    }
    if (s_state.phase != LocalUpdatePhase::uploading ||
        !s_state.update_started)
    {
        return;
    }
    if (length > 0 && !s_state.header_checked)
    {
        s_state.header_checked = true;
        if (index != 0 || data == nullptr || data[0] != 0xE9)
        {
            fail_update("invalid_esp_image");
            return;
        }
    }
    if (length > 0)
    {
        s_state.last_activity_ms = millis();
        if (s_state.bytes_written + length >
            s_state.partition_size)
        {
            fail_update("firmware_too_large");
            return;
        }
        s_state.manifest.feed(data, length);
        const size_t written = Update.write(data, length);
        if (written != length)
        {
            Serial.printf(
                "FGT local Update.write failed: %u/%u %s\n",
                static_cast<unsigned int>(written),
                static_cast<unsigned int>(length),
                Update.errorString());
            fail_update("flash_write_failed");
            return;
        }
        s_state.bytes_written += length;
    }
    if (!final)
    {
        return;
    }

    if (s_state.bytes_written == 0 ||
        !s_state.header_checked)
    {
        fail_update("empty_firmware");
        return;
    }
    if (s_state.manifest.overflowed() ||
        !s_state.manifest.complete())
    {
        fail_update("firmware_manifest_missing");
        return;
    }
    if (!s_state.manifest.matches(
            APP_FIRMWARE_PROJECT,
            APP_DEVICE_KIND,
            APP_FIRMWARE_TARGET,
            APP_FIRMWARE_FRAMEWORK))
    {
        fail_update("firmware_target_mismatch");
        return;
    }
    if (!Update.end(true) || !Update.isFinished())
    {
        Serial.printf(
            "FGT local Update.end failed: %s\n",
            Update.errorString());
        fail_update("firmware_finalize_failed");
        return;
    }

    s_state.update_started = false;
    s_state.phase = LocalUpdatePhase::complete;
    s_state.restart_at_ms = millis() + kRestartDelayMs;
    app_initial_setting_set_status_led_blink_interval(
        kCompleteLedIntervalMs);
    Serial.printf(
        "FGT local firmware update complete: bytes=%lu restart_in=%lu ms\n",
        static_cast<unsigned long>(s_state.bytes_written),
        static_cast<unsigned long>(kRestartDelayMs));
}

void send_status(
    AsyncWebServerRequest *request,
    int status)
{
    JsonDocument doc;
    const LocalUpdatePhase phase = s_state.phase;
    doc["ok"] =
        phase != LocalUpdatePhase::failed;
    doc["state"] = phase_name(phase);
    doc["filename"] = s_state.filename;
    doc["bytes_written"] = s_state.bytes_written;
    doc["partition_size"] = s_state.partition_size;
    doc["error"] = s_state.error;
    if (phase == LocalUpdatePhase::complete)
    {
        const int32_t remaining = static_cast<int32_t>(
            s_state.restart_at_ms - millis());
        doc["restart_in_ms"] = remaining > 0 ? remaining : 0;
    }
    String body;
    serializeJson(doc, body);
    request->send(
        status,
        "application/json; charset=utf-8",
        body);
}

} // namespace

void app_fgt_local_update_init(
    app_fgt_local_update_prepare_callback_t prepare_callback)
{
    s_prepare_callback = prepare_callback;
    if (s_state.update_started)
    {
        Update.abort();
    }
    reset_state();
    app_initial_setting_reset_status_led_blink_interval();
}

void app_fgt_local_update_register_routes(
    AsyncWebServer *server)
{
    if (server == nullptr)
    {
        return;
    }
    server->on(
        "/fgt/firmware-update",
        HTTP_GET,
        [](AsyncWebServerRequest *request)
        {
            request->send(
                200,
                "text/html; charset=utf-8",
                kUpdatePage);
        });
    server->on(
        "/api/fgt/firmware-update/status",
        HTTP_GET,
        [](AsyncWebServerRequest *request)
        {
            send_status(request, 200);
        });
    server->on(
        "/api/fgt/firmware-update/upload",
        HTTP_POST,
        [](AsyncWebServerRequest *request)
        {
            if (s_state.active_request != nullptr &&
                s_state.active_request != request)
            {
                JsonDocument doc;
                doc["ok"] = false;
                doc["error"] = "upload_in_progress";
                String body;
                serializeJson(doc, body);
                request->send(
                    409,
                    "application/json; charset=utf-8",
                    body);
                return;
            }
            send_status(
                request,
                s_state.phase ==
                        LocalUpdatePhase::complete
                    ? 200
                    : 400);
        },
        handle_upload_chunk);
}

void app_fgt_local_update_loop()
{
    if ((s_state.phase == LocalUpdatePhase::preparing ||
         s_state.phase == LocalUpdatePhase::uploading) &&
        static_cast<uint32_t>(
            millis() - s_state.last_activity_ms) >=
            kUploadTimeoutMs)
    {
        fail_update("upload_timeout");
        return;
    }
    if (s_state.phase != LocalUpdatePhase::complete)
    {
        return;
    }
    if (static_cast<int32_t>(
            millis() - s_state.restart_at_ms) < 0)
    {
        return;
    }
    if (s_prepare_callback != nullptr)
    {
        s_prepare_callback();
    }
    Serial.println(
        "FGT local firmware update restarting now");
    ESP.restart();
}

void app_fgt_local_update_end()
{
    if (s_state.update_started)
    {
        Update.abort();
    }
    reset_state();
    app_initial_setting_reset_status_led_blink_interval();
}

bool app_fgt_local_update_busy()
{
    const LocalUpdatePhase phase = s_state.phase;
    return phase == LocalUpdatePhase::preparing ||
           phase == LocalUpdatePhase::uploading ||
           phase == LocalUpdatePhase::complete;
}
