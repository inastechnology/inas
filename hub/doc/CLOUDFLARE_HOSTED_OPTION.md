# Cloudflare Hosted Option 実装方針書

作成日: 2026-07-01

## 1. 結論

`ina-device-hub` の Cloudflare hosted option は実装可能。ただし、Cloudflare Workers に移す対象は管理 UI / HTTP API / Turso 上の状態更新に限定する。

現行 hub は `serve.py` で MQTT 常駐接続、メッセージ処理スレッド、タイムラプス、天気記録、Instagram 投稿、Flask Web サーバを同一プロセスで起動している。Workers は HTTP リクエスト処理に適した実行環境なので、MQTT の常時購読、RTSP カメラ接続、ffmpeg、systemd、ローカルファイル前提の処理は local hub に残す。

推奨構成は以下。

- デフォルト: 現行どおり local hub で操作する。
- オプション: Cloudflare Workers + Hono + Turso で hosted 管理 API / UI を提供する。
- 認証認可: Cloudflare Access を入口に置き、Worker 側でも Access JWT を検証する。
- 許可ユーザー管理: Cloudflare Access の rule group を許可 email の source of truth とし、ローカル/CI のスクリプトから追加・削除する。

## 2. 目的

- 現場 LAN に入らなくても、認可された管理者が device 状態、MQTT event、runtime config、OTA target を確認・変更できる。
- Cloudflare hosted option を追加しても、local 接続の運用を壊さない。
- 許可 email の追加・削除をスクリプト化し、Cloudflare dashboard への手作業依存を減らす。
- 認証済み user email を audit log に残し、誰がどの device 設定を変更したか追えるようにする。

## 3. 対象外

初期実装では次を hosted 化しない。

- MQTT broker の内包、MQTT topic の常時 subscribe。
- `camera_connector.generate_frames()` による RTSP preview / multipart stream。
- タイムラプス生成、ffmpeg、Instagram 投稿、AI 投稿文生成。
- ローカル `WORK_DIR` 配下の JSON / image / log への直接アクセス。
- device への即時 push を Worker から直接 MQTT publish すること。

即時 push は local hub が Turso の command queue を polling して MQTT publish する形で後続対応する。

## 4. 公式ドキュメント確認結果

- Cloudflare Workers から Turso/libSQL へ接続する構成は Cloudflare 公式チュートリアルで案内されており、Worker では `@libsql/client/web` を使う必要がある。
- Hono は Cloudflare Workers の starter / deploy / bindings 利用を公式にサポートしている。
- Cloudflare Access は self-hosted application の前段に置ける。Access application は deny by default で、Allow policy に一致した user だけがアクセスできる。
- Access JWT は `Cf-Access-Jwt-Assertion` header で origin / Worker に渡る。Worker 側では `jose` の JWKS 検証で `issuer` と `audience` を確認する。
- Access rule group は email selector を含められ、API token 権限 `Access: Organizations, Identity Providers, and Groups Write` で `/accounts/$ACCOUNT_ID/access/groups` を作成・更新できる。
- Access の policy / application session が有効な間は既存 token が残る。email 削除後の即時遮断が必要な場合は、session duration を短くするだけでなく、Access の session revoke 運用も併用する。
- 環境変数名は日本版環境で使用している `hub/.env` を正とする。Turso 接続も Worker 固有名へ置き換えず、既存の `TURSO_DATABASE_URL` / `TURSO_AUTH_TOKEN` を使う。

参考:

- Cloudflare Workers + Turso: https://developers.cloudflare.com/workers/tutorials/connect-to-turso-using-workers/
- Hono Cloudflare Workers: https://hono.dev/docs/getting-started/cloudflare-workers
- Cloudflare Access self-hosted application: https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/
- Cloudflare Access JWT validation: https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/
- Cloudflare Access rule groups: https://developers.cloudflare.com/cloudflare-one/access-controls/policies/groups/
- Cloudflare Access session management: https://developers.cloudflare.com/cloudflare-one/access-controls/access-settings/session-management/
- Cloudflare Tunnel API: https://developers.cloudflare.com/api/resources/zero_trust/subresources/tunnels/subresources/cloudflared/
- Cloudflare Tunnel token: https://developers.cloudflare.com/api/resources/zero_trust/subresources/tunnels/subresources/cloudflared/subresources/token/
- Cloudflare DNS records API: https://developers.cloudflare.com/api/resources/dns/subresources/records/

