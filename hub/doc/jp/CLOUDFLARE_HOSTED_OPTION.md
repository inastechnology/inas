# Cloudflare hosted option

INASは次の2構成を分離する。DBとcredentialを相互流用しない。

## Local Hub + 任意Tunnel

現行Local Hubは顧客管理host上でFlask、MQTT、schedule、storage連携、設定済み
Turso/libSQL replicaを実行する。Cloudflare Access + Tunnelは、その同じLocal Hub
へ遠隔接続する任意の入口である。

```text
browser -> Cloudflare Access -> Tunnel -> Local Hub :39151
device  -> local MQTT broker -> Local Hub
```

Tunnelを追加してもLocal HubがCloud Hubへ変わるわけではなく、DBの所有境界も
変わらない。WAN、Access、Tunnel停止中もlocal MQTTと直結commandを継続する。

既存の低level setupは`hub/.env`を正として実行する。

```bash
bash scripts/cloudflare_hosted_setup.sh --install-cloudflared
bash scripts/cloudflare_hosted_up.sh --install-cloudflared
```

`HUB_AUTH_MODE=cloudflare_access`ではLocal Hubが
`Cf-Access-Jwt-Assertion`を検証する。現行本番の`TURSO_DATABASE_URL`と
`TURSO_AUTH_TOKEN`は維持し、Cloud Hub credentialへ置き換えない。

## 共有Cloud Hub

Local Hubを運用しない顧客は、別実装の
[`../../../hub-cloud/`](../../../hub-cloud/README.md)を使う。

```text
browser -> Cloudflare Access -> 共有Worker 1つ
Edge Gateway -> 認証付きHTTPS Sync -> 共有Worker 1つ
                                      |
                                      +-- directory Turso DB
                                      +-- 顧客ごとの専用Turso DB
```

顧客ごとにWorkerを作らない。共有WorkerはAccess利用者またはEdge nodeを先に認証し、
directoryでtenantを解決してから、その顧客専用DBだけを開く。requestのDB URL、
DB token、内部tenant IDで接続先を選べない。

Cloud Hubにはcloud MQTT brokerを置かない。MQTT、Wi-Fi AP、runtime config
cache、安全なlocal actionはEdge Gatewayに残す。Gatewayへ渡すのはnode固有
credentialとCloud Hub Sync URLだけであり、Turso/Cloudflare管理credentialは
渡さない。

## Security境界

- Local Hub browser認証とEdge Sync node認証を分離する。
- Local Hub Turso credentialをCloud Hub/Edge Gatewayへコピーしない。
- Cloud Hub directory/顧客DB credentialをLocal Hub/Edge Gatewayへコピーしない。
- Edge Gatewayの直接の親はLocal HubまたはCloud Hubのどちらか1つだけ。
- 将来の課金・trial制御はCloud UI/管理機能へ適用し、local MQTT safety loopを
  停止させない。

[Cloud Hub security](../../../hub-cloud/docs/SECURITY.md)と
[階層Sync](HIERARCHICAL_SYNC.md)も参照する。
