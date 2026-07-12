# Cloudflare Cloud App 実装方針

作成日: 2026-07-01

## 1. 位置づけ

この文書は、`ina-device-hub` のクラウド版アプリを Cloudflare Workers + Hono + Turso で実装するための方針と、現在の実装範囲をまとめる。

既存の `doc/CLOUDFLARE_HOSTED_OPTION.md` は Cloudflare Access + Tunnel で local hub を公開する選択肢も含む。ここで扱うクラウド版アプリは Tunnel ではなく、Worker 上で動く HTTP API / 管理 UI の土台である。Tunnel はデバイス側で local hub を外部公開するための手段であり、クラウド版 Worker の実行には不要。

## 2. 初期スコープ

初期実装は、local hub の全機能を Workers へ移植しない。Worker に載せるのは、Turso 上の共有データを読む/更新する管理 API から始める。

- Cloudflare Access JWT の検証。
- `admin_users` による Worker 内のロール判定。
- `device_events` の一覧取得。
- `device_events` への管理イベント追加。
- `audit_logs` への操作記録。
- Turso schema migration の雛形。
- 認証、認可、入力検証、監査ログのテスト。

次は初期スコープ外とする。

- MQTT broker の常時 subscribe / publish。
- RTSP camera、ffmpeg、timelapse、Instagram 投稿。
- local `WORK_DIR` 配下の JSON、画像、ログへの直接アクセス。
- Worker から device へ直接 MQTT publish すること。

device への即時反映は、後続で Turso 上に command queue を置き、local hub が polling して MQTT publish する構成にする。

## 3. アーキテクチャ

```text
Browser / Admin client
  -> Cloudflare Access
  -> Cloudflare Worker (Hono)
  -> Turso/libSQL
  <- local hub sync / polling
  -> MQTT broker / devices
```

役割分担:

- `Cloudflare Access`
  - ユーザー認証。
  - 許可 email の入口制御。
  - Worker へ `Cf-Access-Jwt-Assertion` を渡す。
- `Cloudflare Worker`
  - Access JWT の `issuer` / `audience` / `email` を検証する。
  - `admin_users` で `reader` / `operator` / `admin` を判定する。
  - Turso の管理 API を公開する。
- `Turso`
  - local hub と Worker の同期境界。
  - event、状態、設定、将来の command queue を保持する。
- `local hub`
  - MQTT、camera、scheduler、storage 連携など、常駐プロセス前提の処理を担当する。

## 4. 実装レイアウト

Worker 実装は Python hub と分離し、`hub/cloudflare/` に置く。

```text
hub/cloudflare/
  package.json
  wrangler.jsonc
  tsconfig.json
  vitest.config.ts
  migrations/
    0001_cloud_control_plane.sql
  src/
    index.ts
    access.ts
    db.ts
    routes/
      events.ts
      health.ts
    repositories/
      admin-users.ts
      audit-logs.ts
      device-events.ts
  test/
    access.test.ts
    app.test.ts
    db.test.ts
```

## 5. 認証認可

入口は Cloudflare Access を正とする。Worker 側でも Access JWT を検証し、Access の設定ミスや迂回に備える。

Worker が使う env:

- `CLOUDFLARE_ACCESS_TEAM_DOMAIN`
- `CLOUDFLARE_ACCESS_POLICY_AUD`
- `TURSO_DATABASE_URL`
- `TURSO_AUTH_TOKEN`

`CLOUDFLARE_ACCESS_API_TOKEN` は resource 作成スクリプト用の secret であり、Worker には渡さない。

認可は二段階にする。

1. Cloudflare Access group: 許可 email の粗い入口制御。
2. Turso `admin_users`: アプリ内ロール制御。

ロール:

- `reader`: 読み取りのみ。
- `operator`: 管理イベント作成など、通常操作が可能。
- `admin`: 後続でユーザー/設定管理を許可する想定。

## 6. Turso schema

初期 migration は次を作成する。

- `device_events`: 既存 Python hub の event log schema と互換にする。
- `admin_users`: cloud app のロール割当。
- `audit_logs`: Worker からの変更操作を記録。

初期 admin user は手動 SQL で追加する。

```sql
INSERT INTO admin_users (email, role)
VALUES ('admin@example.com', 'admin')
ON CONFLICT(email) DO UPDATE SET role = excluded.role, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now');
```

将来は `scripts/cloudflare_access_setup.py` と同じ思想で、admin user の追加/削除も idempotent な CLI に寄せる。

## 7. URL と Tunnel の切り分け

`CLOUDFLARE_HOSTED_PUBLIC_HOSTNAME` を Tunnel に割り当てている場合、その hostname は local hub への入口であり、Worker の URL ではない。同じ hostname を Tunnel と Worker custom domain に同時利用しない。

推奨:

- local hub over Tunnel: `hub.example.com`
- cloud app Worker: `hub-cloud.example.com`

Worker の deploy 直後は `workers.dev` の URL でも動くが、Access で保護する本番運用では Cloudflare 管理下の custom hostname を割り当てる。

## 8. 開発と検証

初期実装の確認コマンド:

```bash
cd hub/cloudflare
npm install
npm test
npm run typecheck
```

local dev server:

```bash
cd hub/cloudflare
npm run dev
```

本番 deploy 前には Turso migration と Worker env/secrets を設定する。

```bash
cd hub/cloudflare
# Turso 側で migrations/0001_cloud_control_plane.sql を適用
# TURSO_AUTH_TOKEN は wrangler secret として登録
npx wrangler secret put TURSO_AUTH_TOKEN
npm run deploy
```

`TURSO_DATABASE_URL`、`CLOUDFLARE_ACCESS_TEAM_DOMAIN`、`CLOUDFLARE_ACCESS_POLICY_AUD` は secret ではないが、環境差分を避けるため `.env` を source of truth として登録する。自動化スクリプトは後続で追加し、secret を標準出力へ出さない。

## 9. テスト方針

手戻りを減らすため、初期実装では DB や Cloudflare へ実接続しないユニットテストを先に置く。

- `/api/health` は Access JWT なしで通る。
- `/api/me` は JWT なしなら `401`。
- JWT が有効でも `admin_users` 未登録なら `403`。
- `reader` は event 一覧を読める。
- `reader` は event 作成できない。
- `operator` は event 作成でき、audit log が追加される。
- Access issuer 正規化と JSON payload 変換を個別テストする。

外部接続テストは、Turso database と Cloudflare Access application が固定できてから別レイヤーで追加する。

## 10. 今後の実装順

1. Worker API の deploy 手順を `.env` 起点で自動化する。
2. `admin_users` 管理 CLI を追加する。
3. device status / config / firmware target の Turso schema と API を追加する。
4. local hub が Turso command queue を polling する。
5. 管理 UI を Hono API の上に追加する。
6. Cloudflare Access session revoke を運用スクリプト化する。

## 11. 参考

- Cloudflare Workers + Turso: https://developers.cloudflare.com/workers/tutorials/connect-to-turso-using-workers/
- Hono Cloudflare Workers: https://hono.dev/docs/getting-started/cloudflare-workers
- Cloudflare Access JWT validation: https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/
