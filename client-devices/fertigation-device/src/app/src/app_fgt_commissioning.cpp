#include "app_fgt_commissioning.h"

#include <Arduino.h>
#include <ArduinoJson.h>
#include <ESPAsyncWebServer.h>
#include <errno.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <stdlib.h>

#include "app_initial_setting.h"
#include "fgt_commissioning_interlock.h"
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
constexpr uint8_t kMaxScanCount = 32;
constexpr uint32_t kAddressChangeVerifyDelayMs = 500;

const char *const kOutputLabels[] = {
    "給水",
    "A液",
    "B液",
    "攪拌",
    "潅水",
};

hal_direct_gpio_t s_commissioning_io = {};
hal_power_switch_t s_commissioning_sensor_power = {};
bool s_io_ready = false;
bool s_sensor_power_ready = false;
bool s_rs485_ready = false;
uint32_t s_rs485_baud = 0;
SemaphoreHandle_t s_operation_mutex = nullptr;
fgt::CommissioningInterlock s_interlock(APP_FGT_COMMISSIONING_SWITCH_GUARD_MS,
                                        APP_FGT_COMMISSIONING_MAX_ON_MS);

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
    pre{white-space:pre-wrap;overflow-wrap:anywhere;min-height:90px;background:#0f1720;color:#d7f7e9;border-radius:8px;padding:12px;font-size:13px}
    @media(max-width:760px){.grid{grid-template-columns:1fr}.outputs{grid-template-columns:repeat(2,1fr)}.row{grid-template-columns:repeat(2,1fr)}}
  </style>
</head>
<body><main>
  <a class="back" href="/">← 接続設定へ戻る</a>
  <h1>FGT 出荷動作確認</h1>
  <p>初期配線、MOSFET出力、RS485 ModbusセンサーをAPモードで確認します。</p>
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
      </div>
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

    <section class="card">
      <h2>RS485センサー電源</h2>
      <p>D9 / GPIO20の高側スイッチENを操作します。</p>
      <div class="actions">
        <button onclick="sensorPower(true)">12V ON</button>
        <button class="secondary" onclick="sensorPower(false)">12V OFF</button>
      </div>
    </section>

    <section class="card">
      <h2>Modbus IDスキャン</h2>
      <div class="row">
        <div><label>Baud</label><select id="scanBaud"><option>2400</option><option selected>4800</option><option>9600</option></select></div>
        <div><label>Function</label><select id="scanFunction"><option value="3">03</option><option value="4">04</option></select></div>
        <div><label>開始ID</label><input id="scanStart" type="number" min="1" max="247" value="1"></div>
        <div><label>終了ID</label><input id="scanEnd" type="number" min="1" max="247" value="10"></div>
      </div>
      <label>Probe register</label><input id="scanRegister" value="0x0000">
      <div class="actions"><button onclick="scanModbus()">スキャン</button></div>
      <p class="hint">同じIDが複数ある場合、CRCエラーや応答なしになることがあります。1回のスキャンは最大32 IDです。</p>
    </section>

    <section class="card wide">
      <h2>Modbusレジスタ読取</h2>
      <div class="row">
        <div><label>Slave ID</label><input id="readId" type="number" min="1" max="247" value="1"></div>
        <div><label>Baud</label><select id="readBaud"><option>2400</option><option selected>4800</option><option>9600</option></select></div>
        <div><label>Function</label><select id="readFunction"><option value="3">03 Holding</option><option value="4">04 Input</option></select></div>
        <div><label>Count</label><input id="readCount" type="number" min="1" max="16" value="1"></div>
      </div>
      <label>Start register</label><input id="readRegister" value="0x0000">
      <div class="actions"><button onclick="readModbus()">データ取得</button></div>
    </section>

    <section class="card wide">
      <h2>Modbusアドレス変更</h2>
      <section class="notice">
        <strong>同一アドレスの機器を複数接続したまま、1台だけ変更することはできません。</strong>
        変更対象以外のRS485機器をコネクタから外し、対象1台だけに電源が入っている状態で実行してください。
        書き込みは自動再送しません。
      </section>
      <div class="row">
        <div><label>現在のID</label><input id="oldId" type="number" min="1" max="247" value="1"></div>
        <div><label>新しいID</label><input id="newId" type="number" min="1" max="247" value="2"></div>
        <div><label>Baud</label><select id="addressBaud"><option>2400</option><option selected>4800</option><option>9600</option></select></div>
        <div><label>Address register</label><input id="addressRegister" value="0x07D0"></div>
      </div>
      <p class="hint">CWT-SOILとSEN0641のアドレスレジスタは0x07D0です。他機種では必ず取扱説明書を確認してください。</p>
      <label class="confirm"><input id="singleConfirmed" type="checkbox">変更対象のセンサー1台だけがRS485バスへ接続されていることを確認しました</label>
      <div class="actions"><button class="stop" onclick="changeAddress()">変更前読取 → FC06を1回送信 → 新IDで検証</button></div>
    </section>

    <section class="card wide">
      <h2>結果</h2>
      <pre id="result">操作結果がここに表示されます。</pre>
    </section>
  </div>
</main>
<script>
const result=document.getElementById('result');
const value=id=>document.getElementById(id).value;
function form(data){const p=new URLSearchParams();Object.entries(data).forEach(([k,v])=>p.set(k,String(v)));return p}
async function call(path,data){
  result.textContent='処理中...';
  try{
    const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:form(data)});
    const body=await response.json();
    result.textContent=JSON.stringify(body,null,2);
    await refreshStatus();
    return body;
  }catch(error){result.textContent='通信エラー: '+error;return null}
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
    document.getElementById('status').innerHTML=`<span class="pill ${s.active_output>0?'danger':'ok'}">${active}</span><span class="pill ${s.guard_remaining_ms>0?'warn':'ok'}">${guard}</span><span class="pill">${power}</span><span class="pill">RS485 ${s.rs485_ready?'ready':'not ready'} / ${s.rs485_baud}bps</span>`;
    document.querySelectorAll('[data-output]').forEach(button=>button.disabled=s.active_output>0||s.guard_remaining_ms>0||!s.io_ready);
  }catch(error){document.getElementById('status').innerHTML='<span class="pill danger">状態取得失敗</span>'}
}
function outputOn(channel){
  const seconds=Number(document.getElementById('duration').value);
  call('/api/fgt/commissioning/output',{channel,duration_ms:seconds*1000});
}
function allOff(){call('/api/fgt/commissioning/all-off',{})}
function sensorPower(on){call('/api/fgt/commissioning/sensor-power',{enabled:on?1:0})}
function scanModbus(){call('/api/fgt/commissioning/modbus/scan',{
  baud:value('scanBaud'),function:value('scanFunction'),start_id:value('scanStart'),end_id:value('scanEnd'),register:value('scanRegister')
})}
function readModbus(){call('/api/fgt/commissioning/modbus/read',{
  baud:value('readBaud'),function:value('readFunction'),slave_id:value('readId'),register:value('readRegister'),count:value('readCount')
})}
function changeAddress(){
  if(!document.getElementById('singleConfirmed').checked){result.textContent='対象センサー1台だけの接続確認が必要です。';return}
  call('/api/fgt/commissioning/modbus/change-address',{
    baud:value('addressBaud'),old_id:value('oldId'),new_id:value('newId'),address_register:value('addressRegister'),single_device_confirmed:1
  })
}
refreshStatus();setInterval(refreshStatus,500);
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

