---
title: 自己調達セットアップの全手順
description: 機器の購入からRaspberry Pi、Hub、デバイス、Cloudflare Access、圃場設置までを順番に進めます。
---

このページは自己調達ルートの目次です。上から順に進み、各工程の完了条件を満たしてから次へ移ります。弊社提供機器を利用するルートは[準備中](/start/provided-hardware/)です。

## 1. 全体構成を理解する

- [全体構成を理解する](/start/overview/)で、何がRaspberry Pi、ESP32S3、Cloudflare上で動くかを確認します。
- Hub画面用の外部経路と、デバイス用のLAN内経路を区別します。

**完了条件:** `Cloudflare Accessは人向け、MQTT/OTAはデバイス向け`と説明できる。

## 2. 機器を選んで購入する

- [機器を選んで購入する](/start/hardware/)で暫定最低目安と推奨構成を比較します。
- [購入前チェックリスト](/start/prerequisites/)で設置場所、電源、電波、負荷定格を確認します。
- 最初に作るdevice kindと部品表を確定します。

**完了条件:** Raspberry Pi、storage、電源、冷却、LAN、デバイス部品が揃っている。

## 3. ネットワーク情報を決める

- [ネットワーク構成を決める](/start/network/)で、Hub hostname、管理PC用mDNS名、デバイス用DHCP予約IP、2.4GHz SSID、MQTT credential、Cloudflare hostnameを決めます。
- Hub、設定用PC、最初のデバイスを同じLANへ接続できるようにします。

**完了条件:** `<hub名>.local`、Hub予約IP、Cloudflare公開hostnameの違いを記録済み。

## 4. Raspberry Piを準備する

- [Raspberry Piを準備する](/hub/raspberry-pi/)に従い、Raspberry Pi OS Lite 64-bitを入れます。
- hostname、mDNS、DHCP予約、`uv`、Mosquittoを設定します。

**完了条件:** `<hub名>.local`でSSHでき、認証付きMQTTのpublish/subscribeが成功する。

## 5. INAS Hubをインストールする

- [Hubをインストール](/hub/install/)に従い、Raspberry Pi上でclone、`.env`設定、接続確認、systemd登録を行います。
- `http://<hub名>.local:39151/readyz`を確認します。

**完了条件:** Hubが再起動後も自動起動し、MQTTを含むreadinessが成功する。

## 6. 最初の圃場を作る

1. 管理者としてログインします。
2. 「圃場」から新しい圃場を追加します。
3. 圃場名、所在地、タイムゾーンを確認します。
4. 必要なら区画や畝を追加します。
5. ダッシュボードに圃場が表示されることを確認します。

**完了条件:** 再読み込み後も圃場が残り、設定画面を開ける。

## 7. デバイスを1台作って接続する

1. [デバイス一覧](/devices/)からkindを選びます。
2. 電源を外して配線し、continuityとshortを検査します。
3. F/Wをbuild・uploadします。
4. setup APで2.4GHz Wi‑FiとMQTT `<Hub予約IP>:1883`を設定します。
5. Hubへ同じdevice IDを登録し、`config_received=true`を確認します。
6. device-specificな受入試験を行います。

**完了条件:** Hubに最新状態が表示され、Runtime Config受信と安全な出力試験に成功する。

## 8. Cloudflare Accessで外部公開する

- [Cloudflareで公開](/hub/cloudflare/)に従い、利用者自身のCloudflare accountでAccessとTunnelを構築します。
- 許可したemailだけがアクセスできることを確認します。
- ルーターのinbound portは開けません。

**完了条件:** 外部networkから許可ユーザーはloginでき、未許可ユーザーは拒否される。

## 9. 圃場へ設置する

1. 手動遮断と停止手段を確認します。
2. deviceを設置し、実際の電波強度と電源電圧を確認します。
3. 少量・短時間から通水します。
4. 測定、潅水結果、eventをHubで確認します。
5. 起動時潅水testなどの施工用modeを無効にします。

## 導入後に読む

- 潅水を設定する: [潅水](/configure/watering/)
- 日々の状態を確認する: [日々の確認](/operate/daily/)
- F/Wを更新する: [F/W・OTA更新](/operate/firmware/)
- 問題を切り分ける: [トラブルシューティング](/troubleshoot/)

:::tip[完了条件]
HubとMosquittoが自動起動し、デバイスがWi‑Fi/MQTTへ再接続し、許可した利用者がCloudflare Access経由で画面を開ければ、初期導入は完了です。
:::
