#include "app_fgt_commissioning.h"

#include <Arduino.h>
#include <ArduinoJson.h>
#include <ESPAsyncWebServer.h>
#include <errno.h>
#include <esp_attr.h>
#include <esp_system.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <freertos/task.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "app_initial_setting.h"
#include "app_fgt_local_update.h"
#include "app_fgt_rs485_devices.h"
#include "fgt_commissioning_interlock.h"
#include "fgt_sensor_diagnostics.h"
#include "hal_direct_gpio.h"
#include "hal_power_switch.h"
#include "hal_rs485_modbus.h"

#ifndef APP_FGT_COMMISSIONING_SWITCH_GUARD_MS
#define APP_FGT_COMMISSIONING_SWITCH_GUARD_MS 3000UL
#endif

#ifndef APP_FGT_COMMISSIONING_MAX_ON_MS
#define APP_FGT_COMMISSIONING_MAX_ON_MS 30000UL
#endif

#ifndef APP_FGT_COMMISSIONING_RS485_TIMEOUT_MS
#define APP_FGT_COMMISSIONING_RS485_TIMEOUT_MS 250UL
#endif

namespace
{

constexpr uint16_t kAllOutputsMask = 0x001F;
constexpr uint8_t kAutoScanMaxId = 10;
constexpr uint16_t kSensorAddressRegister = 0x07D0;
constexpr uint32_t kSensorPowerSettleMs = 800;
constexpr uint32_t kAddressChangeVerifyDelayMs = 500;
constexpr size_t kSensorCommunicationLogSize = 4096;
constexpr uint32_t kAutoScanBauds[] = {4800, 2400, 9600};

const char *const kOutputLabels[] = {
    "給水",
    "A液",
    "B液",
    "攪拌",
    "潅水",
};

struct CommissioningSensorReading
{
    bool communication_ok = false;
    bool values_plausible = false;
    uint16_t values[7] = {};
};

struct DetectedSensor
{
    fgt::SensorIdentification identification = {};
    CommissioningSensorReading reading = {};
    uint8_t slave_id = 0;
    uint32_t baud = 0;
    const char *identification_basis = "unknown";
};

enum class AutoDetectionPhase : uint8_t
{
    idle,
    power_settle,
    scanning,
    complete,
    failed,
    cancelled,
};

struct AutoDetectionOperation
{
    AutoDetectionPhase phase = AutoDetectionPhase::idle;
    uint32_t started_ms = 0;
    uint32_t power_ready_ms = 0;
    uint8_t baud_index = 0;
    uint8_t next_id = 1;
    size_t sensor_count = 0;
    size_t passed_count = 0;
    DetectedSensor sensors[30] = {};
    char communication_log[kSensorCommunicationLogSize] = {};
    size_t communication_log_length = 0;
    size_t communication_transaction_count = 0;
    bool communication_log_truncated = false;
};

hal_direct_gpio_t s_commissioning_io = {};
hal_power_switch_t s_commissioning_sensor_power = {};
bool s_io_ready = false;
bool s_sensor_power_ready = false;
bool s_rs485_ready = false;
bool s_rs485_internal_loopback_ok = false;
uint32_t s_rs485_baud = 0;
SemaphoreHandle_t s_operation_mutex = nullptr;
fgt::CommissioningInterlock s_interlock(APP_FGT_COMMISSIONING_SWITCH_GUARD_MS,
                                        APP_FGT_COMMISSIONING_MAX_ON_MS);
AutoDetectionOperation s_auto_detection = {};

constexpr uint32_t kRegistrationDiagnosticMagic = 0x46475444UL;

struct RegistrationResetMarker
{
    uint32_t magic;
    uint32_t active;
    uint32_t slave_id;
    uint32_t baud;
    uint32_t stack_low_water_mark_bytes;
    uint32_t free_heap_bytes;
};

RTC_NOINIT_ATTR RegistrationResetMarker s_registration_reset_marker;
esp_reset_reason_t s_portal_reset_reason = ESP_RST_UNKNOWN;
bool s_registration_interrupted = false;
uint32_t s_registration_stack_before_bytes = 0;
uint32_t s_registration_stack_after_bytes = 0;
uint32_t s_registration_heap_before_bytes = 0;
uint32_t s_registration_heap_after_bytes = 0;
uint32_t s_registration_sensor_id = 0;
uint32_t s_registration_sensor_baud = 0;
const char *s_registration_last_result = "not_attempted";

const char kCommissioningPage[] PROGMEM = R"HTML(
<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>FGT 出荷動作確認</title>
  <style>
    :root{color-scheme:light;--ink:#17202a;--muted:#5c6b73;--line:#d9e2e8;--bg:#f3f7f5;--card:#fff;--green:#176b52;--red:#b42318;--amber:#9a6700}
    *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:system-ui,-apple-system,"Segoe UI",sans-serif}
    main{max-width:900px;margin:0 auto;padding:22px 16px 64px}a{color:var(--green)}
    h1{font-size:26px;margin:10px 0 6px}h2{font-size:19px;margin:0 0 14px}p{line-height:1.6;color:var(--muted)}
    .back{display:inline-block;margin-bottom:6px}.notice{border:1px solid #f2cc8f;background:#fff8e8;border-radius:12px;padding:14px 16px;margin:16px 0}
    .notice strong{color:#7a4b00}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin:14px 0}
    .card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;box-shadow:0 2px 8px rgba(15,23,42,.04)}
    .wide{grid-column:1/-1}.status{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}.pill{padding:6px 10px;border-radius:99px;background:#eef2f4;font-size:13px}
    .ok{background:#e7f6ef;color:#125b46}.warn{background:#fff2cc;color:#7a4b00}.danger{background:#feeceb;color:#8f1d18}
    .outputs{display:grid;grid-template-columns:repeat(5,minmax(105px,1fr));gap:10px}.output{border:1px solid var(--line);border-radius:10px;padding:12px;text-align:center}
    .output strong{display:block;margin-bottom:8px}.output button{width:100%}
    label{display:block;font-weight:700;margin:11px 0 5px}.row{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
    input,select,button{font:inherit}input,select{width:100%;padding:9px 10px;border:1px solid #b8c4cb;border-radius:7px;background:#fff}
    button{border:0;border-radius:7px;padding:10px 13px;background:var(--green);color:#fff;font-weight:700;cursor:pointer}
    button.secondary{background:#52616b}button.stop{background:var(--red)}button:disabled{opacity:.45;cursor:not-allowed}
    .actions{display:flex;flex-wrap:wrap;gap:9px;margin-top:14px}.hint{font-size:13px;color:var(--muted);margin-top:7px}
    .confirm{display:flex;gap:9px;align-items:flex-start;margin:12px 0;color:#7a2e0e;font-weight:700}.confirm input{width:auto;margin-top:4px}
    .sensor-list{display:grid;gap:12px;margin-top:14px}.sensor{border:1px solid var(--line);border-radius:11px;padding:14px;background:#fbfdfc}
    .sensor-head{display:flex;gap:10px;align-items:flex-start;justify-content:space-between}.sensor h3{margin:0;font-size:17px}.sensor-meta{font-size:13px;color:var(--muted);margin-top:4px}
    .measurements{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-top:12px}.measurement{background:#eef5f1;border-radius:8px;padding:10px}
    .measurement span{display:block;color:var(--muted);font-size:12px}.measurement strong{display:block;margin-top:2px;font-size:16px}.empty{padding:18px;text-align:center;color:var(--muted);border:1px dashed #b8c4cb;border-radius:9px}
    .configured-list{display:grid;gap:12px;margin-top:14px}.configured{border:1px solid #b7d8ca;border-radius:11px;padding:14px;background:#f5fbf8}
    .configured-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:10px}.configured .confirm{color:var(--ink)}
    .error-box{display:none;border:1px solid #f4a7a1;background:#fff0ef;color:#8f1d18;border-radius:10px;padding:12px 14px;margin-top:12px;white-space:pre-wrap;overflow-wrap:anywhere}
    .error-box.visible{display:block}
    pre{white-space:pre-wrap;overflow-wrap:anywhere;min-height:90px;background:#0f1720;color:#d7f7e9;border-radius:8px;padding:12px;font-size:13px}
    details{margin-top:8px}summary{cursor:pointer;color:var(--muted)}
    @media(max-width:760px){.grid{grid-template-columns:1fr}.outputs{grid-template-columns:repeat(2,1fr)}.row{grid-template-columns:repeat(2,1fr)}.measurements{grid-template-columns:repeat(2,1fr)}.configured-grid{grid-template-columns:1fr}}
  </style>
</head>
<body><main>
  <a class="back" href="/">← 接続設定へ戻る</a>
  <h1>FGT 出荷動作確認</h1>
  <p>初期配線、ポンプ出力、土壌・PARセンサーをAPモードで確認します。</p>
  <section class="notice">
    <strong>監視下の水だけの試験専用です。</strong>
    ポンプの周囲を安全にし、12Vを物理的に遮断できる状態で操作してください。
    MOSFET出力は1系統だけONになり、最大30秒で自動停止します。OFF後3秒間は次のONを受け付けません。
  </section>

  <div class="grid">
    <section class="card wide">
      <h2>現在の状態</h2>
      <div id="status" class="status"><span class="pill">読込中</span></div>
      <div class="actions">
        <button class="stop" onclick="allOff()">全MOSFETをOFF</button>
        <button class="secondary" onclick="refreshStatus()">状態を更新</button>
        <button class="secondary" onclick="location.href='/fgt/firmware-update'">F/Wアップデート</button>
      </div>
    </section>

    <section class="card wide">
      <h2>障害診断</h2>
      <p>登録時にAPが切れた場合は、再接続してこの欄を開き、表示内容をそのまま共有してください。パスワードは含みません。</p>
      <div id="diagnosticSummary" class="status"><span class="pill">読込中</span></div>
      <div id="operationError" class="error-box" role="alert"></div>
      <details>
        <summary>共有用診断データを表示</summary>
        <pre id="diagnosticDetails">診断情報を取得中です。</pre>
      </details>
    </section>

    <section class="card wide">
      <h2>MOSFET出力</h2>
      <div class="row">
        <div><label for="duration">ON時間（秒）</label><input id="duration" type="number" min="1" max="30" value="3"></div>
      </div>
      <p class="hint">別の出力へ切り替える場合は、全OFFにして保護期間が終わるまで待ってください。</p>
      <div class="outputs">
        <div class="output"><strong>1 給水</strong><button data-output="1" onclick="outputOn(1)">ON</button></div>
        <div class="output"><strong>2 A液</strong><button data-output="2" onclick="outputOn(2)">ON</button></div>
        <div class="output"><strong>3 B液</strong><button data-output="3" onclick="outputOn(3)">ON</button></div>
        <div class="output"><strong>4 攪拌</strong><button data-output="4" onclick="outputOn(4)">ON</button></div>
        <div class="output"><strong>5 潅水</strong><button data-output="5" onclick="outputOn(5)">ON</button></div>
      </div>
    </section>

    <section class="card wide">
      <h2>登録済みRS485センサー</h2>
      <p>ここに保存した構成は再起動後も残り、APモードと通常運転の両方で使用されます。接続場所は、実際に確認できる名前で記録してください。</p>
      <div id="configuredSummary" class="status"><span class="pill">読込中</span></div>
      <div id="configuredDevices" class="configured-list"></div>
    </section>

    <section class="card wide">
      <h2>センサー電源</h2>
      <p>自動検出を開始するとセンサー電源も自動でONになります。必要な場合だけ手動操作してください。</p>
      <div class="actions">
        <button data-sensor-action onclick="sensorPower(true)">12V ON</button>
        <button data-sensor-action class="secondary" onclick="sensorPower(false)">12V OFF</button>
      </div>
    </section>

    <section class="card wide">
      <h2>RS485 UART・配線診断</h2>
      <p>起動時にESP32-C6内部のUART送受信試験を自動実行します。内部試験がOKでセンサー応答がない場合は、D6/D7とMAX3485基板の間を確認します。</p>
      <section class="notice">
        <strong>D6-D7配線試験はMAX3485基板を外して実施します。</strong>
        センサー12VをOFFにし、D6・D7・D8からMAX3485基板を外した後、XIAOのD6とD7だけをジャンパ線で直結してください。
        MAX3485基板を接続したままD6-D7を短絡しないでください。
      </section>
      <label class="confirm"><input id="ttlLoopbackConfirmed" type="checkbox">MAX3485基板をD6・D7・D8から外し、XIAOのD6-D7だけを直結しました</label>
      <div class="actions">
        <button class="secondary" onclick="runTtlLoopback()">D6-D7配線試験を実行</button>
      </div>
      <p class="hint">試験後はジャンパ線を外し、D6/TX→module RXD、D7/RX←module TXD、D8→module ENへ戻してください。</p>
    </section>

    <section class="card wide">
      <h2>センサー自動検出・値取得試験</h2>
      <p>接続済みの土壌センサーとPARセンサーを自動で探し、機種名と測定値を表示します。通信速度、アドレス、レジスタの入力は不要です。</p>
      <div class="actions">
        <button id="detectButton" data-sensor-action onclick="detectSensors()">センサーを自動検出して試験</button>
      </div>
      <p class="hint">対応機種: ComWinTop CWT-SOIL NPKPHCTH-S、DFRobot SEN0641 PAR。ID 1〜10、2400/4800/9600 bpsを自動確認します。</p>
      <div id="sensorSummary" class="status"></div>
      <div id="sensorList" class="sensor-list"><div class="empty">まだセンサーを検出していません。</div></div>
      <details id="sensorCommunicationLogDetails">
        <summary>共有用センサー通信ログを表示</summary>
        <p class="hint">検出時のModbusアドレス、通信速度、Function、レジスタ、応答値、判定根拠です。Wi-Fi/MQTTのパスワードは含みません。</p>
        <div class="actions">
          <button class="secondary" onclick="copySensorCommunicationLog()">通信ログをコピー</button>
        </div>
        <pre id="sensorCommunicationLog">まだ通信ログはありません。</pre>
        <p id="sensorCommunicationLogCopyStatus" class="hint"></p>
      </details>
      <section class="notice">
        <strong>登録は1台ずつ行います。</strong>
        登録するセンサーだけをRS485バスへ接続して自動検出し、種別、名前、接続場所を確認してください。
        自動判定が実機ラベルと違う場合は、登録前に正しい種別へ変更できます。
        保存後に次のセンサーへつなぎ替えます。
      </section>
      <div class="row">
        <div><label for="deviceType">登録するセンサー種別</label><select id="deviceType" onchange="updateRegistrationTypeHint()" disabled><option value="soil">土壌センサー</option><option value="par">PAR（日射）センサー</option></select></div>
        <div><label for="deviceName">センサー名</label><input id="deviceName" maxlength="20" placeholder="例: 育苗ベンチ土壌"></div>
        <div><label for="deviceLocation">接続場所・用途</label><input id="deviceLocation" maxlength="30" placeholder="例: ハウス東側 RS485分岐1"></div>
      </div>
      <p id="deviceTypeHint" class="hint">1台だけ検出すると、自動判定された種別を確認・訂正できます。</p>
      <div class="actions">
        <button id="registerDeviceButton" data-sensor-action onclick="registerDetectedDevice()" disabled>検出した1台を登録</button>
      </div>
    </section>

    <section class="card wide">
      <h2>センサーアドレス変更</h2>
      <section class="notice">
        <strong>同じアドレスのセンサーを複数接続したまま、1台だけ変更することはできません。</strong>
        重複している場合は変更対象以外をコネクタから外し、「センサーを自動検出して試験」をもう一度実行してください。
        書き込みは自動再送しません。
      </section>
      <div class="row">
        <div><label>変更するセンサー</label><select id="addressSensor" onchange="updateAddressRegistryOptions()"><option value="">先に自動検出してください</option></select></div>
        <div><label>登録済み構成との関係</label><select id="addressRegistry"><option value="255">新しく追加する未登録センサー</option></select></div>
        <div><label>新しいアドレス</label><input id="newId" type="number" min="1" max="10" value="2"></div>
      </div>
      <p class="hint">新しいセンサーは「未登録センサー」のまま変更します。登録済みセンサー本体のアドレスを変更する場合だけ、対応する登録名を選択してください。推奨割り当て: 土壌センサー1 = 1、土壌センサー2 = 2、PARセンサー = 3</p>
      <label class="confirm"><input id="singleConfirmed" type="checkbox">変更対象のセンサー1台だけがRS485バスへ接続されていることを確認しました</label>
      <div class="actions"><button data-sensor-action class="stop" onclick="changeAddress()">アドレスを変更して再試験</button></div>
    </section>

    <section class="card wide">
      <details>
        <summary>保守用の詳細結果を表示</summary>
        <pre id="result">操作結果がここに表示されます。</pre>
      </details>
    </section>
  </div>
</main>
<script>
const result=document.getElementById('result');
const value=id=>document.getElementById(id).value;
let detectedSensors=[];
let configuredDevices=[];
let sensorCommunicationLog='';
const escapeHtml=text=>String(text??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
function form(data){const p=new URLSearchParams();Object.entries(data).forEach(([k,v])=>p.set(k,String(v)));return p}
function setSensorCommunicationLog(log,truncated=false){
  sensorCommunicationLog=String(log||'');
  document.getElementById('sensorCommunicationLog').textContent=sensorCommunicationLog||'まだ通信ログはありません。';
  document.getElementById('sensorCommunicationLogCopyStatus').textContent=truncated?'ログ上限に達したため末尾が省略されています。':'';
}
async function copySensorCommunicationLog(){
  if(!sensorCommunicationLog){
    document.getElementById('sensorCommunicationLogCopyStatus').textContent='コピーできる通信ログがまだありません。';
    return;
  }
  let copied=false;
  try{
    if(navigator.clipboard&&window.isSecureContext){
      await navigator.clipboard.writeText(sensorCommunicationLog);
      copied=true;
    }
  }catch(error){}
  if(!copied){
    const area=document.createElement('textarea');
    area.value=sensorCommunicationLog;
    area.setAttribute('readonly','');
    area.style.position='fixed';
    area.style.opacity='0';
    document.body.appendChild(area);
    area.select();
    try{copied=document.execCommand('copy')}catch(error){}
    area.remove();
  }
  document.getElementById('sensorCommunicationLogCopyStatus').textContent=copied?'通信ログをコピーしました。':'自動コピーできませんでした。ログ本文を長押しして選択・コピーしてください。';
}
function showOperationError(message){
  const box=document.getElementById('operationError');
  box.textContent=message||'';
  box.classList.toggle('visible',Boolean(message));
}
async function call(path,data){
  result.textContent='処理中...';
  showOperationError('');
  try{
    const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:form(data)});
    const body=await response.json();
    result.textContent=JSON.stringify(body,null,2);
    if(typeof body.communication_log==='string'){
      setSensorCommunicationLog(body.communication_log,Boolean(body.communication_log_truncated));
    }
    if(!response.ok||!body.ok){
      showOperationError(`処理に失敗しました: ${body.code||response.status}\n${body.message||'詳細は共有用診断データを確認してください。'}${body.storage_detail?`\n保存処理: ${body.storage_detail}`:''}`);
      result.closest('details').open=true;
    }
    await refreshStatus();
    return body;
  }catch(error){
    const message='通信が切断されました: '+error+'\nFGTのAPへ再接続してこの画面を開き直し、「共有用診断データ」を共有してください。';
    result.textContent=message;
    showOperationError(message);
    return null;
  }
}
async function refreshStatus(){
  try{
    const response=await fetch('/api/fgt/commissioning/status',{cache:'no-store'});
    const s=await response.json();
    if(!s.ok){
      if(s.code==='busy')return;
      throw new Error(s.message||'状態取得失敗');
    }
    const active=s.active_output>0?`MOSFET ${s.active_output} ${s.active_output_label} ON（残り ${(s.active_remaining_ms/1000).toFixed(1)}秒）`:'全MOSFET OFF';
    const guard=s.guard_remaining_ms>0?`保護期間 ${(s.guard_remaining_ms/1000).toFixed(1)}秒`:'ON許可';
    const power=s.sensor_power_on?'センサー12V ON':'センサー12V OFF';
    const detection=s.sensor_detection_running?'<span class="pill warn">センサー検出中</span>':'';
    const updating=s.firmware_update_running?'<span class="pill danger">F/W更新中</span>':'';
    const loopback=s.rs485_internal_loopback_ok?'<span class="pill ok">UART内部試験 OK</span>':'<span class="pill danger">UART内部試験 NG</span>';
    document.getElementById('status').innerHTML=`<span class="pill ${s.active_output>0?'danger':'ok'}">${active}</span><span class="pill ${s.guard_remaining_ms>0?'warn':'ok'}">${guard}</span><span class="pill">${power}</span><span class="pill">センサー通信 ${s.rs485_ready?'準備完了':'未準備'}</span>${loopback}${detection}${updating}`;
    const resetDanger=['panic','interrupt_watchdog','task_watchdog','watchdog','brownout'].includes(s.reset_reason);
    const interrupted=s.registration_interrupted;
    document.getElementById('diagnosticSummary').innerHTML=
      `<span class="pill ${interrupted||resetDanger?'danger':'ok'}">再起動理由: ${escapeHtml(s.reset_reason)}</span>`+
      `<span class="pill ${interrupted?'danger':s.registration_last_result==='ok'?'ok':'warn'}">直前の登録: ${escapeHtml(s.registration_last_result)}</span>`+
      `<span class="pill ${s.async_tcp_stack_low_water_mark_bytes<2048?'danger':'ok'}">HTTP最小空きスタック ${s.async_tcp_stack_low_water_mark_bytes} bytes</span>`+
      `<span class="pill">空きヒープ ${s.free_heap_bytes} bytes</span>`;
    document.getElementById('diagnosticDetails').textContent=JSON.stringify({
      firmware_version:s.firmware_version,
      firmware_build_id:s.firmware_build_id,
      reset_reason:s.reset_reason,
      reset_reason_code:s.reset_reason_code,
      registration_interrupted:s.registration_interrupted,
      registration_last_result:s.registration_last_result,
      registration_storage_error:s.registration_storage_error,
      registration_sensor_id:s.registration_sensor_id,
      registration_sensor_baud:s.registration_sensor_baud,
      registration_stack_before_bytes:s.registration_stack_before_bytes,
      registration_stack_after_bytes:s.registration_stack_after_bytes,
      registration_heap_before_bytes:s.registration_heap_before_bytes,
      registration_heap_after_bytes:s.registration_heap_after_bytes,
      async_tcp_stack_size_bytes:s.async_tcp_stack_size_bytes,
      async_tcp_stack_low_water_mark_bytes:s.async_tcp_stack_low_water_mark_bytes,
      free_heap_bytes:s.free_heap_bytes,
      registry_store_bytes:s.registry_store_bytes
    },null,2);
    if(interrupted){
      showOperationError('直前のセンサー登録処理中にFGTが再起動しました。共有用診断データを共有してください。');
      document.getElementById('diagnosticDetails').closest('details').open=true;
    }else if(resetDanger){
      showOperationError(`FGTの再起動理由は ${s.reset_reason} です。共有用診断データを共有してください。`);
      document.getElementById('diagnosticDetails').closest('details').open=true;
    }
    document.querySelectorAll('[data-output]').forEach(button=>button.disabled=s.firmware_update_running||s.active_output>0||s.guard_remaining_ms>0||!s.io_ready);
    document.querySelectorAll('[data-sensor-action]').forEach(button=>button.disabled=s.firmware_update_running||s.active_output>0||s.sensor_detection_running);
    updateRegisterButton(s.firmware_update_running||s.active_output>0||s.sensor_detection_running);
  }catch(error){document.getElementById('status').innerHTML='<span class="pill danger">状態取得失敗</span>'}
}
function outputOn(channel){
  const seconds=Number(document.getElementById('duration').value);
  call('/api/fgt/commissioning/output',{channel,duration_ms:seconds*1000});
}
function allOff(){call('/api/fgt/commissioning/all-off',{})}
function sensorPower(on){call('/api/fgt/commissioning/sensor-power',{enabled:on?1:0})}
async function runTtlLoopback(){
  if(!document.getElementById('ttlLoopbackConfirmed').checked){
    result.textContent='MAX3485基板を外し、XIAOのD6-D7だけを直結したことを確認してください。';
    result.closest('details').open=true;
    return;
  }
  const body=await call('/api/fgt/commissioning/rs485/ttl-loopback',{wiring_confirmed:1});
  result.closest('details').open=true;
  if(body&&body.ok)document.getElementById('ttlLoopbackConfirmed').checked=false;
  await refreshStatus();
}
function configuredAddressConflict(sensor){
  return sensor?configuredDevices.find(device=>device.id===sensor.id&&device.baud===sensor.baud):null;
}
function suggestedAddress(sensor){
  for(let id=1;id<=10;id++){
    if(id!==sensor.id&&!configuredDevices.some(device=>device.baud===sensor.baud&&device.id===id))return id;
  }
  return null;
}
function updateRegisterButton(operationBlocked=false){
  const sensor=detectedSensors.length===1?detectedSensors[0]:null;
  document.getElementById('registerDeviceButton').disabled=operationBlocked||!sensor||Boolean(configuredAddressConflict(sensor));
}
function updateRegistrationTypeHint(){
  const selector=document.getElementById('deviceType');
  const hint=document.getElementById('deviceTypeHint');
  const sensor=detectedSensors.length===1?detectedSensors[0]:null;
  if(!sensor){
    selector.disabled=true;
    hint.textContent='1台だけ検出すると、自動判定された種別を確認・訂正できます。';
    return;
  }
  selector.disabled=false;
  const typeNames={soil:'土壌センサー',par:'PAR（日射）センサー'};
  const basisNames={
    reserved_par_address_3:'予約アドレス3に基づく判定',
    single_register_response_only:'1レジスタだけ応答',
    nonzero_soil_signature_registers:'土壌判定用レジスタが非ゼロ',
    nonzero_secondary_measurements:'追加測定レジスタが非ゼロ',
    single_measurement_values_only:'追加測定値なし'
  };
  const automatic=typeNames[sensor.sensor_type]||sensor.sensor_type;
  const selected=typeNames[selector.value]||selector.value;
  const basis=basisNames[sensor.identification_basis]||sensor.identification_basis||'判定根拠なし';
  hint.textContent=selector.value===sensor.sensor_type
    ?`自動判定: ${automatic}（${basis}）。実機ラベルと違う場合は変更してください。`
    :`手動訂正: 自動判定「${automatic}」から「${selected}」へ変更して登録します。登録前に選択種別のレジスタを再読取します。`;
}
async function loadConfiguredDevices(){
  try{
    const response=await fetch('/api/fgt/commissioning/devices',{cache:'no-store'});
    const body=await response.json();
    if(!body.ok)throw new Error(body.message||'登録構成の取得に失敗しました');
    configuredDevices=Array.isArray(body.devices)?body.devices:[];
    renderConfiguredDevices(body.saved_registry);
    updateAddressRegistryOptions();
    updateRegisterButton();
  }catch(error){
    document.getElementById('configuredSummary').innerHTML='<span class="pill danger">登録構成を取得できません</span>';
    document.getElementById('configuredDevices').innerHTML=`<div class="empty">${escapeHtml(error.message)}</div>`;
  }
}
function renderConfiguredDevices(savedRegistry=true){
  const summary=document.getElementById('configuredSummary');
  const list=document.getElementById('configuredDevices');
  if(configuredDevices.length===0){
    summary.innerHTML=savedRegistry?'<span class="pill warn">登録0台</span>':'<span class="pill warn">未構築</span>';
    list.innerHTML='<div class="empty">センサーはまだ登録されていません。1台だけ接続して、下の自動検出から登録してください。</div>';
    return;
  }
  const enabled=configuredDevices.filter(device=>device.enabled).length;
  summary.innerHTML=`<span class="pill ok">${configuredDevices.length}台登録済み</span><span class="pill">${enabled}台を通常運転で使用</span>`;
  list.innerHTML=configuredDevices.map((device,index)=>`
    <article class="configured">
      <div class="sensor-head"><div><h3>${escapeHtml(device.name)}</h3><div class="sensor-meta">${escapeHtml(device.model)}・${escapeHtml(device.location)}</div></div><span class="pill ${device.enabled?'ok':'warn'}">${device.enabled?'使用中':'無効'}</span></div>
      <div class="status"><span class="pill">アドレス ${device.id}</span><span class="pill">${device.baud} bps</span><span class="pill">FC${String(device.function_code).padStart(2,'0')} / 0x${Number(device.start_register).toString(16).toUpperCase().padStart(4,'0')}</span></div>
      <div class="configured-grid">
        <div><label for="configuredName${index}">センサー名</label><input id="configuredName${index}" maxlength="20" value="${escapeHtml(device.name)}"></div>
        <div><label for="configuredLocation${index}">接続場所・用途</label><input id="configuredLocation${index}" maxlength="30" value="${escapeHtml(device.location)}"></div>
      </div>
      <label class="confirm"><input id="configuredEnabled${index}" type="checkbox" ${device.enabled?'checked':''}>通常運転でこのセンサーを使用する</label>
      <div class="actions"><button onclick="updateConfiguredDevice(${index})">変更を保存</button><button class="stop" onclick="removeConfiguredDevice(${index})">登録を削除</button></div>
    </article>`).join('');
}
async function registerDetectedDevice(){
  if(detectedSensors.length!==1){result.textContent='登録するセンサー1台だけを接続して、自動検出してください。';result.closest('details').open=true;return}
  const conflict=configuredAddressConflict(detectedSensors[0]);
  if(conflict){result.textContent=`同じ通信速度・アドレスは「${conflict.name}」で使用済みです。新しいセンサーなら先にアドレスを変更してください。`;result.closest('details').open=true;return}
  const name=value('deviceName').trim();
  const location=value('deviceLocation').trim();
  if(!name||!location){result.textContent='センサー名と接続場所・用途を入力してください。';result.closest('details').open=true;return}
  const body=await call('/api/fgt/commissioning/devices/register',{sensor_index:0,sensor_type:value('deviceType'),name,location});
  if(body&&body.ok){
    document.getElementById('deviceName').value='';
    document.getElementById('deviceLocation').value='';
    detectedSensors=[];
    document.getElementById('deviceType').disabled=true;
    updateRegistrationTypeHint();
    document.getElementById('sensorSummary').innerHTML='<span class="pill ok">登録完了</span>';
    document.getElementById('sensorList').innerHTML='<div class="empty">次のセンサーへつなぎ替え、「センサーを自動検出して試験」を実行してください。</div>';
    document.getElementById('addressSensor').innerHTML='<option value="">先に自動検出してください</option>';
    updateAddressRegistryOptions();
    updateRegisterButton();
    await loadConfiguredDevices();
  }
}
async function updateConfiguredDevice(index){
  const body=await call('/api/fgt/commissioning/devices/update',{
    index,name:value(`configuredName${index}`).trim(),
    location:value(`configuredLocation${index}`).trim(),
    enabled:document.getElementById(`configuredEnabled${index}`).checked?1:0
  });
  if(body&&body.ok)await loadConfiguredDevices();
}
async function removeConfiguredDevice(index){
  const device=configuredDevices[index];
  if(!device||!confirm(`「${device.name}」の登録を削除しますか？\\nセンサー本体のModbusアドレスは変更されません。`))return;
  const body=await call('/api/fgt/commissioning/devices/remove',{index});
  if(body&&body.ok)await loadConfiguredDevices();
}
function renderSensors(){
  const list=document.getElementById('sensorList');
  const summary=document.getElementById('sensorSummary');
  const selector=document.getElementById('addressSensor');
  selector.innerHTML='<option value="">変更するセンサーを選択</option>';
  if(detectedSensors.length===0){
    summary.innerHTML='<span class="pill danger">センサー未検出</span>';
    list.innerHTML='<div class="empty">応答するセンサーがありません。電源、A/B、GND、アドレス重複を確認してください。</div>';
    updateAddressRegistryOptions();
    updateRegistrationTypeHint();
    updateRegisterButton();
    return;
  }
  const passed=detectedSensors.filter(sensor=>sensor.test_pass).length;
  summary.innerHTML=`<span class="pill ok">${detectedSensors.length}台検出</span><span class="pill ${passed===detectedSensors.length?'ok':'warn'}">値取得成功 ${passed}/${detectedSensors.length}</span>`;
  if(detectedSensors.length===1){
    const conflict=configuredAddressConflict(detectedSensors[0]);
    if(conflict){
      summary.innerHTML+=`<span class="pill danger">アドレスは「${escapeHtml(conflict.name)}」で使用済み</span>`;
      const suggestion=suggestedAddress(detectedSensors[0]);
      if(suggestion!==null)document.getElementById('newId').value=String(suggestion);
    }
  }
  list.innerHTML=detectedSensors.map((sensor,index)=>{
    const confidence=sensor.identification_basis==='reserved_par_address_3'
      ?'<span class="pill ok">ID 3からPAR判定</span>'
      :sensor.identification_confidence==='tentative'
        ?'<span class="pill warn">機種推定</span>'
        :'<span class="pill ok">自動識別</span>';
    const test=sensor.test_pass
      ?'<span class="pill ok">値取得OK</span>'
      :'<span class="pill danger">要確認</span>';
    const measurements=(sensor.measurements||[]).map(item=>`<div class="measurement"><span>${item.label}</span><strong>${item.value} ${item.unit||''}</strong></div>`).join('');
    return `<article class="sensor"><div class="sensor-head"><div><h3>${sensor.name}</h3><div class="sensor-meta">${sensor.model}・アドレス ${sensor.id}</div></div><div>${test}${confidence}</div></div><div class="measurements">${measurements}</div><p class="hint">${sensor.test_message}</p><div class="actions"><button data-sensor-action onclick="testSensor(${index})">このセンサーの値を再取得</button></div></article>`;
  }).join('');
  if(detectedSensors.length===1){
    const selectorType=document.getElementById('deviceType');
    selectorType.value=detectedSensors[0].sensor_type;
  }
  updateRegistrationTypeHint();
  detectedSensors.forEach((sensor,index)=>{
    const option=document.createElement('option');
    option.value=String(index);
    option.textContent=`${sensor.name}（アドレス ${sensor.id}）`;
    selector.appendChild(option);
  });
  updateAddressRegistryOptions();
  updateRegisterButton();
}
function updateAddressRegistryOptions(){
  const selector=document.getElementById('addressRegistry');
  const selectedIndex=value('addressSensor');
  const sensor=selectedIndex===''?null:detectedSensors[Number(selectedIndex)];
  selector.innerHTML='<option value="255">新しく追加する未登録センサー</option>';
  if(!sensor)return;
  configuredDevices.forEach((device,index)=>{
    if(device.sensor_type!==sensor.sensor_type||device.id!==sensor.id||device.baud!==sensor.baud)return;
    const option=document.createElement('option');
    option.value=String(index);
    option.textContent=`登録済み「${device.name}」の構成も更新`;
    selector.appendChild(option);
  });
}
async function detectSensors(){
  const button=document.getElementById('detectButton');
  button.disabled=true;
  detectedSensors=[];
  setSensorCommunicationLog('');
  updateRegisterButton(true);
  document.getElementById('sensorSummary').innerHTML='<span class="pill warn">自動検出中…最大約10秒</span>';
  try{
    const started=await call('/api/fgt/commissioning/sensors/detect',{});
    if(!started||!started.ok)return;
    for(let attempt=0;attempt<120;attempt++){
      await new Promise(resolve=>setTimeout(resolve,500));
      const response=await fetch('/api/fgt/commissioning/sensors/detect/status',{cache:'no-store'});
      if(response.status===409)continue;
      const body=await response.json();
      if(typeof body.communication_log==='string'){
        setSensorCommunicationLog(body.communication_log,Boolean(body.communication_log_truncated));
      }
      if(body.state==='running'){
        document.getElementById('sensorSummary').innerHTML=`<span class="pill warn">自動検出中 ${body.completed_steps}/${body.total_steps}</span><span class="pill">${body.found}台応答</span>`;
        continue;
      }
      result.textContent=JSON.stringify(body,null,2);
      if(!body.ok)result.closest('details').open=true;
      detectedSensors=Array.isArray(body.sensors)?body.sensors:[];
      renderSensors();
      await refreshStatus();
      return;
    }
    result.textContent='自動検出の完了を確認できませんでした。画面を再読み込みしてください。';
    result.closest('details').open=true;
  }finally{button.disabled=false}
}
async function testSensor(index){
  const sensor=detectedSensors[index];
  if(!sensor)return;
  const body=await call('/api/fgt/commissioning/sensors/test',{
    sensor_type:sensor.sensor_type,slave_id:sensor.id,baud:sensor.baud,
    identification_confidence:sensor.identification_confidence
  });
  if(body&&body.sensor){detectedSensors[index]=body.sensor;renderSensors()}
}
async function changeAddress(){
  if(!document.getElementById('singleConfirmed').checked){result.textContent='対象センサー1台だけの接続確認が必要です。';return}
  const selected=value('addressSensor');
  if(selected===''){result.textContent='先にセンサーを自動検出し、変更対象を選択してください。';return}
  const sensor=detectedSensors[Number(selected)];
  if(!sensor)return;
  const body=await call('/api/fgt/commissioning/modbus/change-address',{
    sensor_type:sensor.sensor_type,baud:sensor.baud,old_id:sensor.id,
    new_id:value('newId'),identification_confidence:sensor.identification_confidence,
    registry_index:value('addressRegistry'),
    single_device_confirmed:1
  });
  if(body&&body.ok){
    document.getElementById('singleConfirmed').checked=false;
    await detectSensors();
    await loadConfiguredDevices();
  }
}
loadConfiguredDevices();refreshStatus();setInterval(refreshStatus,500);
</script></body></html>
)HTML";

bool take_operation(TickType_t wait_ticks = pdMS_TO_TICKS(50))
{
    return s_operation_mutex != nullptr &&
           xSemaphoreTake(s_operation_mutex, wait_ticks) == pdTRUE;
}

void release_operation()
{
    if (s_operation_mutex != nullptr)
    {
        xSemaphoreGive(s_operation_mutex);
    }
}

bool auto_detection_running()
{
    return s_auto_detection.phase == AutoDetectionPhase::power_settle ||
           s_auto_detection.phase == AutoDetectionPhase::scanning;
}

void append_sensor_communication_log(const char *format, ...)
{
    if (format == nullptr || s_auto_detection.communication_log_truncated)
    {
        return;
    }
    const size_t capacity =
        sizeof(s_auto_detection.communication_log);
    const size_t remaining =
        capacity - s_auto_detection.communication_log_length;
    if (remaining <= 1)
    {
        s_auto_detection.communication_log_truncated = true;
        return;
    }

    va_list arguments;
    va_start(arguments, format);
    const int written = vsnprintf(
        s_auto_detection.communication_log +
            s_auto_detection.communication_log_length,
        remaining,
        format,
        arguments);
    va_end(arguments);
    if (written < 0)
    {
        return;
    }
    if (static_cast<size_t>(written) >= remaining)
    {
        static constexpr char kTruncatedMarker[] =
            "\n[LOG] result=TRUNCATED\n";
        const size_t marker_length = sizeof(kTruncatedMarker) - 1;
        if (capacity > marker_length + 1)
        {
            const size_t marker_offset =
                capacity - marker_length - 1;
            memcpy(
                s_auto_detection.communication_log + marker_offset,
                kTruncatedMarker,
                marker_length);
            s_auto_detection.communication_log[capacity - 1] = '\0';
            s_auto_detection.communication_log_length =
                capacity - 1;
        }
        s_auto_detection.communication_log_truncated = true;
        return;
    }
    s_auto_detection.communication_log_length +=
        static_cast<size_t>(written);
}

void reset_auto_detection()
{
    s_auto_detection.phase = AutoDetectionPhase::idle;
    s_auto_detection.started_ms = 0;
    s_auto_detection.power_ready_ms = 0;
    s_auto_detection.baud_index = 0;
    s_auto_detection.next_id = 1;
    s_auto_detection.sensor_count = 0;
    s_auto_detection.passed_count = 0;
    s_auto_detection.communication_log[0] = '\0';
    s_auto_detection.communication_log_length = 0;
    s_auto_detection.communication_transaction_count = 0;
    s_auto_detection.communication_log_truncated = false;
}

void cancel_auto_detection()
{
    if (auto_detection_running())
    {
        s_auto_detection.phase = AutoDetectionPhase::cancelled;
        Serial.printf(
            "FGT commissioning sensor detection cancelled: completed=%u elapsed=%lu ms\n",
            static_cast<unsigned int>(
                static_cast<size_t>(s_auto_detection.baud_index) *
                    kAutoScanMaxId +
                static_cast<size_t>(s_auto_detection.next_id - 1)),
            static_cast<unsigned long>(
                millis() - s_auto_detection.started_ms));
    }
}

bool prepare_local_firmware_update()
{
    if (!take_operation(pdMS_TO_TICKS(100)))
    {
        return false;
    }
    cancel_auto_detection();
    if (s_io_ready)
    {
        hal_direct_gpio_all_outputs_off(
            &s_commissioning_io);
    }
    s_interlock.request_off(millis());
    if (s_sensor_power_ready)
    {
        hal_power_switch_set(
            &s_commissioning_sensor_power,
            false);
    }
    release_operation();
    Serial.println(
        "FGT commissioning prepared for firmware update: outputs=off sensor_power=off");
    return true;
}

void send_json(AsyncWebServerRequest *request, int status, JsonDocument &doc)
{
    String body;
    serializeJson(doc, body);
    request->send(status, "application/json; charset=utf-8", body);
}

void send_error(AsyncWebServerRequest *request,
                int status,
                const char *code,
                const char *message)
{
    JsonDocument doc;
    doc["ok"] = false;
    doc["code"] = code;
    doc["message"] = message;
    send_json(request, status, doc);
}

void send_sensor_communication_error(
    AsyncWebServerRequest *request,
    int status,
    const char *code,
    const char *message)
{
    JsonDocument doc;
    doc["ok"] = false;
    doc["code"] = code;
    doc["message"] = message;
    doc["communication_log"] =
        s_auto_detection.communication_log;
    doc["communication_log_truncated"] =
        s_auto_detection.communication_log_truncated;
    send_json(request, status, doc);
}

const char *reset_reason_name(esp_reset_reason_t reason)
{
    switch (reason)
    {
    case ESP_RST_POWERON:
        return "power_on";
    case ESP_RST_EXT:
        return "external_reset";
    case ESP_RST_SW:
        return "software_reset";
    case ESP_RST_PANIC:
        return "panic";
    case ESP_RST_INT_WDT:
        return "interrupt_watchdog";
    case ESP_RST_TASK_WDT:
        return "task_watchdog";
    case ESP_RST_WDT:
        return "watchdog";
    case ESP_RST_DEEPSLEEP:
        return "deep_sleep";
    case ESP_RST_BROWNOUT:
        return "brownout";
    case ESP_RST_SDIO:
        return "sdio";
    case ESP_RST_UNKNOWN:
    default:
        return "unknown";
    }
}

bool reject_during_firmware_update(
    AsyncWebServerRequest *request)
{
    if (!app_fgt_local_update_busy())
    {
        return false;
    }
    send_error(
        request,
        409,
        "firmware_update_running",
        "Firmware update is running. Every commissioning operation is disabled until restart.");
    return true;
}

bool parse_uint(AsyncWebServerRequest *request,
                const char *name,
                uint32_t minimum,
                uint32_t maximum,
                uint32_t *value_out)
{
    if (value_out == nullptr || !request->hasParam(name, true))
    {
        return false;
    }
    const String value = request->getParam(name, true)->value();
    if (value.length() == 0)
    {
        return false;
    }
    errno = 0;
    char *end = nullptr;
    const unsigned long parsed = strtoul(value.c_str(), &end, 0);
    if (errno != 0 || end == value.c_str() || *end != '\0' ||
        parsed < minimum || parsed > maximum)
    {
        return false;
    }
    *value_out = static_cast<uint32_t>(parsed);
    return true;
}

bool baud_supported(uint32_t baud)
{
    return baud == 2400 || baud == 4800 || baud == 9600;
}

bool ensure_rs485_baud(uint32_t baud)
{
    if (!baud_supported(baud))
    {
        return false;
    }
    if (s_rs485_ready && s_rs485_baud == baud)
    {
        return true;
    }

    hal_rs485_modbus_deinit();
    hal_rs485_modbus_config_t config = hal_rs485_modbus_default_config();
    config.baud = baud;
    config.response_timeout_ms = APP_FGT_COMMISSIONING_RS485_TIMEOUT_MS;
    s_rs485_ready = hal_rs485_modbus_init(&config);
    s_rs485_baud = s_rs485_ready ? baud : 0;
    return s_rs485_ready;
}

void handle_status(AsyncWebServerRequest *request)
{
    if (!take_operation())
    {
        send_error(request, 409, "busy", "Another commissioning operation is running.");
        return;
    }
    const fgt::CommissioningSwitchSnapshot state = s_interlock.snapshot(millis());
    JsonDocument doc;
    doc["ok"] = true;
    doc["io_ready"] = s_io_ready;
    doc["sensor_power_ready"] = s_sensor_power_ready;
    doc["sensor_power_on"] =
        s_sensor_power_ready && hal_power_switch_enabled(&s_commissioning_sensor_power);
    doc["rs485_ready"] = s_rs485_ready;
    doc["rs485_baud"] = s_rs485_baud;
    doc["rs485_internal_loopback_ok"] =
        s_rs485_internal_loopback_ok;
    doc["sensor_detection_running"] = auto_detection_running();
    doc["firmware_update_running"] =
        app_fgt_local_update_busy();
    doc["active_output"] =
        state.active_channel >= 0 ? static_cast<int>(state.active_channel) + 1 : 0;
    doc["active_output_label"] =
        state.active_channel >= 0 ? kOutputLabels[state.active_channel] : "";
    doc["active_remaining_ms"] = state.active_remaining_ms;
    doc["guard_remaining_ms"] = state.guard_remaining_ms;
    doc["guard_ms"] = APP_FGT_COMMISSIONING_SWITCH_GUARD_MS;
    doc["max_on_ms"] = APP_FGT_COMMISSIONING_MAX_ON_MS;
    doc["firmware_version"] = APP_FIRMWARE_VERSION;
    doc["firmware_build_id"] = APP_FIRMWARE_BUILD_ID;
    doc["reset_reason"] =
        reset_reason_name(s_portal_reset_reason);
    doc["reset_reason_code"] =
        static_cast<int>(s_portal_reset_reason);
    doc["registration_interrupted"] =
        s_registration_interrupted;
    doc["registration_last_result"] =
        s_registration_last_result;
    doc["registration_storage_error"] =
        app_fgt_rs485_devices_last_storage_error();
    doc["registration_sensor_id"] =
        s_registration_sensor_id;
    doc["registration_sensor_baud"] =
        s_registration_sensor_baud;
    doc["registration_stack_before_bytes"] =
        s_registration_stack_before_bytes;
    doc["registration_stack_after_bytes"] =
        s_registration_stack_after_bytes;
    doc["registration_heap_before_bytes"] =
        s_registration_heap_before_bytes;
    doc["registration_heap_after_bytes"] =
        s_registration_heap_after_bytes;
    doc["async_tcp_stack_size_bytes"] =
        CONFIG_ASYNC_TCP_STACK_SIZE;
    doc["async_tcp_stack_low_water_mark_bytes"] =
        static_cast<uint32_t>(
            uxTaskGetStackHighWaterMark(nullptr));
    doc["free_heap_bytes"] = ESP.getFreeHeap();
    doc["registry_store_bytes"] =
        app_fgt_rs485_devices_registry_size();
    release_operation();
    send_json(request, 200, doc);
}

void handle_output_on(AsyncWebServerRequest *request)
{
    if (reject_during_firmware_update(request))
    {
        return;
    }
    uint32_t channel = 0;
    uint32_t duration_ms = 0;
    if (!parse_uint(request, "channel", 1, 5, &channel) ||
        !parse_uint(request, "duration_ms", 100, APP_FGT_COMMISSIONING_MAX_ON_MS,
                    &duration_ms))
    {
        send_error(request, 400, "invalid_request",
                   "channel must be 1..5 and duration_ms must be within the safe limit.");
        return;
    }
    if (!take_operation())
    {
        send_error(request, 409, "busy", "Another commissioning operation is running.");
        return;
    }
    if (auto_detection_running())
    {
        release_operation();
        send_error(request, 409, "sensor_detection_running",
                   "Wait for automatic sensor detection to finish.");
        return;
    }
    if (!s_io_ready)
    {
        release_operation();
        send_error(request, 503, "io_not_ready", "MOSFET output GPIO is not ready.");
        return;
    }

    const uint32_t now_ms = millis();
    const fgt::CommissioningSwitchResult result =
        s_interlock.request_on(static_cast<uint8_t>(channel - 1), duration_ms, now_ms);
    if (result != fgt::CommissioningSwitchResult::ok)
    {
        const fgt::CommissioningSwitchSnapshot state = s_interlock.snapshot(now_ms);
        release_operation();
        JsonDocument doc;
        doc["ok"] = false;
        doc["code"] = fgt::commissioning_switch_result_name(result);
        doc["guard_remaining_ms"] = state.guard_remaining_ms;
        doc["active_output"] =
            state.active_channel >= 0 ? static_cast<int>(state.active_channel) + 1 : 0;
        send_json(request, 409, doc);
        return;
    }

    hal_direct_gpio_all_outputs_off(&s_commissioning_io);
    const uint16_t selected = static_cast<uint16_t>(1U << (channel - 1));
    if (!hal_direct_gpio_write_outputs(&s_commissioning_io, kAllOutputsMask, selected))
    {
        hal_direct_gpio_all_outputs_off(&s_commissioning_io);
        s_interlock.request_off(now_ms);
        release_operation();
        send_error(request, 500, "gpio_write_failed", "Failed to turn the selected output on.");
        return;
    }

    Serial.printf("FGT commissioning output ON: channel=%lu label=%s duration=%lu ms\n",
                  static_cast<unsigned long>(channel),
                  kOutputLabels[channel - 1],
                  static_cast<unsigned long>(duration_ms));
    release_operation();
    JsonDocument doc;
    doc["ok"] = true;
    doc["active_output"] = channel;
    doc["duration_ms"] = duration_ms;
    send_json(request, 200, doc);
}

void handle_all_off(AsyncWebServerRequest *request)
{
    if (!take_operation())
    {
        send_error(request, 409, "busy", "Another commissioning operation is running.");
        return;
    }
    if (s_io_ready)
    {
        hal_direct_gpio_all_outputs_off(&s_commissioning_io);
    }
    cancel_auto_detection();
    const bool was_active = s_interlock.request_off(millis());
    release_operation();
    Serial.printf("FGT commissioning all outputs OFF: was_active=%s\n",
                  was_active ? "true" : "false");
    JsonDocument doc;
    doc["ok"] = true;
    doc["was_active"] = was_active;
    doc["guard_ms"] = was_active ? APP_FGT_COMMISSIONING_SWITCH_GUARD_MS : 0;
    send_json(request, 200, doc);
}

void handle_sensor_power(AsyncWebServerRequest *request)
{
    if (reject_during_firmware_update(request))
    {
        return;
    }
    uint32_t enabled = 0;
    if (!parse_uint(request, "enabled", 0, 1, &enabled))
    {
        send_error(request, 400, "invalid_request", "enabled must be 0 or 1.");
        return;
    }
    if (!take_operation())
    {
        send_error(request, 409, "busy", "Another commissioning operation is running.");
        return;
    }
    if (!s_sensor_power_ready)
    {
        release_operation();
        send_error(request, 503, "sensor_power_not_ready",
                   "RS485 sensor power GPIO is not ready.");
        return;
    }
    if (auto_detection_running())
    {
        if (enabled != 0)
        {
            release_operation();
            send_error(request, 409, "sensor_detection_running",
                       "Sensor power is already managed by automatic detection.");
            return;
        }
        cancel_auto_detection();
    }

    bool ok = false;
    if (enabled != 0)
    {
        const fgt::CommissioningSwitchSnapshot state = s_interlock.snapshot(millis());
        if (state.active_channel >= 0)
        {
            release_operation();
            send_error(request, 409, "output_active",
                       "Turn every MOSFET output off before enabling sensor power.");
            return;
        }
        ok = hal_power_switch_enable_wait(&s_commissioning_sensor_power, 800);
    }
    else
    {
        ok = hal_power_switch_set(&s_commissioning_sensor_power, false);
    }
    release_operation();

    JsonDocument doc;
    doc["ok"] = ok;
    doc["sensor_power_on"] = enabled != 0 && ok;
    send_json(request, ok ? 200 : 500, doc);
}

void handle_rs485_ttl_loopback(
    AsyncWebServerRequest *request)
{
    if (reject_during_firmware_update(request))
    {
        return;
    }
    uint32_t wiring_confirmed = 0;
    if (!parse_uint(
            request, "wiring_confirmed", 1, 1,
            &wiring_confirmed))
    {
        send_error(
            request, 400, "wiring_confirmation_required",
            "Disconnect the MAX3485 module and connect only D6 to D7 before running this test.");
        return;
    }
    if (!take_operation())
    {
        send_error(
            request, 409, "busy",
            "Another commissioning operation is running.");
        return;
    }
    if (auto_detection_running())
    {
        release_operation();
        send_error(
            request, 409, "sensor_detection_running",
            "Wait for automatic sensor detection to finish.");
        return;
    }
    const fgt::CommissioningSwitchSnapshot state =
        s_interlock.snapshot(millis());
    if (state.active_channel >= 0)
    {
        release_operation();
        send_error(
            request, 409, "output_active",
            "Turn every MOSFET output off before the UART wiring test.");
        return;
    }
    if (s_sensor_power_ready)
    {
        hal_power_switch_set(
            &s_commissioning_sensor_power, false);
    }
    if (!ensure_rs485_baud(4800))
    {
        release_operation();
        send_error(
            request, 500, "rs485_not_ready",
            "Failed to initialize UART1 for the D6-D7 wiring test.");
        return;
    }

    const bool passed =
        hal_rs485_modbus_external_loopback_test();
    release_operation();

    JsonDocument doc;
    doc["ok"] = passed;
    doc["test"] = "external_d6_d7_loopback";
    doc["uart"] = APP_RS485_UART_NUM;
    doc["tx_pin"] = APP_RS485_TX_PIN;
    doc["rx_pin"] = APP_RS485_RX_PIN;
    doc["message"] =
        passed
            ? "D6 TX and D7 RX passed the physical jumper loopback test."
            : "D6-D7 loopback failed. Check the jumper and the XIAO ESP32-C6 D6/D7 pins.";
    send_json(request, passed ? 200 : 502, doc);
}

const char *sensor_type_key(fgt::CommissioningSensorType type)
{
    return type == fgt::CommissioningSensorType::soil ? "soil" : "par";
}

const char *sensor_display_name(fgt::CommissioningSensorType type)
{
    return type == fgt::CommissioningSensorType::soil
               ? "土壌センサー"
               : "PAR（日射）センサー";
}

const char *sensor_model_name(fgt::CommissioningSensorType type)
{
    return type == fgt::CommissioningSensorType::soil
               ? "ComWinTop CWT-SOIL NPKPHCTH-S"
               : "DFRobot SEN0641 PAR";
}

fgt::Rs485DeviceType registry_device_type(
    fgt::CommissioningSensorType type)
{
    return type == fgt::CommissioningSensorType::soil
               ? fgt::Rs485DeviceType::soil
               : fgt::Rs485DeviceType::par;
}

const char *registry_device_type_key(fgt::Rs485DeviceType type)
{
    return type == fgt::Rs485DeviceType::soil ? "soil" : "par";
}

const char *registry_device_model_name(fgt::Rs485DeviceType type)
{
    return type == fgt::Rs485DeviceType::soil
               ? "ComWinTop CWT-SOIL NPKPHCTH-S"
               : "DFRobot SEN0641 PAR";
}

bool parse_text(AsyncWebServerRequest *request,
                const char *name,
                char *value_out,
                size_t value_size,
                bool required)
{
    if (request == nullptr || name == nullptr ||
        value_out == nullptr || value_size == 0 ||
        !request->hasParam(name, true))
    {
        return false;
    }
    String value = request->getParam(name, true)->value();
    value.trim();
    if ((required && value.length() == 0) ||
        value.length() >= value_size)
    {
        return false;
    }
    memcpy(value_out, value.c_str(), value.length() + 1);
    return true;
}

void add_configured_device_json(
    JsonObject object,
    const fgt::Rs485DeviceConfig &device,
    size_t index)
{
    object["index"] = index;
    object["enabled"] = device.enabled;
    object["sensor_type"] = registry_device_type_key(device.type);
    object["model"] = registry_device_model_name(device.type);
    object["name"] = device.name;
    object["location"] = device.location;
    object["id"] = device.slave_id;
    object["baud"] = device.baud;
    object["function_code"] = device.function_code;
    object["start_register"] = device.start_register;
    object["register_count"] = device.register_count;
    object["scale"] = device.scale;
}

void add_configured_devices_json(JsonDocument &doc)
{
    const fgt::Rs485DeviceRegistry &registry =
        app_fgt_rs485_devices_get();
    doc["saved_registry"] =
        app_fgt_rs485_devices_has_saved_registry();
    doc["count"] = registry.count;
    JsonArray devices = doc["devices"].to<JsonArray>();
    for (size_t i = 0; i < registry.count; ++i)
    {
        JsonObject device = devices.add<JsonObject>();
        add_configured_device_json(device, registry.devices[i], i);
    }
}

bool parse_sensor_type(AsyncWebServerRequest *request,
                       fgt::CommissioningSensorType *type_out)
{
    if (type_out == nullptr || !request->hasParam("sensor_type", true))
    {
        return false;
    }
    const String value = request->getParam("sensor_type", true)->value();
    if (value == "soil")
    {
        *type_out = fgt::CommissioningSensorType::soil;
        return true;
    }
    if (value == "par")
    {
        *type_out = fgt::CommissioningSensorType::par;
        return true;
    }
    return false;
}

fgt::SensorIdentificationConfidence parse_identification_confidence(
    AsyncWebServerRequest *request)
{
    if (request->hasParam("identification_confidence", true))
    {
        const String value =
            request->getParam("identification_confidence", true)->value();
        if (value == "high")
        {
            return fgt::SensorIdentificationConfidence::high;
        }
        if (value == "medium")
        {
            return fgt::SensorIdentificationConfidence::medium;
        }
    }
    return fgt::SensorIdentificationConfidence::tentative;
}

bool prepare_sensor_operation(AsyncWebServerRequest *request)
{
    if (auto_detection_running())
    {
        send_error(request, 409, "sensor_detection_running",
                   "Wait for automatic sensor detection to finish.");
        return false;
    }
    const fgt::CommissioningSwitchSnapshot state = s_interlock.snapshot(millis());
    if (state.active_channel >= 0)
    {
        send_error(request, 409, "output_active",
                   "Turn every MOSFET output off before testing sensors.");
        return false;
    }
    if (!s_sensor_power_ready)
    {
        send_error(request, 503, "sensor_power_not_ready",
                   "RS485 sensor power GPIO is not ready.");
        return false;
    }
    if (!hal_power_switch_enabled(&s_commissioning_sensor_power) &&
        !hal_power_switch_enable_wait(&s_commissioning_sensor_power,
                                      kSensorPowerSettleMs))
    {
        send_error(request, 500, "sensor_power_failed",
                   "Failed to turn the RS485 sensor 12 V power on.");
        return false;
    }
    return true;
}

bool read_sensor_registers_with_log(
    uint8_t slave_id,
    uint8_t function_code,
    uint16_t start_register,
    uint16_t register_count,
    uint16_t *values,
    size_t value_capacity)
{
    const bool ok = hal_rs485_modbus_read_registers(
        slave_id,
        function_code,
        start_register,
        register_count,
        values,
        value_capacity);
    ++s_auto_detection.communication_transaction_count;
    append_sensor_communication_log(
        "[%03u] baud=%lu id=%u FC%02u reg=0x%04X count=%u result=%s",
        static_cast<unsigned int>(
            s_auto_detection.communication_transaction_count),
        static_cast<unsigned long>(s_rs485_baud),
        static_cast<unsigned int>(slave_id),
        static_cast<unsigned int>(function_code),
        static_cast<unsigned int>(start_register),
        static_cast<unsigned int>(register_count),
        ok ? "OK" : "NO_VALID_RESPONSE");
    if (ok)
    {
        append_sensor_communication_log(" values=[");
        for (size_t i = 0; i < register_count; ++i)
        {
            append_sensor_communication_log(
                "%s%u",
                i == 0 ? "" : ",",
                static_cast<unsigned int>(values[i]));
        }
        append_sensor_communication_log("]\n");
    }
    else
    {
        append_sensor_communication_log("\n");
    }
    return ok;
}

bool read_sensor_measurement(fgt::CommissioningSensorType type,
                             uint8_t slave_id,
                             CommissioningSensorReading *reading)
{
    if (reading == nullptr)
    {
        return false;
    }
    *reading = {};
    const uint16_t count =
        type == fgt::CommissioningSensorType::soil ? 7 : 1;
    reading->communication_ok = read_sensor_registers_with_log(
        slave_id, 0x03, 0x0000, count, reading->values, 7);
    if (!reading->communication_ok)
    {
        return false;
    }
    reading->values_plausible =
        type == fgt::CommissioningSensorType::par ||
        fgt::soil_measurement_values_plausible(
            reading->values[0], reading->values[1], reading->values[3]);
    return true;
}

void add_measurement(JsonArray measurements,
                     const char *label,
                     float value,
                     const char *unit)
{
    JsonObject measurement = measurements.add<JsonObject>();
    measurement["label"] = label;
    measurement["value"] = value;
    measurement["unit"] = unit;
}

void add_sensor_json(JsonObject sensor,
                     fgt::CommissioningSensorType type,
                     fgt::SensorIdentificationConfidence confidence,
                     const char *identification_basis,
                     uint8_t slave_id,
                     uint32_t baud,
                     const CommissioningSensorReading &reading)
{
    sensor["sensor_type"] = sensor_type_key(type);
    sensor["name"] = sensor_display_name(type);
    sensor["model"] = sensor_model_name(type);
    sensor["id"] = slave_id;
    sensor["baud"] = baud;
    sensor["identification_confidence"] =
        fgt::sensor_identification_confidence_name(confidence);
    sensor["identification_basis"] =
        identification_basis == nullptr
            ? "unknown"
            : identification_basis;
    sensor["communication_ok"] = reading.communication_ok;
    sensor["values_plausible"] = reading.values_plausible;
    sensor["test_pass"] =
        reading.communication_ok && reading.values_plausible;

    JsonArray measurements = sensor["measurements"].to<JsonArray>();
    if (reading.communication_ok &&
        type == fgt::CommissioningSensorType::soil)
    {
        add_measurement(measurements, "土壌水分",
                        reading.values[0] * 0.1F, "%");
        add_measurement(measurements, "温度",
                        static_cast<int16_t>(reading.values[1]) * 0.1F, "℃");
        add_measurement(measurements, "EC",
                        static_cast<float>(reading.values[2]), "µS/cm");
        add_measurement(measurements, "pH",
                        reading.values[3] * 0.1F, "");
        add_measurement(measurements, "窒素 N",
                        static_cast<float>(reading.values[4]), "mg/kg");
        add_measurement(measurements, "リン P",
                        static_cast<float>(reading.values[5]), "mg/kg");
        add_measurement(measurements, "カリウム K",
                        static_cast<float>(reading.values[6]), "mg/kg");
    }
    else if (reading.communication_ok)
    {
        add_measurement(measurements, "PAR",
                        static_cast<float>(reading.values[0]),
                        "µmol/m²/s");
    }

    if (!reading.communication_ok)
    {
        sensor["test_message"] =
            "センサーからCRC正常な応答を受信できませんでした。";
    }
    else if (!reading.values_plausible)
    {
        sensor["test_message"] =
            "通信できましたが、取得値がセンサー仕様の範囲外です。配線とセンサーを確認してください。";
    }
    else if (confidence == fgt::SensorIdentificationConfidence::tentative)
    {
        sensor["test_message"] =
            "センサー値を取得できました。固有情報が少ないため、機種はPARセンサーとして推定しています。";
    }
    else
    {
        sensor["test_message"] =
            "Modbus通信とセンサー値の取得に成功しました。";
    }
}

bool identify_sensor(uint8_t slave_id,
                     fgt::SensorIdentification *identification,
                     CommissioningSensorReading *reading,
                     const char **identification_basis)
{
    if (identification == nullptr ||
        reading == nullptr ||
        identification_basis == nullptr)
    {
        return false;
    }

    uint16_t primary_value = 0;
    if (!read_sensor_registers_with_log(
            slave_id, 0x03, 0x0000, 1, &primary_value, 1))
    {
        return false;
    }

    uint16_t soil_values[7] = {};
    const bool soil_measurement_supported =
        read_sensor_registers_with_log(
            slave_id, 0x03, 0x0000, 7, soil_values, 7);
    const bool soil_secondary_values_present =
        soil_measurement_supported &&
        (soil_values[1] != 0 || soil_values[2] != 0 ||
         soil_values[3] != 0 || soil_values[4] != 0 ||
         soil_values[5] != 0 || soil_values[6] != 0);

    uint16_t signature[3] = {};
    const bool soil_signature_read =
        soil_measurement_supported &&
        read_sensor_registers_with_log(
            slave_id, 0x03, 0x0022, 3, signature, 3);
    const bool soil_signature_present =
        soil_signature_read &&
        (signature[1] != 0 || signature[2] != 0);

    *identification = fgt::identify_commissioning_sensor(
        soil_measurement_supported,
        soil_secondary_values_present,
        soil_signature_read,
        soil_signature_present,
        slave_id == 3);
    if (slave_id == 3)
    {
        *identification_basis = "reserved_par_address_3";
    }
    else if (!soil_measurement_supported)
    {
        *identification_basis = "single_register_response_only";
    }
    else if (soil_signature_read && soil_signature_present)
    {
        *identification_basis = "nonzero_soil_signature_registers";
    }
    else if (soil_secondary_values_present)
    {
        *identification_basis = "nonzero_secondary_measurements";
    }
    else
    {
        *identification_basis = "single_measurement_values_only";
    }
    append_sensor_communication_log(
        "[IDENTIFY] id=%u automatic_type=%s confidence=%s basis=%s\n",
        static_cast<unsigned int>(slave_id),
        sensor_type_key(identification->type),
        fgt::sensor_identification_confidence_name(
            identification->confidence),
        *identification_basis);

    *reading = {};
    reading->communication_ok = true;
    if (identification->type == fgt::CommissioningSensorType::soil)
    {
        memcpy(reading->values, soil_values, sizeof(soil_values));
        reading->values_plausible =
            fgt::soil_measurement_values_plausible(
                reading->values[0], reading->values[1], reading->values[3]);
    }
    else
    {
        reading->values[0] = primary_value;
        reading->values_plausible = true;
    }
    return true;
}

const char *auto_detection_state_name()
{
    switch (s_auto_detection.phase)
    {
    case AutoDetectionPhase::power_settle:
    case AutoDetectionPhase::scanning:
        return "running";
    case AutoDetectionPhase::complete:
        return "complete";
    case AutoDetectionPhase::failed:
        return "failed";
    case AutoDetectionPhase::cancelled:
        return "cancelled";
    case AutoDetectionPhase::idle:
        return "idle";
    }
    return "idle";
}

void add_auto_detection_json(JsonDocument &doc)
{
    const size_t total_steps =
        sizeof(kAutoScanBauds) / sizeof(kAutoScanBauds[0]) *
        kAutoScanMaxId;
    size_t completed_steps =
        static_cast<size_t>(s_auto_detection.baud_index) *
            kAutoScanMaxId +
        static_cast<size_t>(s_auto_detection.next_id - 1);
    if (s_auto_detection.phase == AutoDetectionPhase::complete)
    {
        completed_steps = total_steps;
    }

    doc["ok"] =
        s_auto_detection.phase != AutoDetectionPhase::failed &&
        s_auto_detection.phase != AutoDetectionPhase::cancelled;
    doc["state"] = auto_detection_state_name();
    doc["completed_steps"] = completed_steps;
    doc["total_steps"] = total_steps;
    doc["found"] = s_auto_detection.sensor_count;
    doc["passed"] = s_auto_detection.passed_count;
    doc["test_pass"] =
        s_auto_detection.phase == AutoDetectionPhase::complete &&
        s_auto_detection.sensor_count > 0 &&
        s_auto_detection.passed_count == s_auto_detection.sensor_count;
    doc["elapsed_ms"] =
        s_auto_detection.started_ms == 0
            ? 0
            : millis() - s_auto_detection.started_ms;

    JsonArray sensors = doc["sensors"].to<JsonArray>();
    for (size_t i = 0; i < s_auto_detection.sensor_count; ++i)
    {
        const DetectedSensor &detected = s_auto_detection.sensors[i];
        JsonObject sensor = sensors.add<JsonObject>();
        add_sensor_json(sensor,
                        detected.identification.type,
                        detected.identification.confidence,
                        detected.identification_basis,
                        detected.slave_id,
                        detected.baud,
                        detected.reading);
    }
    doc["communication_log"] =
        s_auto_detection.communication_log;
    doc["communication_log_truncated"] =
        s_auto_detection.communication_log_truncated;

    if (s_auto_detection.phase == AutoDetectionPhase::complete &&
        s_auto_detection.sensor_count == 0)
    {
        doc["message"] =
            "No supported sensor responded. Duplicate addresses can also cause CRC errors or no response.";
    }
    else if (s_auto_detection.phase == AutoDetectionPhase::failed)
    {
        doc["code"] = "rs485_not_ready";
        doc["message"] = "Failed to initialize RS485 during automatic detection.";
    }
    else if (s_auto_detection.phase == AutoDetectionPhase::cancelled)
    {
        doc["message"] = "Automatic sensor detection was cancelled.";
    }
}

void handle_sensor_detect(AsyncWebServerRequest *request)
{
    if (reject_during_firmware_update(request))
    {
        return;
    }
    if (!take_operation(pdMS_TO_TICKS(100)))
    {
        send_error(request, 409, "busy",
                   "Another commissioning operation is running.");
        return;
    }
    if (auto_detection_running())
    {
        release_operation();
        send_error(request, 409, "sensor_detection_running",
                   "Automatic sensor detection is already running.");
        return;
    }
    const fgt::CommissioningSwitchSnapshot output =
        s_interlock.snapshot(millis());
    if (output.active_channel >= 0)
    {
        release_operation();
        send_error(request, 409, "output_active",
                   "Turn every MOSFET output off before testing sensors.");
        return;
    }
    if (!s_sensor_power_ready)
    {
        release_operation();
        send_error(request, 503, "sensor_power_not_ready",
                   "RS485 sensor power GPIO is not ready.");
        return;
    }

    const bool power_was_on =
        hal_power_switch_enabled(&s_commissioning_sensor_power);
    if (!power_was_on &&
        !hal_power_switch_set(&s_commissioning_sensor_power, true))
    {
        release_operation();
        send_error(request, 500, "sensor_power_failed",
                   "Failed to turn the RS485 sensor 12 V power on.");
        return;
    }

    reset_auto_detection();
    s_auto_detection.phase = power_was_on
                                 ? AutoDetectionPhase::scanning
                                 : AutoDetectionPhase::power_settle;
    s_auto_detection.started_ms = millis();
    s_auto_detection.power_ready_ms =
        s_auto_detection.started_ms +
        (power_was_on ? 0 : kSensorPowerSettleMs);
    append_sensor_communication_log(
        "# FGT RS485 sensor communication log\n"
        "firmware_version=%s firmware_build_id=%s\n"
        "scan_bauds=[4800,2400,9600] scan_ids=1-10 "
        "par_reserved_id=3\n"
        "NO_VALID_RESPONSE=timeout_or_crc_or_exception_or_malformed\n",
        APP_FIRMWARE_VERSION,
        APP_FIRMWARE_BUILD_ID);
    JsonDocument doc;
    add_auto_detection_json(doc);
    release_operation();
    send_json(request, 202, doc);
}

void handle_sensor_detect_status(AsyncWebServerRequest *request)
{
    if (!take_operation(pdMS_TO_TICKS(10)))
    {
        send_error(request, 409, "busy",
                   "Automatic sensor detection is processing one address.");
        return;
    }
    JsonDocument doc;
    add_auto_detection_json(doc);
    release_operation();
    send_json(request, 200, doc);
}

void auto_detection_tick(uint32_t now_ms)
{
    if (s_auto_detection.phase == AutoDetectionPhase::power_settle)
    {
        if (static_cast<int32_t>(
                now_ms - s_auto_detection.power_ready_ms) < 0)
        {
            return;
        }
        s_auto_detection.phase = AutoDetectionPhase::scanning;
    }
    if (s_auto_detection.phase != AutoDetectionPhase::scanning)
    {
        return;
    }

    const size_t baud_count =
        sizeof(kAutoScanBauds) / sizeof(kAutoScanBauds[0]);
    if (s_auto_detection.baud_index >= baud_count)
    {
        s_auto_detection.phase = AutoDetectionPhase::complete;
        return;
    }
    const uint32_t baud =
        kAutoScanBauds[s_auto_detection.baud_index];
    if (s_auto_detection.next_id == 1 &&
        !ensure_rs485_baud(baud))
    {
        append_sensor_communication_log(
            "[SETUP] baud=%lu result=RS485_INIT_FAILED\n",
            static_cast<unsigned long>(baud));
        s_auto_detection.phase = AutoDetectionPhase::failed;
        return;
    }

    fgt::SensorIdentification identification = {};
    CommissioningSensorReading reading = {};
    const char *identification_basis = "unknown";
    const uint8_t id = s_auto_detection.next_id;
    if (identify_sensor(
            id,
            &identification,
            &reading,
            &identification_basis) &&
        s_auto_detection.sensor_count <
            sizeof(s_auto_detection.sensors) /
                sizeof(s_auto_detection.sensors[0]))
    {
        DetectedSensor &detected =
            s_auto_detection.sensors[s_auto_detection.sensor_count++];
        detected.identification = identification;
        detected.reading = reading;
        detected.slave_id = id;
        detected.baud = baud;
        detected.identification_basis = identification_basis;
        if (reading.communication_ok && reading.values_plausible)
        {
            ++s_auto_detection.passed_count;
        }
        Serial.printf(
            "FGT commissioning sensor detected: model=%s id=%u baud=%lu confidence=%s\n",
            sensor_model_name(identification.type),
            static_cast<unsigned int>(id),
            static_cast<unsigned long>(baud),
            fgt::sensor_identification_confidence_name(
                identification.confidence));
    }

    ++s_auto_detection.next_id;
    if (s_auto_detection.next_id > kAutoScanMaxId)
    {
        s_auto_detection.next_id = 1;
        ++s_auto_detection.baud_index;
        if (s_auto_detection.baud_index >= baud_count)
        {
            s_auto_detection.phase = AutoDetectionPhase::complete;
            append_sensor_communication_log(
                "[COMPLETE] found=%u passed=%u elapsed_ms=%lu\n",
                static_cast<unsigned int>(
                    s_auto_detection.sensor_count),
                static_cast<unsigned int>(
                    s_auto_detection.passed_count),
                static_cast<unsigned long>(
                    millis() - s_auto_detection.started_ms));
            Serial.printf(
                "FGT commissioning sensor detection complete: found=%u passed=%u elapsed=%lu ms\n",
                static_cast<unsigned int>(
                    s_auto_detection.sensor_count),
                static_cast<unsigned int>(
                    s_auto_detection.passed_count),
                static_cast<unsigned long>(
                    millis() - s_auto_detection.started_ms));
        }
    }
}

const char *registry_error_message(fgt::Rs485RegistryResult result)
{
    switch (result)
    {
    case fgt::Rs485RegistryResult::duplicate_address:
        return "The same Modbus address and baud rate are already registered.";
    case fgt::Rs485RegistryResult::full:
        return "The maximum number of RS485 devices is already registered.";
    case fgt::Rs485RegistryResult::not_found:
        return "The registered RS485 device was not found.";
    case fgt::Rs485RegistryResult::storage_error:
        return "The RS485 device configuration could not be saved to flash.";
    case fgt::Rs485RegistryResult::invalid:
        return "The RS485 device configuration is invalid.";
    case fgt::Rs485RegistryResult::ok:
        return "";
    }
    return "The RS485 device configuration is invalid.";
}

int registry_result_status(fgt::Rs485RegistryResult result)
{
    switch (result)
    {
    case fgt::Rs485RegistryResult::duplicate_address:
    case fgt::Rs485RegistryResult::full:
        return 409;
    case fgt::Rs485RegistryResult::not_found:
        return 404;
    case fgt::Rs485RegistryResult::storage_error:
        return 500;
    case fgt::Rs485RegistryResult::invalid:
        return 400;
    case fgt::Rs485RegistryResult::ok:
        return 200;
    }
    return 400;
}

void send_registry_result(
    AsyncWebServerRequest *request,
    fgt::Rs485RegistryResult result,
    const char *automatic_sensor_type = nullptr,
    const char *registered_sensor_type = nullptr)
{
    JsonDocument doc;
    doc["ok"] = result == fgt::Rs485RegistryResult::ok;
    doc["code"] = fgt::rs485_registry_result_name(result);
    if (result != fgt::Rs485RegistryResult::ok)
    {
        doc["message"] = registry_error_message(result);
        if (result == fgt::Rs485RegistryResult::storage_error)
        {
            doc["storage_detail"] =
                app_fgt_rs485_devices_last_storage_error();
        }
    }
    if (automatic_sensor_type != nullptr &&
        registered_sensor_type != nullptr)
    {
        doc["automatic_sensor_type"] =
            automatic_sensor_type;
        doc["registered_sensor_type"] =
            registered_sensor_type;
        doc["manual_override"] =
            strcmp(
                automatic_sensor_type,
                registered_sensor_type) != 0;
        doc["communication_log"] =
            s_auto_detection.communication_log;
    }
    send_json(request, registry_result_status(result), doc);
}

void handle_configured_devices_get(AsyncWebServerRequest *request)
{
    if (!take_operation())
    {
        send_error(request, 409, "busy",
                   "Another commissioning operation is running.");
        return;
    }
    JsonDocument doc;
    doc["ok"] = true;
    add_configured_devices_json(doc);
    release_operation();
    send_json(request, 200, doc);
}

void handle_configured_device_register(
    AsyncWebServerRequest *request)
{
    if (reject_during_firmware_update(request))
    {
        return;
    }
    uint32_t sensor_index = 0;
    fgt::CommissioningSensorType selected_type =
        fgt::CommissioningSensorType::par;
    char name[fgt::kRs485DeviceNameSize] = {};
    char location[fgt::kRs485DeviceLocationSize] = {};
    if (!parse_uint(
            request, "sensor_index", 0,
            fgt::kMaxRs485Devices - 1, &sensor_index) ||
        !parse_sensor_type(request, &selected_type) ||
        !parse_text(request, "name", name, sizeof(name), true) ||
        !parse_text(
            request, "location", location, sizeof(location), true))
    {
        send_error(request, 400, "invalid_request",
                   "Sensor name and connection location are required.");
        return;
    }
    if (!take_operation(pdMS_TO_TICKS(100)))
    {
        send_error(request, 409, "busy",
                   "Another commissioning operation is running.");
        return;
    }
    if (s_auto_detection.phase != AutoDetectionPhase::complete ||
        s_auto_detection.sensor_count != 1 ||
        sensor_index != 0 ||
        !s_auto_detection.sensors[0].reading.communication_ok)
    {
        release_operation();
        send_error(
            request, 409, "single_sensor_required",
            "Connect and successfully detect exactly one sensor before registration.");
        return;
    }

    const DetectedSensor &detected =
        s_auto_detection.sensors[sensor_index];
    append_sensor_communication_log(
        "[REGISTER] automatic_type=%s selected_type=%s "
        "manual_override=%s\n",
        sensor_type_key(detected.identification.type),
        sensor_type_key(selected_type),
        detected.identification.type == selected_type
            ? "false"
            : "true");
    if (!ensure_rs485_baud(detected.baud))
    {
        release_operation();
        send_sensor_communication_error(
            request, 500, "rs485_not_ready",
            "Failed to initialize RS485 for the selected sensor type.");
        return;
    }
    CommissioningSensorReading selected_reading = {};
    if (!read_sensor_measurement(
            selected_type,
            detected.slave_id,
            &selected_reading) ||
        !selected_reading.communication_ok)
    {
        release_operation();
        send_sensor_communication_error(
            request, 502, "selected_sensor_type_no_response",
            "The sensor did not answer the measurement read for the selected type.");
        return;
    }
    if (!selected_reading.values_plausible)
    {
        release_operation();
        send_sensor_communication_error(
            request, 422, "selected_sensor_type_values_out_of_range",
            "The sensor answered, but the values are outside the selected sensor type range.");
        return;
    }

    fgt::Rs485DeviceConfig device = {};
    device.enabled = true;
    device.type = registry_device_type(
        selected_type);
    device.slave_id = detected.slave_id;
    device.baud = detected.baud;
    device.function_code = 0x03;
    device.start_register = 0;
    device.register_count =
        device.type == fgt::Rs485DeviceType::soil ? 7 : 1;
    device.scale = 1.0F;
    memcpy(device.name, name, sizeof(device.name));
    memcpy(device.location, location, sizeof(device.location));

    s_registration_stack_before_bytes =
        static_cast<uint32_t>(
            uxTaskGetStackHighWaterMark(nullptr));
    s_registration_stack_after_bytes = 0;
    s_registration_heap_before_bytes = ESP.getFreeHeap();
    s_registration_heap_after_bytes = 0;
    s_registration_sensor_id = device.slave_id;
    s_registration_sensor_baud = device.baud;
    s_registration_last_result = "running";
    s_registration_interrupted = false;
    s_registration_reset_marker.magic =
        kRegistrationDiagnosticMagic;
    s_registration_reset_marker.slave_id =
        device.slave_id;
    s_registration_reset_marker.baud =
        device.baud;
    s_registration_reset_marker.stack_low_water_mark_bytes =
        s_registration_stack_before_bytes;
    s_registration_reset_marker.free_heap_bytes =
        s_registration_heap_before_bytes;
    s_registration_reset_marker.active = 1;
    Serial.printf(
        "FGT sensor registration start: id=%u baud=%lu "
        "stack_low_water=%lu heap_free=%lu registry_store=%u\n",
        static_cast<unsigned int>(device.slave_id),
        static_cast<unsigned long>(device.baud),
        static_cast<unsigned long>(
            s_registration_stack_before_bytes),
        static_cast<unsigned long>(
            s_registration_heap_before_bytes),
        static_cast<unsigned int>(
            app_fgt_rs485_devices_registry_size()));

    const fgt::Rs485RegistryResult result =
        app_fgt_rs485_devices_add(device);
    s_registration_stack_after_bytes =
        static_cast<uint32_t>(
            uxTaskGetStackHighWaterMark(nullptr));
    s_registration_heap_after_bytes = ESP.getFreeHeap();
    s_registration_last_result =
        fgt::rs485_registry_result_name(result);
    s_registration_reset_marker.active = 0;
    Serial.printf(
        "FGT sensor registration result: result=%s "
        "storage=%s stack_low_water=%lu heap_free=%lu\n",
        s_registration_last_result,
        app_fgt_rs485_devices_last_storage_error(),
        static_cast<unsigned long>(
            s_registration_stack_after_bytes),
        static_cast<unsigned long>(
            s_registration_heap_after_bytes));
    release_operation();
    send_registry_result(
        request,
        result,
        sensor_type_key(detected.identification.type),
        sensor_type_key(selected_type));
}

void handle_configured_device_update(
    AsyncWebServerRequest *request)
{
    if (reject_during_firmware_update(request))
    {
        return;
    }
    uint32_t index = 0;
    uint32_t enabled = 0;
    char name[fgt::kRs485DeviceNameSize] = {};
    char location[fgt::kRs485DeviceLocationSize] = {};
    if (!parse_uint(
            request, "index", 0,
            fgt::kMaxRs485Devices - 1, &index) ||
        !parse_uint(request, "enabled", 0, 1, &enabled) ||
        !parse_text(request, "name", name, sizeof(name), true) ||
        !parse_text(
            request, "location", location, sizeof(location), true))
    {
        send_error(request, 400, "invalid_request",
                   "Registered sensor name and connection location are required.");
        return;
    }
    if (!take_operation())
    {
        send_error(request, 409, "busy",
                   "Another commissioning operation is running.");
        return;
    }
    const fgt::Rs485DeviceRegistry &registry =
        app_fgt_rs485_devices_get();
    if (index >= registry.count)
    {
        release_operation();
        send_registry_result(
            request, fgt::Rs485RegistryResult::not_found);
        return;
    }
    fgt::Rs485DeviceConfig device = registry.devices[index];
    device.enabled = enabled != 0;
    memcpy(device.name, name, sizeof(device.name));
    memcpy(device.location, location, sizeof(device.location));
    const fgt::Rs485RegistryResult result =
        app_fgt_rs485_devices_update(index, device);
    release_operation();
    send_registry_result(request, result);
}

void handle_configured_device_remove(
    AsyncWebServerRequest *request)
{
    if (reject_during_firmware_update(request))
    {
        return;
    }
    uint32_t index = 0;
    if (!parse_uint(
            request, "index", 0,
            fgt::kMaxRs485Devices - 1, &index))
    {
        send_error(request, 400, "invalid_request",
                   "Select a registered sensor to remove.");
        return;
    }
    if (!take_operation())
    {
        send_error(request, 409, "busy",
                   "Another commissioning operation is running.");
        return;
    }
    const fgt::Rs485RegistryResult result =
        app_fgt_rs485_devices_remove(index);
    release_operation();
    send_registry_result(request, result);
}

void handle_sensor_test(AsyncWebServerRequest *request)
{
    if (reject_during_firmware_update(request))
    {
        return;
    }
    uint32_t slave_id = 0;
    uint32_t baud = 0;
    fgt::CommissioningSensorType type = {};
    if (!parse_sensor_type(request, &type) ||
        !parse_uint(request, "slave_id", 1, 247, &slave_id) ||
        !parse_uint(request, "baud", 2400, 9600, &baud) ||
        !baud_supported(baud))
    {
        send_error(request, 400, "invalid_request",
                   "Select an automatically detected sensor.");
        return;
    }
    if (!take_operation(pdMS_TO_TICKS(100)))
    {
        send_error(request, 409, "busy",
                   "Another commissioning operation is running.");
        return;
    }
    if (!prepare_sensor_operation(request))
    {
        release_operation();
        return;
    }
    if (!ensure_rs485_baud(baud))
    {
        release_operation();
        send_error(request, 500, "rs485_not_ready",
                   "Failed to initialize RS485 for the detected sensor.");
        return;
    }

    CommissioningSensorReading reading = {};
    read_sensor_measurement(type, static_cast<uint8_t>(slave_id), &reading);
    JsonDocument doc;
    doc["ok"] = true;
    JsonObject sensor = doc["sensor"].to<JsonObject>();
    add_sensor_json(sensor,
                    type,
                    parse_identification_confidence(request),
                    "manual_retest",
                    static_cast<uint8_t>(slave_id),
                    baud,
                    reading);
    doc["communication_log"] =
        s_auto_detection.communication_log;
    release_operation();
    send_json(request, 200, doc);
}

void handle_modbus_change_address(AsyncWebServerRequest *request)
{
    if (reject_during_firmware_update(request))
    {
        return;
    }
    uint32_t baud = 0;
    uint32_t old_id = 0;
    uint32_t new_id = 0;
    uint32_t registry_index = 255;
    uint32_t confirmed = 0;
    fgt::CommissioningSensorType type = {};
    if (!parse_sensor_type(request, &type) ||
        !parse_uint(request, "baud", 2400, 9600, &baud) ||
        !baud_supported(baud) ||
        !parse_uint(request, "old_id", 1, 247, &old_id) ||
        !parse_uint(request, "new_id", 1, kAutoScanMaxId, &new_id) ||
        !parse_uint(
            request, "registry_index", 0, 255,
            &registry_index) ||
        !parse_uint(request, "single_device_confirmed", 1, 1, &confirmed) ||
        old_id == new_id)
    {
        send_error(request, 400, "invalid_request",
                   "Select one detected sensor and provide a different new address from 1 to 10.");
        return;
    }
    if (!take_operation(pdMS_TO_TICKS(100)))
    {
        send_error(request, 409, "busy", "Another commissioning operation is running.");
        return;
    }
    if (!prepare_sensor_operation(request))
    {
        release_operation();
        return;
    }
    if (!ensure_rs485_baud(baud))
    {
        release_operation();
        send_error(request, 500, "rs485_not_ready",
                   "Failed to initialize RS485 for the selected sensor.");
        return;
    }

    const fgt::Rs485DeviceRegistry &registry =
        app_fgt_rs485_devices_get();
    int registered_index = -1;
    if (registry_index != 255)
    {
        if (registry_index >= registry.count)
        {
            release_operation();
            send_error(
                request, 404, "registered_sensor_not_found",
                "The selected registered sensor configuration was not found.");
            return;
        }
        const fgt::Rs485DeviceConfig &registered =
            registry.devices[registry_index];
        if (registered.type != registry_device_type(type) ||
            registered.baud != baud ||
            registered.slave_id != old_id)
        {
            release_operation();
            send_error(
                request, 409, "registered_sensor_mismatch",
                "The detected sensor does not match the selected registered configuration.");
            return;
        }
        registered_index = static_cast<int>(registry_index);
    }
    const int conflicting_index = fgt::rs485_registry_find_address(
        registry,
        baud,
        static_cast<uint8_t>(new_id),
        registered_index);
    if (conflicting_index >= 0)
    {
        release_operation();
        send_error(
            request, 409, "duplicate_address",
            "The new Modbus address is already assigned to a registered sensor at the same baud rate.");
        return;
    }

    uint16_t current_id = 0;
    const bool precheck_ok = read_sensor_registers_with_log(
        static_cast<uint8_t>(old_id),
        0x03,
        kSensorAddressRegister,
        1,
        &current_id,
        1);
    if (!precheck_ok || current_id != old_id)
    {
        release_operation();
        JsonDocument doc;
        doc["ok"] = false;
        doc["code"] = "precheck_failed";
        doc["message"] =
            "Address register could not be read or did not match the current slave ID. Nothing was written.";
        doc["read_value"] = current_id;
        doc["communication_log"] =
            s_auto_detection.communication_log;
        send_json(request, 409, doc);
        return;
    }

    const bool write_echo_ok = hal_rs485_modbus_write_single_register(
        static_cast<uint8_t>(old_id),
        kSensorAddressRegister,
        static_cast<uint16_t>(new_id));
    ++s_auto_detection.communication_transaction_count;
    append_sensor_communication_log(
        "[%03u] baud=%lu id=%u FC06 reg=0x%04X value=%u result=%s\n",
        static_cast<unsigned int>(
            s_auto_detection.communication_transaction_count),
        static_cast<unsigned long>(s_rs485_baud),
        static_cast<unsigned int>(old_id),
        static_cast<unsigned int>(kSensorAddressRegister),
        static_cast<unsigned int>(new_id),
        write_echo_ok ? "ECHO_OK" : "NO_VALID_ECHO");
    if (!write_echo_ok)
    {
        release_operation();
        JsonDocument doc;
        doc["ok"] = false;
        doc["code"] = "write_unconfirmed";
        doc["message"] =
            "FC06 echo was not verified. The write result is unknown and was not retried.";
        doc["communication_log"] =
            s_auto_detection.communication_log;
        send_json(request, 502, doc);
        return;
    }

    delay(kAddressChangeVerifyDelayMs);
    uint16_t verified_id = 0;
    const bool verification_ok = read_sensor_registers_with_log(
        static_cast<uint8_t>(new_id),
        0x03,
        kSensorAddressRegister,
        1,
        &verified_id,
        1);
    CommissioningSensorReading reading = {};
    if (verification_ok && verified_id == new_id)
    {
        read_sensor_measurement(
            type, static_cast<uint8_t>(new_id), &reading);
    }
    fgt::Rs485RegistryResult registry_update_result =
        fgt::Rs485RegistryResult::ok;
    bool registry_updated = false;
    if (verification_ok && verified_id == new_id &&
        registered_index >= 0)
    {
        fgt::Rs485DeviceConfig registered =
            registry.devices[registered_index];
        registered.slave_id = static_cast<uint8_t>(new_id);
        registry_update_result = app_fgt_rs485_devices_update(
            static_cast<size_t>(registered_index), registered);
        registry_updated =
            registry_update_result == fgt::Rs485RegistryResult::ok;
    }
    release_operation();

    JsonDocument doc;
    const bool physical_change_verified =
        verification_ok && verified_id == new_id;
    const bool configuration_saved =
        registered_index < 0 || registry_updated;
    doc["ok"] =
        physical_change_verified && configuration_saved;
    doc["old_id"] = old_id;
    doc["new_id"] = new_id;
    doc["baud"] = baud;
    doc["sensor_name"] = sensor_display_name(type);
    doc["model"] = sensor_model_name(type);
    doc["write_echo_ok"] = write_echo_ok;
    doc["verification_ok"] = verification_ok && verified_id == new_id;
    doc["verified_value"] = verified_id;
    doc["registered_sensor"] = registered_index >= 0;
    doc["configuration_saved"] = configuration_saved;
    doc["communication_log"] =
        s_auto_detection.communication_log;
    if (doc["verification_ok"].as<bool>())
    {
        JsonObject sensor = doc["sensor"].to<JsonObject>();
        add_sensor_json(sensor,
                        type,
                        parse_identification_confidence(request),
                        "manual_address_change",
                        static_cast<uint8_t>(new_id),
                        baud,
                        reading);
    }
    if (!physical_change_verified)
    {
        doc["code"] = "verification_failed";
        doc["message"] =
            "FC06 echo was valid, but the new ID could not be verified. The write was not retried.";
    }
    else if (!configuration_saved)
    {
        doc["code"] =
            fgt::rs485_registry_result_name(registry_update_result);
        doc["message"] =
            "The sensor address changed, but the saved device configuration could not be updated. Detect and register the sensor again before normal operation.";
    }
    send_json(
        request,
        doc["ok"].as<bool>()
            ? 200
            : (physical_change_verified ? 500 : 502),
        doc);
}

void commissioning_begin()
{
    s_portal_reset_reason = esp_reset_reason();
    s_registration_interrupted =
        s_registration_reset_marker.magic ==
            kRegistrationDiagnosticMagic &&
        s_registration_reset_marker.active == 1;
    if (s_registration_interrupted)
    {
        s_registration_sensor_id =
            s_registration_reset_marker.slave_id;
        s_registration_sensor_baud =
            s_registration_reset_marker.baud;
        s_registration_stack_before_bytes =
            s_registration_reset_marker
                .stack_low_water_mark_bytes;
        s_registration_heap_before_bytes =
            s_registration_reset_marker.free_heap_bytes;
        s_registration_stack_after_bytes = 0;
        s_registration_heap_after_bytes = 0;
        s_registration_last_result =
            "interrupted_by_reset";
        Serial.printf(
            "FGT previous sensor registration was interrupted: "
            "reset=%s id=%lu baud=%lu stack_low_water=%lu "
            "heap_free=%lu\n",
            reset_reason_name(s_portal_reset_reason),
            static_cast<unsigned long>(
                s_registration_sensor_id),
            static_cast<unsigned long>(
                s_registration_sensor_baud),
            static_cast<unsigned long>(
                s_registration_stack_before_bytes),
            static_cast<unsigned long>(
                s_registration_heap_before_bytes));
    }
    s_registration_reset_marker.magic =
        kRegistrationDiagnosticMagic;
    s_registration_reset_marker.active = 0;
    app_fgt_rs485_devices_init();
    hal_rs485_modbus_set_diagnostics(true);
    Serial.println(
        "FGT RS485 wiring: D6/GPIO16/TX->module RXD "
        "D7/GPIO17/RX<-module TXD D8/GPIO19->EN");
    if (s_operation_mutex == nullptr)
    {
        s_operation_mutex = xSemaphoreCreateMutex();
    }
    s_interlock = fgt::CommissioningInterlock(
        APP_FGT_COMMISSIONING_SWITCH_GUARD_MS,
        APP_FGT_COMMISSIONING_MAX_ON_MS);
    reset_auto_detection();
    s_io_ready = hal_direct_gpio_open(&s_commissioning_io);
    if (s_io_ready)
    {
        hal_direct_gpio_all_outputs_off(&s_commissioning_io);
    }

    const hal_power_switch_config_t power_config = hal_power_switch_default_config();
    s_sensor_power_ready =
        hal_power_switch_open(&s_commissioning_sensor_power, &power_config);
    if (s_sensor_power_ready)
    {
        hal_power_switch_set(&s_commissioning_sensor_power, false);
    }

    s_rs485_ready = ensure_rs485_baud(APP_RS485_BAUD);
    s_rs485_internal_loopback_ok =
        s_rs485_ready &&
        hal_rs485_modbus_internal_loopback_test();
    app_fgt_local_update_init(
        prepare_local_firmware_update);
    Serial.printf("FGT commissioning portal ready: io=%s sensor_power=%s rs485=%s guard=%lu max_on=%lu\n",
                  s_io_ready ? "true" : "false",
                  s_sensor_power_ready ? "true" : "false",
                  s_rs485_ready ? "true" : "false",
                  static_cast<unsigned long>(APP_FGT_COMMISSIONING_SWITCH_GUARD_MS),
                  static_cast<unsigned long>(APP_FGT_COMMISSIONING_MAX_ON_MS));
}

void commissioning_register_routes(AsyncWebServer *server)
{
    if (server == nullptr)
    {
        return;
    }
    server->on("/fgt/commissioning", HTTP_GET, [](AsyncWebServerRequest *request)
               { request->send(200, "text/html; charset=utf-8", kCommissioningPage); });
    server->on("/api/fgt/commissioning/status", HTTP_GET, handle_status);
    server->on("/api/fgt/commissioning/output", HTTP_POST, handle_output_on);
    server->on("/api/fgt/commissioning/all-off", HTTP_POST, handle_all_off);
    server->on("/api/fgt/commissioning/sensor-power", HTTP_POST, handle_sensor_power);
    server->on("/api/fgt/commissioning/rs485/ttl-loopback",
               HTTP_POST,
               handle_rs485_ttl_loopback);
    server->on("/api/fgt/commissioning/devices",
               HTTP_GET,
               handle_configured_devices_get);
    server->on("/api/fgt/commissioning/devices/register",
               HTTP_POST,
               handle_configured_device_register);
    server->on("/api/fgt/commissioning/devices/update",
               HTTP_POST,
               handle_configured_device_update);
    server->on("/api/fgt/commissioning/devices/remove",
               HTTP_POST,
               handle_configured_device_remove);
    server->on("/api/fgt/commissioning/sensors/detect",
               HTTP_POST,
               handle_sensor_detect);
    server->on("/api/fgt/commissioning/sensors/detect/status",
               HTTP_GET,
               handle_sensor_detect_status);
    server->on("/api/fgt/commissioning/sensors/test",
               HTTP_POST,
               handle_sensor_test);
    server->on("/api/fgt/commissioning/modbus/change-address",
               HTTP_POST,
               handle_modbus_change_address);
    app_fgt_local_update_register_routes(server);
}

void commissioning_loop()
{
    if (take_operation(0))
    {
        if (s_interlock.tick(millis()) && s_io_ready)
        {
            hal_direct_gpio_all_outputs_off(&s_commissioning_io);
            Serial.println("FGT commissioning output auto-OFF");
        }
        if (app_fgt_local_update_busy())
        {
            cancel_auto_detection();
            if (s_io_ready)
            {
                hal_direct_gpio_all_outputs_off(
                    &s_commissioning_io);
            }
            s_interlock.request_off(millis());
            if (s_sensor_power_ready)
            {
                hal_power_switch_set(
                    &s_commissioning_sensor_power,
                    false);
            }
        }
        else
        {
            auto_detection_tick(millis());
        }
        release_operation();
    }
    app_fgt_local_update_loop();
}

void commissioning_end()
{
    app_fgt_local_update_end();
    if (s_io_ready)
    {
        hal_direct_gpio_all_outputs_off(&s_commissioning_io);
    }
    s_interlock.request_off(millis());
    reset_auto_detection();
    if (s_sensor_power_ready)
    {
        hal_power_switch_set(&s_commissioning_sensor_power, false);
        hal_power_switch_close(&s_commissioning_sensor_power);
    }
    hal_rs485_modbus_deinit();
    hal_rs485_modbus_set_diagnostics(false);
    hal_direct_gpio_close(&s_commissioning_io);
    s_io_ready = false;
    s_sensor_power_ready = false;
    s_rs485_ready = false;
    s_rs485_baud = 0;
}

} // namespace

void app_fgt_commissioning_register_setup_portal()
{
    static const app_initial_setting_extension_t extension = {
        "FGT 出荷動作確認",
        "MOSFET出力、RS485データ取得、Modbusアドレス設定を確認します。",
        "/fgt/commissioning",
        commissioning_begin,
        commissioning_register_routes,
        commissioning_loop,
        commissioning_end,
    };
    app_initial_setting_set_extension(&extension);
}