## 5. Target Architecture

```text
Browser/Admin CLI
  -> Cloudflare Access
  -> Cloudflare Worker (Hono)
  -> Turso/libSQL
  <- local hub sync/polling
  -> local MQTT broker / devices
```

役割分担:

- `local hub`
  - MQTT subscribe / publish。
  - device config request/reply。
  - camera / timelapse / scheduler / Instagram。
  - Turso への event / status / config 同期。
  - hosted command queue の polling と MQTT publish。
- `Cloudflare Worker`
  - hosted API / UI。
  - Access JWT の検証。
  - Turso からの read。
  - device state / runtime config / firmware target / artifact metadata の write。
  - audit log 追記。
- `Turso`
  - hosted option で共有する device/event/config の source of truth。
  - local hub と hosted Worker の同期境界。
- `Cloudflare Access`
  - user authentication。
  - 許可 email による coarse-grained authorization。
  - Worker へ user identity token を渡す。

## 6. Repository Layout 案

Cloudflare Worker は Python hub と別 package として `hub/cloudflare/` に置く。

```text
hub/
  cloudflare/
    package.json
    wrangler.jsonc
    tsconfig.json
    src/
      index.ts
      access.ts
      db.ts
      routes/
        devices.ts
        events.ts
        firmware.ts
        health.ts
      repositories/
        device_records.ts
        device_events.ts
        audit_logs.ts
    migrations/
      0001_hosted_control_plane.sql
  scripts/
    cloudflare_access_setup.py
    cloudflare_tunnel_setup.sh
```

既存 Python 側は段階的に Turso schema へ合わせる。最初から Flask を置き換えない。

## 7. Environment Source of Truth

日本版環境で使用している `hub/.env` を正とする。値は secret を含むため repo / docs / logs に出さない。

Cloudflare Worker でも、既存 Python hub と同じキー名を使う。

- `TURSO_DATABASE_URL`
- `TURSO_AUTH_TOKEN`
- `S3_ENDPOINT_URL`
- `S3_BUCKET_NAME`
- `S3_BUCKET_REGION`
- `S3_ACCESS_KEY`
- `S3_SECRET_KEY`
- `S3_TMP_ENDPOINT_URL`
- `S3_TMP_BUCKET_NAME`
- `S3_TMP_BUCKET_REGION`
- `S3_TMP_ACCESS_KEY`
- `S3_TMP_SECRET_KEY`
- `S3_TMP_BASE_URL`

Cloudflare hosted option 用に追加するキーは、既存 `.env` に追記する。

