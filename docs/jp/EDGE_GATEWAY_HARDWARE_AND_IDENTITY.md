# Edge Gateway H/W・識別子仕様

English summary: [../EDGE_GATEWAY_HARDWARE_AND_IDENTITY.md](../EDGE_GATEWAY_HARDWARE_AND_IDENTITY.md)

作成日: 2026-07-23

## 1. 結論

INASの識別子は、配置先、契約者、デバイス用途、H/W型番を埋め込まない。prefixは実体の種類だけを示し、その後ろに、時刻同期なしで生成できるlowercase UUIDv4を置く。

既存デバイスの`INADS-<UUIDv4>`は変更しない。Edge Gatewayには`INAEG-<UUIDv4>`、Local Hubには`INALH-<UUIDv4>`を新設する。Cloud Hubは物理node IDを持たない共有Workerであり、登録済み`INAEG`を顧客専用Turso DBへ解決する。

Edge Gatewayの量産基準は、removable microSDではなくeMMC搭載Compute Moduleとする。標準機はデータ中継に必要な能力へ絞り、カメラ処理が必要な場合だけ上位H/W profileを使う。SORACOMはMQTT経路ではなく、Edge Gatewayから親HubへのHTTPS WAN回線として追加する。

## 2. ID namespace

| Entity | Production format | Example | Meaning |
|---|---|---|---|
| Client Device | `INADS-<UUIDv4>` | `INADS-123e4567-e89b-42d3-a456-426614174000` | ESP32等のセンサー・制御デバイス |
| Edge Gateway | `INAEG-<UUIDv4>` | `INAEG-123e4567-e89b-42d3-a456-426614174001` | 圃場に置く独立Gateway |
| Local Hub | `INALH-<UUIDv4>` | `INALH-123e4567-e89b-42d3-a456-426614174002` | 管理画面と内蔵Edge Runtimeを持つLocal Hub |

UUIDはRFC 4122 variantのversion 4をcanonical lowercase表記で保存する。prefixはuppercase、区切りは`-`とする。IDは一度発行したら変更・再利用しない。

`INADS-DEMO-*`のようなfixture用IDはdemo/test環境だけで許可し、本番登録・同期APIでは拒否する。

### 2.1 IDへ入れない情報

以下は変更され得るためIDへ埋め込まず、独立した属性または履歴として保存する。

- `device_kind`: `WTR`、`WRS`、`ENV`、`SOI`、`FGT`などのfirmware契約。
- `hardware_profile_id`: `egw-cm4-standard-r1`などのH/W profile。
- `hardware_revision`: carrier boardや組立仕様のrevision。
- `serial_number`: 人がラベルから読み取る短い製造番号。
- `tenant_id`、`site_id`、`field_id`: 契約・配置情報。
- `parent_node_id`: 同期先のLocal Hub。
- SIMのIMSI、IMEI、Ethernet MAC、Wi-Fi MAC、Raspberry Pi board serial。

MAC addressやboard serialは補助的なinventory情報であり、主キーや認証主体にはしない。基板交換、NIC交換、圃場移設、契約移管をしても、過去データの意味が変わらないようにする。

### 2.2 lifecycle

- Client Deviceのfactory resetは、既存実装どおり可能な限り`INADS` IDを保存する。
- Edge GatewayとLocal HubのOS再imageは、保護identity領域から同じnode IDと鍵を復元する。
- 物理本体を交換した場合は新しいnode IDを発行し、site/device assignmentを新nodeへ移す。古いnode IDの履歴は削除しない。
- 認証鍵のrotationではnode IDを変更しない。旧鍵をrevokeし、重複利用を監査する。
- 同じnode IDから同時に異なる鍵・H/W fingerprintが観測された場合はclone疑いとして同期を隔離し、自動的にどちらかを正としない。

## 3. 製造・登録時のidentity

量産Gatewayでは、製造工程でnode IDと非対称鍵pairを作成する。秘密鍵は可能ならTPM 2.0またはsecure elementに生成し、exportしない。Cloud/Local Hubへ登録するのは公開鍵、credential ID、node ID、H/W inventoryだけである。

筐体ラベルには、短い`serial_number`、node ID、claim用QR codeを表示する。QR codeへ長期秘密鍵や継続利用できるbearer tokenを入れない。claim codeは一回限りかつ短時間で失効させる。

初期登録は次の順序にする。

1. 製造時にnode IDと鍵を発行し、H/W検査結果へ紐付ける。
2. 出荷時は未割当状態にする。
3. 管理者がLocal HubまたはCloud HubでQR codeを読み、site/parentを割り当てる。
4. Gatewayが署名付きchallengeで本人性を証明し、短命access tokenと設定を取得する。
5. 以後はGateway固有資格情報だけで、自分のnode subtreeを同期する。

Cloudflare mTLSは追加防御として利用できるが、Sync v1のidentityをCloudflare固有のservice tokenだけには依存させない。Local Hubも同じINA発行鍵を検証できることを必須とする。

## 4. H/W profile

### 4.1 共通要件

量産Edge Gatewayは次を満たす。

