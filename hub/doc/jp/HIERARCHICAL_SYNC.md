# Local Hub 階層 Sync v1 運用

Local Hub は、従来どおり直結デバイスを MQTT で制御しながら、子の Edge
Gateway / Local Hub を集約する Sync v1 親として動作できます。また、上位の
Local Hub に対する Sync v1 子としても動作します。別実装のCloud Hubも直結Edge
Gatewayから同じSync v1 envelopeを受けますが、Local HubのTurso DBをCloudへ
uploadする構成ではありません。cloud MQTTも使用しません。

```text
上位 Local Hub
             ^
             | 子から開始する HTTPS Sync v1
             |
         Local Hub
          /      \
  直結 MQTT     HTTPS Sync v1
   devices       child Local Hub / Edge Gateway
```

上位接続が停止しても、Local Hub と Edge Gateway はローカル MQTT、キャッシュ
済み runtime config、永続 outbox を使って圃場内の運用を継続します。配送は
at-least-once であり、安定した ID と revision によって再送を重複適用しません。

## 永続データ

Local Hub の階層状態は `WORK_DIR/edge-runtime/` に保存します。

- `identity.json`: Local Hub の不変な `INALH-<UUIDv4>` ID
- `edge.db`: 直結デバイス用の runtime config、上位向け event/result outbox、
  Sync cursor
- `hierarchy.db`: 子ノード、origin route、子から受信した event/result、下位へ
  配送する desired resource/command

SQLite ファイルはローカル Linux ファイルシステム上で `0600` とし、ディレクトリ
はサービス実行ユーザー以外から読めない権限で運用してください。Edge Gateway
へ Turso URL や Turso token を配布しません。

Cloud Hubを親にするEdge Gatewayは、Cloud Hub directoryに登録したnode
credentialで認証し、directoryが顧客専用Turso DBを決定します。Edge requestの
`tenant_id`やDB情報ではrouteしません。

## 子ノードの登録

登録 API は Hub 管理者専用です。`INAEG-<UUIDv4>` の Edge Gateway、または
`INALH-<UUIDv4>` の Local Hub を登録します。

```http
POST /local/api/hierarchy/children/enrollments
Content-Type: application/json

{
  "node_id": "INAEG-223e4567-e89b-42d3-a456-426614174001",
  "display_name": "北圃場 Gateway"
}
```

Local Hub を子にする場合だけ、その配下として明示的に許可する node ID を
`descendant_node_ids` に指定できます。Edge Gateway は子を持てません。

応答の `bearer_token` はこの1回だけ返ります。Hub はランダム salt 付き digest
のみを保存します。トークンは QR または同等の一時的な引き渡し手段で対象機へ
渡し、対象機では所有者だけが読める `0600` のファイルに保存してください。
再登録すると旧トークンは直ちに無効になり、次の API でも明示的に失効できます。

```http
POST /local/api/hierarchy/children/<node_id>/revoke
```

現段階では安全な登録 API と one-time credential 発行までが実装範囲です。
Gateway の初回 AP 画面、QR カメラ導線、任意の Flutter 専用端末 UI は後続の
セットアップ UI でこの API に接続します。登録トークンをログ、URL query、
通常のノード一覧へ出してはいけません。

## 上位 Hub への接続

上位 Hub から受け取った one-time token を、たとえば
`/var/lib/inas/credentials/parent.token` に保存して `0600` にします。

```dotenv
HUB_SYNC_PARENT_BASE_URL=https://parent.example.jp
HUB_SYNC_PARENT_TOKEN_FILE=/var/lib/inas/credentials/parent.token
HUB_SYNC_PARENT_CA_FILE=
HUB_SYNC_PARENT_CLIENT_CERT_FILE=
HUB_SYNC_PARENT_CLIENT_KEY_FILE=
HUB_SYNC_PARENT_TIMEOUT_SECONDS=20
HUB_SYNC_PARENT_ALLOW_INSECURE_LOOPBACK=false
```

本番の親 URL は HTTPS が必須です。開発時だけ、
`HUB_SYNC_PARENT_ALLOW_INSECURE_LOOPBACK=true` と
`localhost` / `127.0.0.1` / `::1` の組み合わせで HTTP を許可します。URL への
credential 埋め込み、redirect、group/other が読める bearer token / private key、
symlinkや通常ファイルでないcredential、正規の`inas_sync_v1_`形式でないtoken、
1 MiB を超える圧縮前後の Sync body は拒否します。
node bearer token は常に必須で、mTLS は追加防御として併用できますが token の
代わりにはなりません。

`HUB_SYNC_PARENT_BASE_URL` が空なら standalone Local Hub として動作します。
上位 URL を設定しただけでは event 転送を有効にせず、認証済みの正常な応答を
初めて永続適用できた時点で有効にします。上位が一時停止しても Hub の readiness
や直結 MQTT 制御は停止しません。

初回要求は health と空の outbox batch だけを送り、TLS・node credential・応答の
correlationを確認してから次回以降にbacklogを送ります。正常接続済みの親URLは
階層DBへ結び付けます。URLを変更した場合は以前のcursorとactive状態を引き継がず、
新しい親との空ハンドシェイクからやり直します。

## HTTP API

ノード用 Sync API とブラウザ管理 API は認証境界を分離します。

- `POST /sync/v1/nodes/<node_id>/exchange`: node bearer credential 専用
- `GET /local/api/hierarchy/nodes`: 自ノード、子ノード、接続状態
- `GET /local/api/hierarchy/events?limit=100`: 子から受信した event
- `PUT /local/api/hierarchy/desired-resources`: 下位へ配送する desired state
- `POST /local/api/hierarchy/commands`: 有効期限付き command

Cloudflare Access の利用者 JWT は node bearer credential の代わりになりません。
反対に node credential で管理 API を利用することもできません。要求 body に
`tenant_id`、DB URL、DB token などのルーティング指定を受け付けません。

## 障害時の確認事項

`GET /local/api/hierarchy/nodes` の `upstream_active` は「上位設定がある」ではなく、
少なくとも1回は正常な Sync 応答を永続適用したことを表します。WAN 障害時は
次を確認してください。

1. 直結デバイスの config request/reply とローカル command が継続していること
2. `edge.db` と `hierarchy.db` を置くファイルシステムに空きがあること
3. 上位 URL の TLS、CA、時刻、token file の所有者と mode が正しいこと
4. 復旧後に同一 event ID / origin sequence のまま backlog が再送されること

上位から直結デバイスへ届いた `device.runtime_config` は Local Hub のキャッシュ
で authoritative になります。上位停止中もその値で MQTT reply を返し、ローカル
JSON の編集によって暗黙に上書きしません。