- `CLOUDFLARE_HOSTED_PUBLIC_HOSTNAME`: Access application / Tunnel に使う公開 hostname。例: `hub.example.com`
- `CLOUDFLARE_ACCESS_TEAM_DOMAIN`: `https://<team-name>.cloudflareaccess.com`
- `CLOUDFLARE_ACCESS_POLICY_AUD`: Access application の Audience tag
- `CLOUDFLARE_ACCOUNT_ID`: Cloudflare account ID
- `CLOUDFLARE_ACCESS_GROUP_ID`: 許可 email rule group ID
- `CLOUDFLARE_ACCESS_APP_ID`: Access self-hosted application ID
- `CLOUDFLARE_ACCESS_POLICY_ID`: Access allow policy ID
- `CLOUDFLARE_ACCESS_APP_NAME`: Access application 名。既定: `inas-hub-hosted`
- `CLOUDFLARE_ACCESS_GROUP_NAME`: Access group 名。既定: `inas-hub-allowed-users`
- `CLOUDFLARE_ACCESS_POLICY_NAME`: Access policy 名。既定: `inas-hub-allow-email-group`
- `CLOUDFLARE_ACCESS_SESSION_DURATION`: Access session duration。既定: `4h`
- `CLOUDFLARE_ACCESS_ALLOWED_EMAILS`: 初期 provision 用の許可 email カンマ区切り
- `CLOUDFLARE_TUNNEL_NAME`: Tunnel 名。既定: `inas-hub`
- `CLOUDFLARE_TUNNEL_ID`: 作成済み Tunnel ID
- `CLOUDFLARE_TUNNEL_HOSTNAME`: Tunnel DNS route hostname
- `CLOUDFLARE_TUNNEL_ORIGIN_URL`: Tunnel の転送先 local URL。既定: `http://localhost:39151`
- `CLOUDFLARE_TUNNEL_TOKEN_FILE`: Tunnel token file path。既定: `hub/.data/cloudflare/tunnel-token`
- `CLOUDFLARE_TUNNEL_DNS_RECORD_ID`: Tunnel 用 DNS CNAME record ID
- `CLOUDFLARE_ZONE_ID`: DNS record を作る zone ID
- `CLOUDFLARE_ZONE_NAME`: DNS record を作る zone name
- `CLOUDFLARE_CLOUDFLARED_BIN`: `cloudflared` binary path

Cloudflare Access API token は local script / CI 用の secret として扱う。Worker には渡さない。

- `CLOUDFLARE_ACCESS_API_TOKEN`

Worker deploy 時は、`hub/.env` から Worker vars / secrets を登録する。Turso token や S3 secret は `wrangler secret put` で登録し、非 secret の URL / bucket 名 / Access audience は `wrangler.jsonc` vars または CI の環境変数から設定する。

## 8. 認証認可設計

### 8.1 Access application

Cloudflare Zero Trust に `inas-hub-hosted` Access application を作成する。

- public hostname: `hub.<domain>`。
- session duration: 初期値は 4-8 時間を推奨。運用上もっと短くできる場合は 1 時間。
- policy: `inas-hub-allowed-users` rule group に一致する user を Allow。
- IdP: まず One-time PIN または既存 IdP。組織 IdP があるならそちらを優先。

### 8.2 Worker 側 JWT 検証

Cloudflare Access で保護されていても、Worker 側で `Cf-Access-Jwt-Assertion` を検証する。

Worker env:

- `CLOUDFLARE_ACCESS_TEAM_DOMAIN`: `https://<team-name>.cloudflareaccess.com`
- `CLOUDFLARE_ACCESS_POLICY_AUD`: Access application の Audience tag

検証内容:

- header `cf-access-jwt-assertion` が存在する。
- JWKS は `${CLOUDFLARE_ACCESS_TEAM_DOMAIN}/cdn-cgi/access/certs` から取得する。
- `issuer == CLOUDFLARE_ACCESS_TEAM_DOMAIN`。
- `audience == CLOUDFLARE_ACCESS_POLICY_AUD`。
- payload の `email` を lowercase して `actor_email` として使う。

### 8.3 Application-level authorization

Access の email allowlist は入口の認可とする。Worker では追加で role を持つ。

初期 role:

- `reader`: GET のみ。
- `operator`: device config / firmware target の変更可。
- `admin`: user role table と destructive operation を操作可。

初期実装では `operator` 以上を手動 seed し、未登録 email は `reader` とするか 403 にする。推奨は 403。

Turso table 案:

```sql
CREATE TABLE IF NOT EXISTS admin_users (
  email TEXT PRIMARY KEY,
  role TEXT NOT NULL CHECK (role IN ('reader', 'operator', 'admin')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

## 9. 許可 email 追加・削除スクリプト

### 9.1 方針

Cloudflare Access の rule group `inas-hub-allowed-users` を許可 email の source of truth にする。script は Cloudflare API で group を read-modify-write する。

理由:

- Access application / policy 本体を変更せず、許可 email だけを一箇所で管理できる。
- 複数 application に同じ group を再利用できる。
- API payload が `include: [{ "email": { "email": "user@example.com" } }]` と単純。

### 9.2 環境変数

script の実行環境にだけ設定する。Worker には置かない。

- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_ACCESS_API_TOKEN`
- `CLOUDFLARE_HOSTED_PUBLIC_HOSTNAME`
- `CLOUDFLARE_ACCESS_GROUP_ID`
- `CLOUDFLARE_ACCESS_APP_ID`
- `CLOUDFLARE_ACCESS_POLICY_ID`
- `CLOUDFLARE_ACCESS_ALLOWED_EMAILS`
- `CLOUDFLARE_TUNNEL_NAME`
- `CLOUDFLARE_TUNNEL_HOSTNAME`
- `CLOUDFLARE_TUNNEL_ORIGIN_URL`