- 64-bit Linuxを実行できるArm SBCまたはCompute Module。
- 2 GB以上のRAMと32 GB以上のeMMC。
- Device専用2.4 GHz Wi-Fi AP。Device同士のclient isolationを有効にする。
- WAN用Gigabit Ethernet。Cellular profileではLTE modemとSORACOM IoT SIMを追加する。
- AP用radioをWi-Fi WANと共用しない。Wi-Fi WANが必要なら第二radioを追加する。
- hardware watchdog、RTC、電源断を考慮した永続data領域。
- Gateway固有鍵を保存するTPM 2.0またはsecure element。
- 署名済みboot/update、不要なUSB/UART/SSH経路の無効化、read-only rootまたはA/B更新。
- Mosquitto、NTP、Edge Runtime、network manager、firewallをsystemdで監視する。
- Device networkから到達できる宛先をMQTT、NTP、setup/OTA HTTPへ限定し、一般Internet forwardingを既定で禁止する。

Compute ModuleはeMMCとwirelessのvariantを選択でき、embedded/industrial用途を想定した製品である。Raspberry Pi公式資料はCM4/CM5のeMMC、wireless、carrier board構成を説明している。

### 4.2 承認profile

| `hardware_profile_id` | Position | Baseline | WAN | Production use |
|---|---|---|---|---|
| `egw-rpi5-development-r0` | 開発・PoC | Raspberry Pi 5、4 GB、32 GB以上の開発用storage | Ethernet、任意LTE | 不可。機能検証専用 |
| `egw-cm4-standard-r1` | 標準Edge | CM4-class、2 GB RAM、32 GB eMMC、wireless | Ethernet | MQTT/AP/同期の量産候補 |
| `egw-cm4-cellular-r1` | 回線なし圃場 | `egw-cm4-standard-r1` + LTE modem | SORACOM優先、Ethernet fallback | 量産候補 |
| `egw-cm5-vision-r1` | camera/ffmpeg対応Edge | CM5-class、4 GB RAM、32 GB以上eMMC、承認済み冷却 | EthernetまたはSORACOM | 負荷試験合格後 |
| `lhb-cm5-standard-r1` | Local Hub appliance | CM5-class、4 GB以上RAM、32 GB以上eMMC | Ethernet、任意SORACOM | UI、DB、子Gateway集約用 |

`CM4-class`と`CM5-class`はsoftware compatibilityの基準であり、購入SKUはcarrier board、供給期間、温度、消費電力、認証、価格を確認してBOMで固定する。H/W profileを変更してもnode IDは変更しない。CPU architectureなどSync互換性へ影響する変更だけ、別profileとして登録する。

SORACOM Onyx LTE USB ModemはLinux/Raspberry PiでNetworkManagerによる管理が案内されているため、cellular pilotのreference modemとする。量産carrierへ組み込むmodemは、地域band、技適、温度、アンテナ、SIM交換性を別途BOM審査する。

### 4.3 EdgeとLocal Hubの能力差

標準Edgeは土管と安全な現場折り返しに限定する。

- MQTT broker/client、runtime config cache、local schedule/action execution。
- status/telemetry outbox、command inbox、NTP、Device OTA cache。
- WAN/AP状態、disk、temperature、modem signalなどのhealth報告。
- 保守用の最小UI/API。

Local Hubは同じEdge Runtimeに、ローカル管理UI、現行Turso/libSQL業務DB、
子Gateway用Sync server、農業計画、通知、任意のCloudflare Tunnelを追加する。
Cloud Hubは共有Workerと顧客ごとの専用Turso DBで複数Edge Gatewayを集約する。
どちらの場合も1台のEdge Gatewayが同時に複数の親へ送信しない。

## 5. Client Device H/Wとの関係

現行Client DeviceはSeeed XIAO ESP32S3と共通`ina-client-common`を継続利用する。H/W roleは`device_kind`、具体的な基板・端子差はfirmware targetとH/W profileで表し、`INADS` prefixを`WTR`や`ENV`ごとに増やさない。

将来STM32等へ移行しても、同じDevice Definition、Runtime Config、MQTT契約を実装する物理Client Deviceなら`INADS` namespaceを使用できる。MCU種別をIDから推測してはならない。

新規量産Deviceでは、first bootの乱数生成だけでなく、製造時にIDと個別MQTT credentialを注入する方式へ移行する。ただし既に出荷済みのfirst-boot生成IDは永久に有効とし、形式変更のための再登録を要求しない。

## 6. Inventory payload

GatewayはSync v1 health/inventoryで、少なくとも次を上位へ報告する。秘密情報は含めない。

```json
{
  "node_id": "INAEG-123e4567-e89b-42d3-a456-426614174001",
  "node_type": "edge_gateway",
  "hardware_profile_id": "egw-cm4-cellular-r1",
  "hardware_revision": "r1.0",
  "serial_number": "EGW26-000001",
  "software_version": "0.1.0",
  "capabilities": ["mqtt", "wifi_ap", "ntp", "device_ota", "cellular"],
  "storage_total_bytes": 32000000000,
  "storage_free_bytes": 24000000000
}
```

IMEI、IMSI、MAC address、board serialは管理権限を持つinventory endpointだけで扱い、通常のtenant dashboardやevent payloadへ複製しない。

## 7. 参考

- Raspberry Pi Compute Module hardware: https://www.raspberrypi.com/documentation/computers/compute-module.html
- Raspberry Pi secure boot: https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#secure-boot
- SORACOM Onyx software setup: https://developers.soracom.io/en/docs/soracom-onyx-lte-usb-modem/software-setup/
- Cloudflare client certificates: https://developers.cloudflare.com/ssl/client-certificates/
