# INAS アーキテクチャ レイヤ分離ポリシー

英語版: [../ARCHITECTURE_LAYERING_POLICY.md](../ARCHITECTURE_LAYERING_POLICY.md)

## 目的

この文書は、INAS 全体のレイヤ境界を定義する。機能、device、sensor、actuator、cloud 連携、UI flow、data model を追加する前に、この境界に沿って責務を決める。

基本ルールは単純である。各レイヤは「現在それを使っている製品名」ではなく「そのレイヤが持つ責務」で名前を付ける。製品挙動は product/device orchestration に置き、再利用可能な境界は common layer に置く。

## システムレイヤ

| レイヤ | 持つもの | 持たないもの |
|---|---|---|
| Crop system orchestration | イチゴ点滴栽培などの作物別目標、target range、automation level、action approval、result evaluation | 作物 workflow ごとの巨大な単一 device type |
| Hub application | device orchestration、runtime config distribution、MQTT handling、field/device placement、measurement normalization、action plans、OTA decisions、営農者向け UI/API | firmware GPIO behavior、sensor register map、device 内 power sequencing |
| Hub repositories/storage | persistence、schema translation、history query、file/artifact storage | UI wording、device electrical behavior、MQTT transport policy |
| Hub adapters/connectors | Cloudflare、Turso、S3-compatible storage、weather、Instagram、camera/RTSP、external APIs | connector なしでも成立すべき core domain decision |
| MQTT/API contracts | 安定した message shape、topic、status/config/OTA contract | ローカル実装都合や H/W detail |
| Device App | `device_kind`、製品挙動、runtime config parsing、schedule/control policy、sensor sampling order、status payload shape | 共通 HAL/protocol が存在する raw hardware implementation |
| Firmware HAL | GPIO-switched power、ADC、UART/RS485 direction control、camera、audio などの物理 H/W primitive | product policy、MQTT payload、crop rule、runtime config parsing |
| Firmware protocol driver | Modbus sensor register conversion など、bus 上の protocol/register mapping | power sequencing、irrigation policy、hub persistence |

## 横断ルール

- hub は system をオーケストレーションする。device は固定 `device_kind` contract に従って測定または実行を担当する。
- イチゴ点滴栽培のような作物別 system は、device と hub policy の composition である。H/W contract 自体が変わらない限り、作物別巨大 firmware device は作らない。
- `device_kind` は H/W role と payload contract を固定する。material に変わる場合は、新しい firmware project と `device_kind` を作る。
- 電源電圧、MOSFET 定格、筐体、WTR build が小型低電圧負荷を駆動するかどうかのような H/W だけの差異は、payload contract や hub 挙動が変わらない限り、既存 `device_kind` 内の H/W profile として扱う。
- 再利用可能な mechanism は common layer に置く。例: MQTT transport、OTA、RS485 bus handling、Modbus frame handling、GPIO-switched power、storage repositories、Cloudflare provisioning helper。
- 製品判断は reusable mechanism の上に置く。例: いつ灌水するか、どの threshold を使うか、feedback 欠落をどう扱うか、営農者向け UI wording。
- MOSFET 出力の表示名や「何を制御しているか」は hub / device App の設定メタデータで管理する。電気的 primitive は power switch または output channel のままであり、HAL は負荷が pump、valve、relay、sensor rail、現場固有ラベルのどれかを知らない。
- 既存下位 layer の呼び出しを製品名で束ねるだけの wrapper layer は追加しない。wrapper は rename ではなく、実 boundary を追加する場合だけ作る。

## Hub レイヤルール

- Flask route は request/response shape を扱い、service を呼ぶ。
- service は orchestration と domain decision を持つ。
- repository は data persistence と query を担当し、UI wording や transport detail を持たない。
- connector/adapter は外部 system を隔離する。Cloudflare、S3、Instagram、weather-provider code を読まなくても core hub behavior が理解できるようにする。
- Local HubとCloud Hubを、shared contract上の別product applicationとして分離する。
  Local Hubは現行のinstallation別Turso/libSQLと直結MQTT制御を維持する。Cloud Hub
  はdirectory adapterと顧客ごとの専用Turso DBを持てるが、caller入力でDBを
  選ばせない。Cloudのmulti-tenant routing/credentialをLocal HubやEdge Runtimeへ
  importしない。

## Device Firmware ルール

詳細は [../../client-devices/docs/jp/firmware_layering_policy.md](../../client-devices/docs/jp/firmware_layering_policy.md) を正とする。

要点:

- HAL 名は H/W primitive を表し、device kind を表さない。
- product behavior を表す組み合わせは device App から common HAL を compose してよい。
- protocol driver は bus/register protocol を変換し、power rail 制御や product decision を持たない。
- WRS は `hal_power_switch`、`hal_rs485_bus`、`hal_rs485_sensor_protocol` を使う。実 H/W primitive が増えない限り、`hal_wrs` wrapper は再導入しない。
- battery 駆動や低電圧負荷向けの水やり build は、WTR と同じく local irrigation output と local soil moisture feedback を持つなら WTR の H/W profile として扱う。その H/W 差だけで新しい `device_kind` は作らない。

## Data / UI ルール

- 測定値は metric definition と time-series value に分ける。query model 上の必要性がない限り、sensor ごとに固定カラムを増やさない。
- UI は営農者向けの言葉を先に出す。raw payload、register 名、debug field は detail view に置く。
- runtime config には `mosfet_switches` のような表示メタデータを持たせてよい。hub が `channel_mask=1` だけでなく「点滴ライン A」のように表示するための情報であり、firmware HAL contract ではない。
- data placement は model の一部である。field、section、ridge/bed、point のどこに属するかを明示し、device ID や MQTT topic だけから推測しない。

## レビュー時チェックリスト

実装前に次を確認する。

1. その判断はどの layer が持つべきか。
2. 次の layer boundary をまたぐ contract は何か。
3. 新しい module 名は product ではなく responsibility を表しているか。
4. 既存 common primitive の上に App/service orchestration を置くだけで足りないか。
5. UI wording が persistence に、H/W behavior が hub service に、crop policy が firmware HAL に漏れていないか。
6. boundary が維持されていることを、どの build、test、link check で確認するか。