API token permissions:

- rule group 読み書き: `Access: Organizations, Identity Providers, and Groups Read/Write`
- application / policy 読み書き: `Access: Apps and Policies Read/Write`
- tunnel 作成・token 取得・remote config 更新: `Cloudflare Tunnel Edit`
- DNS CNAME 作成・更新: zone scope の `Zone > DNS > Read` と `Zone > DNS > Edit`。Cloudflare DNS record 作成 API の accepted permission は `DNS Write`。
- token resource scope: 固定する Cloudflare account

Account-owned token でも利用できる。account-owned token は user token 用の `/user/tokens/verify` では検証せず、`scripts/cloudflare_access_setup.py check` で Access API への到達性を確認する。

### 9.3 コマンド仕様

実装 script:

```bash
cd hub

# Access group / self-hosted application / allow policy を作成し、生成 ID を .env に追記する
python3 scripts/cloudflare_access_setup.py --write-env provision \
  --email alice@example.com

# 許可 email の確認・追加・削除
python3 scripts/cloudflare_access_setup.py list
python3 scripts/cloudflare_access_setup.py add bob@example.com
python3 scripts/cloudflare_access_setup.py remove bob@example.com

# file を正として allowlist を置換する
python3 scripts/cloudflare_access_setup.py apply ./allowed-emails.txt --yes
```

動作仕様:

- email は lowercase / trim / basic email validation を行う。
- `add` は idempotent。既存 email は成功扱い。
- `remove` は idempotent。存在しない email は成功扱い。
- `apply` は file を正として Cloudflare rule group を置換する。実行前に差分を表示し、`--yes` がない場合は確認を要求する。
- 更新前に group JSON の backup を `hub/.data/cloudflare-access-backups/` へ保存する。ただし token は保存しない。
- `--write-env` を付けると、`CLOUDFLARE_ACCESS_TEAM_DOMAIN` / `CLOUDFLARE_ACCESS_POLICY_AUD` / `CLOUDFLARE_ACCESS_GROUP_ID` / `CLOUDFLARE_ACCESS_APP_ID` / `CLOUDFLARE_ACCESS_POLICY_ID` を `.env` に追記・更新する。
- `wrangler` は Workers deploy 用に使う。Cloudflare Access application / policy / group は `wrangler` の管理対象ではないため、`scripts/cloudflare_access_setup.py` は Cloudflare Zero Trust API を直接呼ぶ。

### 9.4 active session の扱い

email を削除しても、既存 application token の有効期限まではアクセスが残る可能性がある。緊急削除では以下を運用手順に含める。

1. script で email を rule group から削除する。
2. Cloudflare Access の per-user revoke を行う。
3. 必要に応じて application の existing tokens を revoke する。

このため、初期の application / policy session duration は長くしすぎない。

### 9.5 Cloudflare Tunnel 作成・起動スクリプト

Cloudflare Tunnel は Cloudflare API で remotely-managed tunnel として作成する。`cloudflared tunnel login` は不要。起動時は API で取得した tunnel token を使う。

```bash
cd hub

# Access / Tunnel / DNS をまとめて構築する
bash scripts/cloudflare_hosted_setup.sh --install-cloudflared

# local hub と tunnel を foreground でまとめて起動する
bash scripts/cloudflare_hosted_up.sh --install-cloudflared

# tunnel だけ起動する
bash scripts/cloudflare_tunnel_start.sh
```

script の動作:

- Access group / application / policy を作成または再利用する。
- Cloudflare Tunnel を作成または再利用し、remote ingress config を `CLOUDFLARE_TUNNEL_HOSTNAME -> CLOUDFLARE_TUNNEL_ORIGIN_URL` に設定する。
- Tunnel token を `hub/.data/cloudflare/tunnel-token` に `0600` で保存する。token は標準出力に出さない。
- zone を hostname から自動探索し、`<tunnel-id>.cfargotunnel.com` への proxied CNAME を作成または更新する。
- `cloudflared` がない場合は `--install-cloudflared` で `hub/.data/bin/cloudflared` にダウンロードする。
- `cloudflare_hosted_up.sh` は local hub と tunnel を同時に起動し、Cloudflare 経由で local hub の機能を使える状態にする。
- `cloudflare_hosted_up.sh` は local hub の起動直後の終了を検知したら tunnel を開始しない。実行中に local hub または tunnel のどちらかが終了した場合は、もう片方も停止する。

`cloudflare_hosted_up.sh` は通常の local hub と同じ実行条件を前提にする。`WORK_DIR` / `LOCAL_STORAGE_BASE_DIR` が書き込み可能で、MQTT broker など `.env` の接続先へ到達できる必要がある。

初期 hosted option のリソース作成 script が管理する Cloudflare resource は以下。

- Access group: 許可 email rule group。
- Access application: self-hosted application。
- Access policy: group を include する allow policy。
- Cloudflare Tunnel: remotely-managed tunnel。
- Cloudflare Tunnel configuration: public hostname ingress。
- Cloudflare Tunnel token: local token file として保存。
- DNS record: Tunnel 向け proxied CNAME。
- local helper binary: 必要に応じて `hub/.data/bin/cloudflared`。

idempotency / guard:

- `.env` に ID がある resource は ID を優先して再利用する。
- ID がない場合は名前または hostname で既存 resource を検索し、完全一致が 1 件なら再利用する。
- 同名 Access group / Access application / Access policy / Tunnel が複数ある場合は自動選択せず停止する。
- Access group / Access policy は内容が一致していれば PUT しない。
- Tunnel は remotely-managed tunnel のみ対象とし、locally-managed tunnel を同名で見つけた場合は停止する。
- DNS は non-CNAME が同じ hostname に存在する場合は停止する。
- 既存 CNAME が別 target で、`CLOUDFLARE_TUNNEL_DNS_RECORD_ID` または managed comment がない場合は上書きしない。
- setup / up script は lock file を使い、同一 workspace での二重実行を拒否する。

## 10. Turso Schema 方針

既存実装は device config を `WORK_DIR/.device_configs.json`、event を Turso + JSONL fallback に保存している。hosted option では device config / status / OTA target も Turso に寄せる。

初期 migration 案:

```sql
CREATE TABLE IF NOT EXISTS device_records (
  device_id TEXT PRIMARY KEY,
  state TEXT NOT NULL CHECK (state IN ('pending', 'active', 'disabled', 'retired')),
  name TEXT,
  location TEXT,
  memo TEXT,
  device_kind TEXT,
  firmware_version TEXT,
  target_firmware_version TEXT,
  config_json TEXT NOT NULL,
  runtime_config_json TEXT NOT NULL,
  last_seen_at TEXT,
  last_config_request_at TEXT,
  last_status_at TEXT,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS firmware_artifacts (
  version TEXT PRIMARY KEY,
  device_kind TEXT NOT NULL,
  url TEXT NOT NULL,
  sha256 TEXT,
  size_bytes INTEGER,
  metadata_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS device_commands (
  command_id TEXT PRIMARY KEY,
  device_id TEXT NOT NULL,
  command_type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('pending', 'published', 'acked', 'failed', 'cancelled')),
  requested_by TEXT NOT NULL,
  requested_at TEXT NOT NULL,
  published_at TEXT,
  completed_at TEXT,
  error TEXT
);

CREATE TABLE IF NOT EXISTS hosted_audit_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  occurred_at TEXT NOT NULL,
  actor_email TEXT NOT NULL,
  action TEXT NOT NULL,
  target_type TEXT NOT NULL,
  target_id TEXT,
  request_json TEXT,
  result_json TEXT
);
```