bool require_modbus_ready(AsyncWebServerRequest *request, uint32_t baud)
{
    const fgt::CommissioningSwitchSnapshot state = s_interlock.snapshot(millis());
    if (state.active_channel >= 0)
    {
        send_error(request, 409, "output_active",
                   "Turn every MOSFET output off before using RS485.");
        return false;
    }
    if (!s_sensor_power_ready ||
        !hal_power_switch_enabled(&s_commissioning_sensor_power))
    {
        send_error(request, 409, "sensor_power_off",
                   "Turn the RS485 sensor 12 V power on first.");
        return false;
    }
    if (!ensure_rs485_baud(baud))
    {
        send_error(request, 400, "invalid_baud",
                   "Supported baud rates are 2400, 4800, and 9600.");
        return false;
    }
    return true;
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
    doc["active_output"] =
        state.active_channel >= 0 ? static_cast<int>(state.active_channel) + 1 : 0;
    doc["active_output_label"] =
        state.active_channel >= 0 ? kOutputLabels[state.active_channel] : "";
    doc["active_remaining_ms"] = state.active_remaining_ms;
    doc["guard_remaining_ms"] = state.guard_remaining_ms;
    doc["guard_ms"] = APP_FGT_COMMISSIONING_SWITCH_GUARD_MS;
    doc["max_on_ms"] = APP_FGT_COMMISSIONING_MAX_ON_MS;
    release_operation();
    send_json(request, 200, doc);
}

