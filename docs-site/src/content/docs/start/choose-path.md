---
title: 導入ルートを選ぶ
description: 自己調達で構築するルートと、準備中の弊社提供機器ルートを区別します。
---

購入前に、どちらの導入ルートを使うかを確認します。現在、実際の購入・セットアップ手順を公開しているのは自己調達ルートです。

<div class="route-options">
  <section class="route-option is-active">
    <span class="route-status">現在利用可能</span>
    <h2>自己調達して構築する</h2>
    <p>Raspberry Pi、電源、storage、network、ESP32S3と周辺部品を購入し、OSから自分でセットアップします。</p>
    <a href="/start/hardware/">機器選定へ進む →</a>
  </section>
  <section class="route-option is-pending">
    <span class="route-status">準備中</span>
    <h2>弊社提供機器を利用する</h2>
    <p>Hubソフトウェアと.envを設定済みで出荷し、現地ではWi‑FiとCloudflare Accessを設定する構成を検討中です。</p>
    <a href="/start/provided-hardware/">提供予定を見る →</a>
  </section>
</div>

## 自己調達ルートの構成

<table class="decision-table">
  <thead><tr><th>目的</th><th>構成</th><th>次に読む</th></tr></thead>
  <tbody>
    <tr><td>まずHubを構築する</td><td>Raspberry Pi + storage + 電源 + 有線LAN</td><td><a href="/start/hardware/">機器を購入</a></td></tr>
    <tr><td>自宅・圃場LANだけで使う</td><td>上記 + Hub + Mosquitto + 必要なデバイス</td><td><a href="/start/network/">networkを決める</a></td></tr>
    <tr><td>外出先から管理する</td><td>上記 + Cloudflare Tunnel / Access</td><td><a href="/hub/cloudflare/">Cloudflareで公開</a></td></tr>
    <tr><td>土壌水分と1系統の潅水</td><td>WTR</td><td><a href="/devices/wtr/">WTRを作る</a></td></tr>
    <tr><td>2系統の潅水とRS485センサー</td><td>WRS</td><td><a href="/devices/wrs/">WRSを作る</a></td></tr>
    <tr><td>測定だけ追加する</td><td>SOI または ENV</td><td><a href="/devices/sensors/">センサーを選ぶ</a></td></tr>
  </tbody>
</table>

## 実際の導入順

1. [機器を選んで購入する](/start/hardware/)。
2. [Hub名、IP、Wi‑Fi、MQTTを決める](/start/network/)。
3. [Raspberry Pi OSとMosquittoを準備する](/hub/raspberry-pi/)。
4. [INAS Hubをインストールする](/hub/install/)。
5. Hub画面を開き、圃場を1つ作る。
6. デバイスを1台だけ製作し、机上でWi‑Fi/MQTTを設定する。
7. Hubで受信とRuntime Configを確認し、受入試験を行う。
8. [Cloudflare Access経由の外部アクセス](/hub/cloudflare/)を設定する。
9. 圃場へ設置し、実際の水の流れと安全停止を確認する。

:::tip[最初の1台]
アナログ土壌水分と1つの潅水出力だけならWTRが最小構成です。ただしデバイス部品より先に、常時稼働するRaspberry Pi Hubとnetworkを準備します。
:::
