---
title: 通信・ネットワークの技術詳細
description: mDNS、DHCP予約、MQTT、OTA、Cloudflareの通信経路、制約、セキュリティ上の注意を技術者向けにまとめます。
---

:::caution[技術者向け]
このページは、自己構築、ネットワーク設計、障害調査を担当する人向けです。提供機器を通常利用する場合は読む必要がありません。一般的な準備は[使うWi-Fiを準備する](/start/network/)を参照してください。
:::

機器へOSやF/Wを書き込む前に、Hubのhostname、管理PCから使う名前、デバイスから使う固定的な接続先、MQTT認証、外部公開hostnameを決めます。これらは利用者からはひとつの「Hub」に見えますが、技術上は別の経路です。

<figure class="concept-illustration">
  <a href="/images/illustrations/network-layout.webp" aria-label="Hubと圃場デバイスのネットワーク配置スケッチを原寸で開く">
    <img src="/images/illustrations/network-layout.webp" alt="同じLANのルーター、Raspberry Pi Hub、管理PCと、ハウス内の無線デバイスを示すスケッチ" width="1216" height="704" loading="lazy" decoding="async" />
  </a>
  <figcaption>管理PC、Hub、圃場デバイスを、最初は同じLANへ置きます。管理PCはmDNS名、現行デバイスはHubのDHCP予約IPを使う点を区別します。</figcaption>
</figure>

## 技術スタック

| レイヤー | 採用技術 | 主な責務 |
|---|---|---|
| Hub OS | Raspberry Pi OS Lite 64-bit | systemdによる常時稼働、Avahi、Mosquitto、Hub process |
| 管理画面 | INAS Hub HTTP UI / API | 圃場、作業、デバイス、Runtime Config、F/Wの管理 |
| デバイス通信 | MQTT 3.x over TCP / Mosquitto | 状態送信、設定要求・返信、OTA offer |
| F/W配信 | LAN内HTTP | `firmware.bin`本体のdownload |
| LAN内名前解決 | Avahi / mDNS | 管理PCから`<hub名>.local`を参照 |
| 外部アクセス | Cloudflare Access / Tunnel | 利用者認証とHub UIへの外向きTunnel |
| クラウド保存 | Turso / R2またはS3互換storage | database、画像、F/W artifact |

## 2つの名前と1つのIPを区別する

| 値 | 例 | 誰が使うか | 到達範囲 |
|---|---|---|---|
| HubのmDNS名 | `farm-a01.local` | 同じLANの管理PC | 圃場・事務所LAN内 |
| HubのDHCP予約IP | `192.168.10.20` | 現行デバイスのMQTT・OTA | 圃場・事務所LAN内 |
| Cloudflare公開hostname | `hub.example.com` | 外出先の利用者browser | Internet経由、Access認証あり |

自己構築では、重複しないHub名を決めます。利用できる文字は英小文字、数字、hyphenです。`.local`はhostnameへ入力せず、参照するときだけ末尾へ付けます。

```text
OSへ設定するhostname: farm-a01
LAN内で使うmDNS名:     farm-a01.local
```

## 現行デバイスでDHCP予約IPを使う理由

現行F/WのMQTT接続はArduino WiFiの`WiFi.hostByName()`を使い、明示的なmDNS queryを実装していません。ネットワーク機器や中継器によっては`.local`を通常DNSとして解決できないため、自己構築ルートではRaspberry PiのDHCP予約IPをデバイスへ設定します。

- 管理PCからのSSHとHub画面: `<hub名>.local`
- デバイスのMQTT接続先: `<Hub予約IP>:1883`
- デバイスのF/W取得先: `http://<Hub予約IP>:39151`

将来の弊社提供品では、出荷時に割り当てる顧客IDを接続先として扱い、利用者がIPやプロトコルを意識しない構成を検討しています。現在のF/Wへ未実装の挙動を前提にしないでください。

## 通信経路と設定場所