既存 `device_events` table は流用する。JSON column は初期段階では `TEXT` とし、Worker/Python の両方で `JSON.stringify` / `json.dumps` する。SQLite JSON functions に依存した query は後回しにする。

## 11. Hosted API 方針

prefix は `/api`。既存 local API の `/local/api` は local hub 専用として残す。

初期 GET:

- `GET /api/health`
- `GET /api/mqtt-events?device_id=&limit=`
- `GET /api/mqtt-connections?device_id=&limit=`
- `GET /api/mqtt-devices`
- `GET /api/mqtt-devices/:deviceId`
- `GET /api/mqtt-devices/:deviceId/runtime-config`
- `GET /api/mqtt-devices/:deviceId/statuses`
- `GET /api/mqtt-devices/:deviceId/ota-statuses`
- `GET /api/firmware-artifacts`

初期 write:

- `PATCH /api/mqtt-devices/:deviceId`
- `POST /api/mqtt-devices/:deviceId/approve`
- `POST /api/mqtt-devices/:deviceId/disable`
- `POST /api/mqtt-devices/:deviceId/retire`
- `PUT /api/mqtt-devices/:deviceId/runtime-config`
- `POST /api/mqtt-devices/:deviceId/runtime-config/push`
- `PUT /api/mqtt-devices/:deviceId/firmware-target`
- `PUT /api/firmware-artifacts/:version`

`runtime-config/push` は Worker から MQTT publish しない。`device_commands` に `command_type='runtime_config_push'` を作り、local hub が polling して publish する。

## 12. Local Hub 側の変更方針

段階的に進める。

1. `DeviceConfigRepository` の backend を追加する。
   - `json_file`: 現行。
   - `turso`: hosted option 用。
2. `device_event_log` の Turso schema を Worker と共有できるように migration 管理する。
3. local hub に command polling task を追加する。
   - interval: 初期 10 秒。
   - `pending` command を取得。
   - MQTT publish 成功で `published`。
   - device ack / status を受けたら `acked`。
4. local API はそのまま残す。
5. hosted option 有効時でも local UI は fallback として使えるようにする。

追加 env 案:

- `HOSTED_CONTROL_PLANE_ENABLED=false`
- `HOSTED_COMMAND_POLL_INTERVAL_SECONDS=10`
- `DEVICE_CONFIG_REPOSITORY_BACKEND=json_file|turso`

## 13. Security / Operations

- Worker secrets:
  - `TURSO_AUTH_TOKEN`
  - `S3_ACCESS_KEY`
  - `S3_SECRET_KEY`
  - `S3_TMP_ACCESS_KEY`
  - `S3_TMP_SECRET_KEY`
- Worker vars:
  - `TURSO_DATABASE_URL`
  - `CLOUDFLARE_ACCESS_TEAM_DOMAIN`
  - `CLOUDFLARE_ACCESS_POLICY_AUD`
  - `S3_ENDPOINT_URL`
  - `S3_BUCKET_NAME`
  - `S3_BUCKET_REGION`
  - `S3_TMP_ENDPOINT_URL`
  - `S3_TMP_BUCKET_NAME`
  - `S3_TMP_BUCKET_REGION`
  - `S3_TMP_BASE_URL`
- script secrets:
  - `CLOUDFLARE_ACCESS_API_TOKEN`
- script vars:
  - `CLOUDFLARE_ACCOUNT_ID`
  - `CLOUDFLARE_HOSTED_PUBLIC_HOSTNAME`
  - `CLOUDFLARE_ACCESS_GROUP_ID`
  - `CLOUDFLARE_ACCESS_APP_ID`
  - `CLOUDFLARE_ACCESS_POLICY_ID`
  - `CLOUDFLARE_TUNNEL_NAME`
  - `CLOUDFLARE_TUNNEL_HOSTNAME`
  - `CLOUDFLARE_TUNNEL_ORIGIN_URL`
  - `CLOUDFLARE_TUNNEL_TOKEN_FILE`
  - `CLOUDFLARE_TUNNEL_DNS_RECORD_ID`
  - `CLOUDFLARE_ZONE_ID`
  - `CLOUDFLARE_ZONE_NAME`
  - `CLOUDFLARE_CLOUDFLARED_BIN`

