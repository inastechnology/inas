---
title: ネットワーク構成を決める
description: Hub、MQTT、mDNS、デバイスWi-Fi、Cloudflare Accessの名前と通信経路を決めます。
---

機器へOSやF/Wを書き込む前に、Hubの名前、予約IP、Wi‑Fi、MQTT認証を決めます。Hubの外部公開名、管理PCが使うmDNS名、現行デバイスが使うIP addressは別物です。

## 2つの名前と1つのIPを区別する

| 値 | 例 | 誰が使うか | 到達範囲 |
|---|---|---|---|
| HubのmDNS名 | `farm-a01.local` | 同じLANの管理PC | 圃場・事務所LAN内 |
| HubのDHCP予約IP | `192.168.10.20` | 現行デバイスのMQTT・OTA | 圃場・事務所LAN内 |
| Cloudflare公開hostname | `hub.example.com` | 外出先の利用者ブラウザ | Internet経由、Access認証あり |

自己調達では、重複しないHub名を自分で決めます。利用できる文字は英小文字、数字、hyphenです。`.local`はhostnameへ入力せず、参照するときだけ末尾へ付けます。

```text
OSへ設定するhostname: farm-a01
LAN内で使うmDNS名:     farm-a01.local
```

将来の弊社提供品では、紙とemailで案内する顧客IDをhostnameに使い、`<顧客ID>.local`をデバイスにも設定できる構成を予定しています。現在はデバイスF/Wの明示的なmDNS queryが未実装で、製品仕様も検討中です。出荷案内がない環境で推測したIDを設定しないでください。

:::caution[自己調達では予約IPを使う]
現行F/WのMQTT接続は通常DNSの`WiFi.hostByName()`を使います。ネットワーク機器によっては`.local`を解決できないため、自己調達ルートではRaspberry PiのDHCP予約IPをデバイスへ設定します。mDNS名はPCからのSSH・Hub画面に利用できます。
:::

## どの通信に何を設定するか

| 通信 | 接続元 → 接続先 | host / port | 設定場所 |
|---|---|---|---|
| Hubとbroker | Raspberry Pi内 → Mosquitto | `localhost:1883` | Hubの `.env` |
| デバイスMQTT | ESP32S3 → Mosquitto | `<Hub予約IP>:1883` | デバイスsetup AP |
| デバイスOTA | ESP32S3 → Hub HTTP | `http://<Hub予約IP>:39151` | Hubの `FIRMWARE_HOSTNAME` |
| LAN内の画面 | PC → Hub | `http://<hub名>.local:39151` | ブラウザ |
| 外部の画面 | Browser → Access → Tunnel | `https://hub.example.com` | Cloudflare |
| Hubのクラウド保存 | Raspberry Pi → Turso / R2 | HTTPS 443 | Hubの `.env` |

:::caution[CloudflareのURLをデバイスへ設定しない]
Cloudflare公開hostnameは利用者ブラウザ用です。現在のデバイスF/Wは、Access認証付きHTTPSをMQTTやOTAに使用しません。自己調達ではMQTT hostとF/W取得先にLAN内のHub予約IPを設定します。
:::

## 必要なport

| port | protocol | 用途 | 公開範囲 |
|---:|---|---|---|
| 1883 | MQTT / TCP | 状態、Runtime Config、OTA通知 | 信頼できるLANだけ |
| 39151 | HTTP / TCP | Hub画面、API、F/W download | LAN内。Internetへport forwardしない |
| 5353 | mDNS / UDP multicast | 管理PCから`<hub名>.local`を名前解決 | 同一LAN / VLAN |
| 443 | HTTPS / TCP | Turso、R2、Cloudflare APIなど | Raspberry Piから外向き |
| 7844 | QUICまたはHTTP/2 | cloudflaredのTunnel | Raspberry Piから外向き |

Cloudflare TunnelはRaspberry Pi上の`cloudflared`から外向きに接続するため、ルーターでHub向けのinbound portを開けません。

## mDNSが使えるネットワークにする

Raspberry Pi OSはAvahiによるmDNSに対応しています。同じLAN内であれば、IPが変わっても`<hub名>.local`で参照できます。ただし、次の構成では名前解決やデバイス通信が遮断されることがあります。

- guest Wi‑Fi
- AP/client isolationが有効
- Hubとデバイスが別VLAN
- multicastを転送しない中継器
- 圃場ルーターと事務所ルーターが別network

別VLANを使う設計では、mDNS reflector、routing、firewall ruleをネットワーク管理者が設計してください。最初の1台はRaspberry Pi、設定用PC、ESP32S3を同じLANへ接続します。

## 購入・設定前に記録する値

```text
Hub hostname:              ____________________
Hub mDNS（管理PC用）:      ____________________.local
DHCP予約IP（デバイス用）:  ____________________
2.4GHz Wi-Fi SSID:         ____________________
MQTT username:             ____________________
Cloudflare public hostname:____________________
```

Wi‑Fi password、MQTT password、Cloudflare tokenはこの紙へ平文で残さず、password managerで管理します。

次は[Raspberry Piを準備する](/hub/raspberry-pi/)へ進みます。