| 通信 | 接続元 → 接続先 | host / port | 設定場所 |
|---|---|---|---|
| Hubとbroker | Raspberry Pi内 → Mosquitto | `localhost:1883` | Hubの `.env` |
| デバイスMQTT | ESP32S3 → Mosquitto | `<Hub予約IP>:1883` | デバイスsetup AP |
| デバイスOTA | ESP32S3 → Hub HTTP | `http://<Hub予約IP>:39151` | Hubの `FIRMWARE_HOSTNAME` |
| LAN内の画面 | PC → Hub | `http://<hub名>.local:39151` | browser |
| 外部の画面 | Browser → Access → Tunnel | `https://hub.example.com` | Cloudflare |
| Hubのクラウド保存 | Raspberry Pi → Turso / R2 | HTTPS 443 | Hubの `.env` |

:::caution[CloudflareのURLをデバイスへ設定しない]
Cloudflare公開hostnameは利用者browser用です。現在のデバイスF/Wは、Access認証付きHTTPSをMQTTやOTAに使用しません。MQTT hostとF/W取得先にはLAN内のHub予約IPを設定します。
:::

## 必要なポート

| port | protocol | 用途 | 公開範囲 |
|---:|---|---|---|
| 1883 | MQTT / TCP | 状態、Runtime Config、OTA通知 | 信頼できるLANだけ |
| 39151 | HTTP / TCP | Hub画面、API、F/W download | LAN内。Internetへport forwardしない |
| 5353 | mDNS / UDP multicast | 管理PCから`<hub名>.local`を名前解決 | 同一LAN / VLAN |
| 443 | HTTPS / TCP | Turso、R2、Cloudflare APIなど | Raspberry Piから外向き |
| 7844 | QUICまたはHTTP/2 | cloudflaredのTunnel | Raspberry Piから外向き |

Cloudflare TunnelはRaspberry Pi上の`cloudflared`から外向きに接続するため、ルーターでHub向けのinbound portを開けません。

## LAN設計上の注意

最初の1台はRaspberry Pi、設定用PC、ESP32S3を同じLANへ接続します。次の構成では、mDNSの名前解決または端末間通信が遮断されることがあります。

- guest Wi‑Fi
- AP isolationまたはclient isolationが有効
- Hubとデバイスが別VLAN
- multicastを転送しない中継器
- 圃場ルーターと事務所ルーターが別network

別VLANを使う場合は、mDNS reflector、routing、firewall rule、MQTT/HTTPの到達性をネットワーク管理者が設計してください。単に`5353/udp`を開けるだけでは、異なるbroadcast domainを越えた名前解決が成立しない場合があります。

## セキュリティ境界

- MQTT `1883/tcp`とHub HTTP `39151/tcp`をInternetへport forwardしない。
- MQTTはanonymous接続を無効にし、ユーザー名と十分に強いpasswordを使う。
- `.env`、MQTT password、Cloudflare tokenをGit、チャット、公開スクリーンショットへ載せない。
- 外部からの画面アクセスはCloudflare Accessで利用者を認証する。
- デバイス用LANを分離する場合は、Hubへの必要な通信だけを明示的に許可する。
- 平文MQTTを別拠点間やInternetへ延伸しない。拠点間接続が必要ならVPNまたはTLS終端を別途設計する。

## 障害調査の順序

1. Raspberry Piとデバイスへ電源が供給されている。
2. どちらも意図した2.4GHz Wi‑Fiまたは有線LANへ参加している。
3. DHCP leaseと予約IPが一致している。
4. 管理PCから`<hub名>.local`とHub予約IPへ到達できる。
5. デバイスから`<Hub予約IP>:1883`と`:39151`へ到達できる。
6. Mosquittoのcredential、ACL、topicがF/WとHubで一致している。
7. Hubの`/readyz`とservice logに継続的なエラーがない。

Raspberry Pi側で確認する代表的なコマンドです。

```bash
hostnamectl
hostname -I
getent hosts <hub名>.local
systemctl status avahi-daemon mosquitto ina-device-hub --no-pager
curl --fail http://127.0.0.1:39151/readyz
ss -lntup
```

## 構築前に記録する値

```text
Hub hostname:               ____________________
Hub mDNS（管理PC用）:       ____________________.local
DHCP予約IP（デバイス用）:   ____________________
2.4GHz Wi-Fi SSID:          ____________________
MQTT username:              ____________________
Cloudflare public hostname: ____________________
```

Wi‑Fi password、MQTT password、Cloudflare tokenはこの記録用紙へ平文で残さず、password managerで管理します。

設計を確定したら[Raspberry Piを準備する](/hub/raspberry-pi/)へ進みます。
