---
title: 購入前チェックリスト
description: 機器を注文する前に、設置場所、電源、ネットワーク、潅水負荷、アカウントを確認します。
---

このページを印刷または共有し、未確認の項目を残したまま購入へ進まないでください。具体的なRaspberry Piの最低目安・推奨構成は[機器を選んで購入する](/start/hardware/)にあります。

## 設置場所

- [ ] Raspberry Piを水、結露、薬剤、直射日光から守れる
- [ ] 熱がこもらず、冷却部品の吸排気を塞がない
- [ ] 24時間使えるAC電源がある
- [ ] 停電時に安全に停止できる、またはUPSを設置できる
- [ ] Ethernet cableを配線できる、または十分なWi‑Fi強度がある
- [ ] 保守時にRaspberry Piと制御盤へ安全に近づける

## ネットワーク

- [ ] デバイス設置位置で2.4GHz Wi‑Fiを利用できる
- [ ] Raspberry Piとデバイスを同じLAN/VLANへ接続できる
- [ ] guest Wi‑FiやAP/client isolationを使わない
- [ ] ルーターでRaspberry PiのDHCP予約ができる
- [ ] `<hub名>.local`に使う重複しないhostnameを決めた
- [ ] Internet側へ1883/39151をport forwardしない
- [ ] HubからInternetへHTTPS接続できる

詳しい通信経路とportは[ネットワーク構成を決める](/start/network/)で確認します。

## Raspberry Pi Hub

- [ ] Raspberry Pi 4 2GB以上、または推奨するPi 5 4GB以上を選んだ
- [ ] 32GB以上の高耐久microSD、または推奨する64GB以上のSSDを選んだ
- [ ] Piのモデルに合う電源を選んだ
- [ ] ケースと冷却方法を選んだ
- [ ] OS書き込み用のreader・adapterがある
- [ ] セットアップに使うPCとbrowserがある

## デバイスと潅水設備

- [ ] 必要な測定項目と潅水出力数からdevice kindを決めた
- [ ] valve / pumpの定格電圧、最大電流、起動電流を確認した
- [ ] GPIOと実負荷の間に入るdriver、MOSFET、relayを選んだ
- [ ] flyback protectionとfuseを選んだ
- [ ] 電源容量と電線サイズを決めた
- [ ] 防滴筐体、cable gland、端子、線名labelを選んだ
- [ ] multimeter、電流制限付き電源、圧着工具を用意した
- [ ] 手動遮断弁と緊急停止方法を決めた

部品はデバイスごとに異なります。[デバイス一覧](/devices/)で機種を決めてから、各ページの部品表とpin contractを確認してください。

## サービスとアカウント

- [ ] GitHubからリポジトリを取得できる
- [ ] Turso databaseを作成できる
- [ ] Cloudflare R2またはS3互換storageを用意できる
- [ ] 外部アクセスを使う場合、Cloudflare accountと管理domainがある
- [ ] Cloudflare Zero Trustで許可する利用者emailを決めた
- [ ] passwordとtokenを保存するpassword managerがある

## 外部公開する場合に用意するもの

- Cloudflareアカウント
- Cloudflareで管理するドメイン
- Cloudflare Zero Trustの利用環境
- Hub上で動かす `cloudflared`

:::caution[秘密情報]
`.env`、Cloudflare AccessのClient Secret、MQTT password、API tokenをGitへコミットしないでください。公開サイトやスクリーンショットにも含めません。
:::

すべて確認できたら[機器を選んで購入する](/start/hardware/)へ戻って注文内容を確定します。購入後は[Raspberry Piを準備する](/hub/raspberry-pi/)へ進みます。