運用ルール:

- Cloudflare API token は local `.env` または CI secret に置く。repo に保存しない。
- Worker は Cloudflare API token を持たない。
- all write API は `actor_email` を audit log に残す。
- destructive operation は POST/DELETE でも audit log と request id を必須にする。
- `runtime-config` の schema validation は Python と TypeScript で同じ制約にする。共有 JSON Schema を置くか、TypeScript 側に最小 validator を実装する。

## 14. 実装ステップ

### Phase 0: 方針確定

- この文書を review する。
- hosted option の初期対象 API を確定する。
- domain / Cloudflare account / Turso database の運用単位を決める。

### Phase 1: Cloudflare Worker scaffold

- `hub/cloudflare` を追加する。
- Hono + `@libsql/client` + `jose` + Vitest を導入する。
- `GET /api/health` と Access JWT middleware を実装する。
- `wrangler dev` で local 動作確認する。

### Phase 2: Access allowlist scripts

- `scripts/cloudflare_access_setup.py` で Access group / application / policy を provision する。
- `list/add/remove/apply` を idempotent にする。
- dry-run と backup を実装する。
- README / operations に token permissions と緊急 revoke 手順を書く。
- `scripts/cloudflare_tunnel_setup.py` で remotely-managed Cloudflare Tunnel / token / remote ingress config / DNS CNAME を作成する。
- `scripts/cloudflare_hosted_setup.sh` と `scripts/cloudflare_hosted_up.sh` で、`.env` だけから hosted option を構築・起動できる入口を提供する。

### Phase 3: read-only hosted API

- Turso の `device_events` を read する endpoint を実装する。
- `device_records` read を実装する。
- hosted UI は最小 dashboard から開始する。

### Phase 4: shared state migration

- device config / OTA artifact / firmware target を Turso schema に移す。
- local hub は `json_file` と `turso` backend を切替可能にする。
- migration script で `.device_configs.json` から Turso へ import する。

### Phase 5: write API and command queue

- hosted write API を実装する。
- local hub の command polling を実装する。
- `runtime-config/push` は command queue 経由で publish する。
- audit log と request id を通す。

### Phase 6: hardening

- rate limit / request body size guard。
- schema validation。
- integration tests。
- Cloudflare deployment docs。
- session revoke 手順を運用ガイドへ追加。

## 15. Test Plan

Worker:

- Access JWT middleware:
  - header なしは 403。
  - invalid audience は 403。
  - valid JWT は `actor_email` を context に入れる。
- API:
  - read endpoint は limit 上限を守る。
  - write endpoint は role 不足で 403。
  - write 成功時に audit log が残る。
- allowlist script:
  - add/remove は idempotent。
  - apply は file を正として置換する。
  - malformed email は失敗する。

Python local hub:

- 既存 `PYTHONPATH=src python -m unittest discover -s tests`。
- `DeviceConfigRepository` backend 切替。
- command polling:
  - pending command を publish する。
  - publish 失敗時に retry / failed へ遷移する。
  - disabled/retired device へ危険な command を送らない。

Manual:

- 許可 email で hosted UI に入れる。
- 削除 email は session expiration / revoke 後に入れない。
- hosted runtime config 更新後、device config request で local hub が新 config を返す。

## 16. Open Questions

- Cloudflare Access IdP は One-time PIN で開始するか、組織 IdP を使うか。
- hosted UI は API-first の簡素な画面から始めるか、既存 Flask UI と同等の画面を目指すか。
- S3/R2 上の画像閲覧を hosted UI 初期対象に含めるか。
- device config の source of truth をいつ `.device_configs.json` から Turso に切り替えるか。
- 緊急 revoke を script から Cloudflare API で自動化するか、dashboard 運用にするか。