void handle_output_on(AsyncWebServerRequest *request)
{
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

void handle_modbus_read(AsyncWebServerRequest *request)
{
    uint32_t slave_id = 0;
    uint32_t baud = 0;
    uint32_t function = 0;
    uint32_t register_address = 0;
    uint32_t count = 0;
    if (!parse_uint(request, "slave_id", 1, 247, &slave_id) ||
        !parse_uint(request, "baud", 2400, 9600, &baud) ||
        !parse_uint(request, "function", 3, 4, &function) ||
        !parse_uint(request, "register", 0, 65535, &register_address) ||
        !parse_uint(request, "count", 1, 16, &count))
    {
        send_error(request, 400, "invalid_request", "Invalid Modbus read parameters.");
        return;
    }
    if (!take_operation(pdMS_TO_TICKS(100)))
    {
        send_error(request, 409, "busy", "Another commissioning operation is running.");
        return;
    }
    if (!require_modbus_ready(request, baud))
    {
        release_operation();
        return;
    }

    uint16_t values[16] = {};
    const bool ok = hal_rs485_modbus_read_registers(
        static_cast<uint8_t>(slave_id),
        static_cast<uint8_t>(function),
        static_cast<uint16_t>(register_address),
        static_cast<uint16_t>(count),
        values,
        count);
    release_operation();

    JsonDocument doc;
    doc["ok"] = ok;
    doc["slave_id"] = slave_id;
    doc["baud"] = baud;
    doc["function"] = function;
    doc["start_register"] = register_address;
    JsonArray registers = doc["registers"].to<JsonArray>();
    if (ok)
    {
        for (uint32_t i = 0; i < count; ++i)
        {
            registers.add(values[i]);
        }
    }
    else
    {
        doc["code"] = "no_valid_response";
        doc["message"] = "No CRC-valid Modbus response was received.";
    }
    send_json(request, ok ? 200 : 504, doc);
}

void handle_modbus_scan(AsyncWebServerRequest *request)
{
    uint32_t baud = 0;
    uint32_t function = 0;
    uint32_t start_id = 0;
    uint32_t end_id = 0;
    uint32_t register_address = 0;
    if (!parse_uint(request, "baud", 2400, 9600, &baud) ||
        !parse_uint(request, "function", 3, 4, &function) ||
        !parse_uint(request, "start_id", 1, 247, &start_id) ||
        !parse_uint(request, "end_id", 1, 247, &end_id) ||
        !parse_uint(request, "register", 0, 65535, &register_address) ||
        end_id < start_id || end_id - start_id + 1 > kMaxScanCount)
    {
        send_error(request, 400, "invalid_request",
                   "Scan range must contain 1..32 IDs and use a supported baud rate.");
        return;
    }
    if (!take_operation(pdMS_TO_TICKS(100)))
    {
        send_error(request, 409, "busy", "Another commissioning operation is running.");
        return;
    }
    if (!require_modbus_ready(request, baud))
    {
        release_operation();
        return;
    }

    JsonDocument doc;
    doc["ok"] = true;
    doc["baud"] = baud;
    doc["function"] = function;
    doc["register"] = register_address;
    JsonArray devices = doc["devices"].to<JsonArray>();
    for (uint32_t id = start_id; id <= end_id; ++id)
    {
        uint16_t value = 0;
        if (hal_rs485_modbus_read_registers(
                static_cast<uint8_t>(id),
                static_cast<uint8_t>(function),
                static_cast<uint16_t>(register_address),
                1,
                &value,
                1))
        {
            JsonObject device = devices.add<JsonObject>();
            device["slave_id"] = id;
            device["value"] = value;
        }
        delay(10);
    }
    doc["found"] = devices.size();
    if (devices.size() == 0)
    {
        doc["message"] =
            "No device responded. Duplicate IDs can also appear as CRC errors or no response.";
    }
    release_operation();
    send_json(request, 200, doc);
}

void handle_modbus_change_address(AsyncWebServerRequest *request)
{
    uint32_t baud = 0;
    uint32_t old_id = 0;
    uint32_t new_id = 0;
    uint32_t address_register = 0;
    uint32_t confirmed = 0;
    if (!parse_uint(request, "baud", 2400, 9600, &baud) ||
        !parse_uint(request, "old_id", 1, 247, &old_id) ||
        !parse_uint(request, "new_id", 1, 247, &new_id) ||
        !parse_uint(request, "address_register", 0, 65535, &address_register) ||
        !parse_uint(request, "single_device_confirmed", 1, 1, &confirmed) ||
        old_id == new_id)
    {
        send_error(request, 400, "invalid_request",
                   "Confirm one connected device and provide different valid old/new IDs.");
        return;
    }
    if (!take_operation(pdMS_TO_TICKS(100)))
    {
        send_error(request, 409, "busy", "Another commissioning operation is running.");
        return;
    }
    if (!require_modbus_ready(request, baud))
    {
        release_operation();
        return;
    }

    uint16_t current_id = 0;
    const bool precheck_ok = hal_rs485_modbus_read_registers(
        static_cast<uint8_t>(old_id),
        0x03,
        static_cast<uint16_t>(address_register),
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
        send_json(request, 409, doc);
        return;
    }

    const bool write_echo_ok = hal_rs485_modbus_write_single_register(
        static_cast<uint8_t>(old_id),
        static_cast<uint16_t>(address_register),
        static_cast<uint16_t>(new_id));
    if (!write_echo_ok)
    {
        release_operation();
        JsonDocument doc;
        doc["ok"] = false;
        doc["code"] = "write_unconfirmed";
        doc["message"] =
            "FC06 echo was not verified. The write result is unknown and was not retried.";
        send_json(request, 502, doc);
        return;
    }

    delay(kAddressChangeVerifyDelayMs);
    uint16_t verified_id = 0;
    const bool verification_ok = hal_rs485_modbus_read_registers(
        static_cast<uint8_t>(new_id),
        0x03,
        static_cast<uint16_t>(address_register),
        1,
        &verified_id,
        1);
    release_operation();

    JsonDocument doc;
    doc["ok"] = verification_ok && verified_id == new_id;
    doc["old_id"] = old_id;
    doc["new_id"] = new_id;
    doc["baud"] = baud;
    doc["address_register"] = address_register;
    doc["write_echo_ok"] = write_echo_ok;
    doc["verification_ok"] = verification_ok && verified_id == new_id;
    doc["verified_value"] = verified_id;
    if (!doc["ok"].as<bool>())
    {
        doc["code"] = "verification_failed";
        doc["message"] =
            "FC06 echo was valid, but the new ID could not be verified. The write was not retried.";
    }
    send_json(request, doc["ok"].as<bool>() ? 200 : 502, doc);
}

void commissioning_begin()
{
    if (s_operation_mutex == nullptr)
    {
        s_operation_mutex = xSemaphoreCreateMutex();
    }
    s_interlock = fgt::CommissioningInterlock(
        APP_FGT_COMMISSIONING_SWITCH_GUARD_MS,
        APP_FGT_COMMISSIONING_MAX_ON_MS);
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
    server->on("/api/fgt/commissioning/modbus/read", HTTP_POST, handle_modbus_read);
    server->on("/api/fgt/commissioning/modbus/scan", HTTP_POST, handle_modbus_scan);
    server->on("/api/fgt/commissioning/modbus/change-address",
               HTTP_POST,
               handle_modbus_change_address);
}

void commissioning_loop()
{
    if (!take_operation(0))
    {
        return;
    }
    if (s_interlock.tick(millis()) && s_io_ready)
    {
        hal_direct_gpio_all_outputs_off(&s_commissioning_io);
        Serial.println("FGT commissioning output auto-OFF");
    }
    release_operation();
}

void commissioning_end()
{
    if (s_io_ready)
    {
        hal_direct_gpio_all_outputs_off(&s_commissioning_io);
    }
    s_interlock.request_off(millis());
    if (s_sensor_power_ready)
    {
        hal_power_switch_set(&s_commissioning_sensor_power, false);
        hal_power_switch_close(&s_commissioning_sensor_power);
    }
    hal_rs485_modbus_deinit();
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
