---
title: Cloudflareで公開
description: Cloudflare TunnelとAccessを使い、ローカルHubを認証付きで公開します。
---

Cloudflare Tunnelを使うと、ルーターでinbound portを開けずにHubへ接続できます。Cloudflare Accessを入口に置き、許可した利用者だけが管理画面へ進める構成を推奨します。

このページの`bash`・`python3`・`systemctl`コマンドは **HubのRaspberry Pi上** で実行します。Cloudflare Dashboardの操作だけは、管理者のPCにあるbrowserで行います。先にLAN内でHub、Mosquitto、最初のデバイスが正常に動くことを確認してください。

## 構成

```text
Browser → Cloudflare Access → Cloudflare Tunnel → http://127.0.0.1:39151
                                               └→ INAS Hub
```

`cloudflared`はRaspberry Piで動き、Cloudflareへ外向きに接続します。InternetからTCP 39151や1883をRaspberry Piへport forwardしません。Cloudflare Workersを使うCloud Appは管理API/UIの基盤であり、現時点ではローカルHubの全機能を置き換えるものではありません。

## 設定する

1. `.env`にCloudflare account、hostname、Accessの値を設定します。
2. 初回だけsetup scriptでAccess・Tunnel・DNSをprovisionします。
3. HubとTunnelを起動します。
4. 許可したemailでログインできることを確認します。
5. 許可していないブラウザsessionから拒否されることを確認します。

公開hostnameは利用者自身が管理するCloudflare domainで決めます。LAN内の`<hub名>.local`とは別の名前です。

```bash
cd hub
bash scripts/cloudflare_hosted_setup.sh --install-cloudflared
bash scripts/cloudflare_hosted_up.sh --install-cloudflared
```

systemdへ含める初回production installは次のとおりです。

```bash
sudo ./scripts/install_service.sh \
  --production \
  --target-dir "$PWD" \
  --enable-cloudflare-tunnel
```

## 許可するemailを管理する

```bash
python3 scripts/cloudflare_access_setup.py list
python3 scripts/cloudflare_access_setup.py add user@example.com
python3 scripts/cloudflare_access_setup.py remove user@example.com
```

緊急で権限を外す場合は、Access groupからemailを削除するだけでなく、既存sessionもrevokeします。

## Tunnelを確認する

```bash
bash scripts/cloudflare_tunnel_daemon.sh status
bash scripts/cloudflare_tunnel_daemon.sh logs
```

Cloudflare Error 1033は、connectorが停止しているか、connectorから `http://127.0.0.1:39151` へ到達できないときに発生します。Hubの `/readyz`、次にTunnel serviceの順で確認してください。

:::danger[OTAのURLは別経路]
Cloudflare AccessのHTTPS hostnameを、デバイスのMQTT hostやOTA download URLに設定しないでください。自己調達では、デバイスからLAN内HTTPで到達できる`FIRMWARE_HOSTNAME=<Hub予約IP>`を使います。
:::

## Operations API

自動運用には、Cloudflare Access service tokenで保護されたHub Operations APIを使えます。tokenは `CF-Access-Client-Id` と `CF-Access-Client-Secret` headerとして送信し、読み取り・artifact登録・OTA予約などを役割ごとのscriptから実行します。

tokenを公開Webページ、client-side JavaScript、ログへ入れないでください。Operations APIは利用者向け画面とは別の管理境界として扱います。
