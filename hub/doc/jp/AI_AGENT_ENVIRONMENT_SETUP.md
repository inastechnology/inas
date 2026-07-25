# AI Agent 向け環境構築ガイド

この文書は、AI Agent が `ina-device-hub` の環境構築や Cloudflare hosted option のセットアップを担当する時の作業手順と判断基準をまとめる。人間向けの環境変数一覧は `doc/ENVIRONMENT.md`、Cloudflare hosted option の設計方針は `doc/CLOUDFLARE_HOSTED_OPTION.md` を参照する。

## 基本方針

- 日本版環境では `hub/.env` を source of truth とする。
- `.env`、token、secret、tunnel token の値をチャット、ログ、コミット、docs に出さない。
- `.default.env` はキー一覧と既定値のテンプレートとして扱い、実値の正にはしない。
- 既存 `.env` を大きく書き換えない。生成済み ID の追記・更新は用意済み script の `--write-env` に任せる。
- Cloudflare resource は Dashboard で手作業作成せず、idempotent script を使う。
- 同名 resource や既存 DNS record の衝突で script が停止したら、勝手に削除・上書きせず、停止理由をユーザーへ報告する。
- local hub の起動条件と Cloudflare tunnel の起動条件を分けて切り分ける。

## 触ってよいもの・触らないもの

触ってよいもの:

- `hub/.default.env` のキー追加・説明調整。
- `hub/doc/` の手順書・設計書。
- `hub/scripts/cloudflare_*.py` / `hub/scripts/cloudflare_*.sh` の idempotent な改善。
- `hub/.env` の Cloudflare 生成 ID 追記。ただし script の `--write-env` を優先する。

触らないもの:

- `.env` の secret 値の表示・要約・コミット。
- `hub/.data/cloudflare/tunnel-token` の表示・コミット。
- Cloudflare resource の削除。
- ユーザーが作成した unrelated な git 差分。
- 実運用 `.env` の storage path や MQTT 接続先を、検証都合だけで恒久変更すること。

## 最初に確認すること

```bash
cd hub
git status --short
test -f .env
```

`.env` がない場合は対話式CLIで作る。実値はユーザーまたは secret 管理から取得する。

```bash
uv run ina-hub install
```

`.env` の値を確認する必要がある場合は、値ではなくキーの存在だけを見る。

```bash
python3 - <<'PY'
from pathlib import Path
for line_no, line in enumerate(Path(".env").read_text().splitlines(), 1):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key = line.split("=", 1)[0].strip()
    if key.startswith(("CLOUDFLARE_", "TURSO_", "S3_", "MQTT_")):
        print(f"{key}: line {line_no}")
PY
```

## ローカル起動の前提

local hub は通常の `uv run python src/ina_device_hub/serve.py` と同じ条件で起動する。

- `WORK_DIR` が書き込み可能。
- `LOCAL_STORAGE_BASE_DIR` が書き込み可能。
- `TURSO_DATABASE_URL`と`TURSO_AUTH_TOKEN`がこのLocal Hub用として有効である。
- `S3_*` が有効。
- `MQTT_BROKER_URL` / `MQTT_BROKER_PORT` に到達できる。
- `TIMELAPSE_INTERVAL` など `setting.py` が必須として読む値が設定されている。

restricted な Agent 実行環境では、`~/.ina-device-hub` など `$HOME` 配下へ書けないことがある。その場合は実運用 `.env` を変更せず、検証コマンドだけで workspace 内へ override する。

```bash
env \
  WORK_DIR="$PWD/.data/work" \
  LOCAL_STORAGE_BASE_DIR="$PWD/.data/storage" \
  uv run python src/ina_device_hub/serve.py
```

MQTT broker が起動していない環境でもHTTPプロセスは起動し、再接続を継続する。この間は`/healthz`が200、`/readyz`が503になる。MQTT停止はCloudflare設定とは別問題として扱う。

## Cloudflare Tunnelの低レベルenv

最低限、`.env` に保存する非secret値:

- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_HOSTED_PUBLIC_HOSTNAME`
- `CLOUDFLARE_ACCESS_ALLOWED_EMAILS`

`CLOUDFLARE_ACCESS_API_TOKEN`は低レベルprovisioning実行時のprocess環境だけで
渡し、出荷機器の`.env`へ保存しない。

script が生成・補完する値:

- `CLOUDFLARE_ACCESS_TEAM_DOMAIN`
- `CLOUDFLARE_ACCESS_POLICY_AUD`
- `CLOUDFLARE_ACCESS_GROUP_ID`
- `CLOUDFLARE_ACCESS_APP_ID`
- `CLOUDFLARE_ACCESS_POLICY_ID`
- `CLOUDFLARE_TUNNEL_ID`
- `CLOUDFLARE_TUNNEL_TOKEN_FILE`
- `CLOUDFLARE_TUNNEL_DNS_RECORD_ID`
- `CLOUDFLARE_ZONE_ID`
- `CLOUDFLARE_ZONE_NAME`

API token に必要な権限:

- Account: `Access: Apps and Policies Read/Write`
- Account: `Access: Organizations, Identity Providers, and Groups Read/Write`
- Account: `Cloudflare Tunnel Edit`
- Zone: `Zone > DNS > Read`
- Zone: `Zone > DNS > Edit`

Cloudflare DNS record 作成 API の accepted permission は `DNS Write`。`check` は DNS read までを確認し、DNS write は `provision` 時に実際の CNAME 作成・更新で確認される。

## Cloudflare setup 手順

Local Hubを手動保守する場合は次の一括scriptを使用できる。

```bash
cd hub
bash scripts/cloudflare_hosted_setup.sh --install-cloudflared
```

この script は以下を作成または再利用する。

- Cloudflare Access group
- Cloudflare Access self-hosted application
- Cloudflare Access allow policy
- Cloudflare Tunnel
- Tunnel remote ingress config
- Tunnel token file
- proxied DNS CNAME
- local `cloudflared` binary

再実行してよい。`.env` の ID を優先し、既存 resource が同じ内容なら no-op になる。

確認だけ行う場合:

```bash
python3 scripts/cloudflare_access_setup.py check
python3 scripts/cloudflare_tunnel_setup.py check
```

dry-run で書き込み request を確認する場合:

```bash
python3 scripts/cloudflare_access_setup.py --dry-run provision
python3 scripts/cloudflare_tunnel_setup.py --dry-run provision
```

## Cloudflare 起動手順

現場デバイスでは systemd 管理を標準にする。`cloudflare_tunnel_daemon.sh` は手動切り分け用で、常駐運用には使わない。

Cloudflare hosted setup 後、hub と tunnel の systemd unit を配置して有効化する。

```bash
cd hub
sudo scripts/install_service.sh --target-dir "$PWD" --enable-cloudflare-tunnel
```

この script は以下を行う。

- `systemd/inas-device-hub@.service` を `/etc/systemd/system/inas-device-hub@.service` に配置する。
- `systemd/inas-cloudflare-tunnel.service` を `/etc/systemd/system/inas-cloudflare-tunnel.service` に配置する。
- unit template 内の `@@INAS_HUB_DIR@@` / `@@INAS_HUB_USER@@` を対象デバイスの install path と実行 user に置換する。
- `inas-device-hub@main.service` を enable/start する。
- `inas-cloudflare-tunnel.service` を enable/start する。

systemd unit では `WorkingDirectory` に shell のような環境変数展開を期待しない。install path は `.env` ではなく、`scripts/install_service.sh --target-dir ...` で unit 生成時に埋め込む。

Cloudflare Tunnel service は `scripts/cloudflare_tunnel_setup.py --env-file .env start` を systemd の `Restart=always` で起動する。事前に `scripts/cloudflare_hosted_setup.sh --install-cloudflared` または `scripts/cloudflare_tunnel_setup.py --write-env provision` を実行し、`.env` と `hub/.data/cloudflare/tunnel-token` を作成しておく。

systemd 状態確認:

```bash
systemctl status inas-device-hub@main.service --no-pager
systemctl status inas-cloudflare-tunnel.service --no-pager
journalctl -u inas-cloudflare-tunnel.service -f
```

Cloudflare Tunnel の origin port を変更した場合は、`.env` の `HUB_HTTP_PORT` と `CLOUDFLARE_TUNNEL_ORIGIN_URL` を合わせ、hub service を再起動し、Cloudflare remote config を再 provision する。

```bash
sudo systemctl restart inas-device-hub@main.service
python3 scripts/cloudflare_tunnel_setup.py --env-file .env --write-env provision
sudo systemctl restart inas-cloudflare-tunnel.service
```

local hub と tunnel を systemd ではなく一時的に foreground 起動する場合だけ、次の手順を使う。

local hub と tunnel をまとめて foreground 起動する。

```bash
bash scripts/cloudflare_hosted_up.sh --install-cloudflared
```

`cloudflare_hosted_up.sh` の挙動:

- setup を先に実行する。
- local hub を起動する。
- local hub が起動直後に終了した場合、tunnel は開始しない。
- 起動後に local hub または tunnel のどちらかが終了した場合、もう片方も停止する。
- 初期終了検知の待ち時間は `CLOUDFLARE_HOSTED_HUB_STARTUP_WAIT_SECONDS` で調整できる。既定は `3` 秒。

tunnel だけ起動する場合:

```bash
bash scripts/cloudflare_tunnel_start.sh
```

foreground を占有せず tunnel だけ手動常駐させる場合:

```bash
bash scripts/cloudflare_tunnel_daemon.sh --install-cloudflared start
bash scripts/cloudflare_tunnel_daemon.sh status
bash scripts/cloudflare_tunnel_daemon.sh logs
bash scripts/cloudflare_tunnel_daemon.sh stop
```

AI Agent の sandbox 内では PID namespace の違いで `cloudflare_tunnel_daemon.sh status` が stale pid と誤判定することがある。運用確認は systemd の `systemctl status` / `journalctl` を優先する。

公開 hostname が Cloudflare Access で保護されているか確認する。

```bash
curl -I --max-time 15 "https://<CLOUDFLARE_HOSTED_PUBLIC_HOSTNAME>"
```

未ログイン状態では `302` で `*.cloudflareaccess.com` の login URL へ redirect されればよい。

## 許可 email の管理

Cloudflare Dashboard ではなく script で管理する。

```bash
python3 scripts/cloudflare_access_setup.py list
python3 scripts/cloudflare_access_setup.py add user@example.com
python3 scripts/cloudflare_access_setup.py remove user@example.com
python3 scripts/cloudflare_access_setup.py apply allowed-emails.txt --yes
```

`remove` と `apply` は allowlist が空になる操作を拒否する。

## よくある失敗と判断

`Missing required env value`

- `.env` に必要なキーがない。`.default.env` と `doc/ENVIRONMENT.md` を見て不足キーをユーザーへ提示する。

Cloudflare Access check は通るが DNS 作成で `HTTP 403`

- 対象 zone への `Zone > DNS > Edit` が token に効いていない。
- token の resource scope が対象 zone になっているか確認してもらう。

`DNS record already exists with non-CNAME`

- 同じ hostname に A / AAAA / MX / TXT などがある。
- script は上書きしない。別 hostname を使うか、ユーザー判断で既存 DNS を整理してもらう。

`Multiple CNAME records already exist`

- 対象 record を一意に選べない。
- `CLOUDFLARE_TUNNEL_DNS_RECORD_ID` を設定するか、Cloudflare 側で重複を整理してもらう。

Cloudflare Error 1033

- Access や DNS ではなく、Cloudflare Tunnel connector が動いていない可能性が高い。
- `bash scripts/cloudflare_tunnel_daemon.sh status` で `cloudflared` が running か確認する。
- stopped の場合は `bash scripts/cloudflare_tunnel_daemon.sh --install-cloudflared start` を実行する。
- connector が running でも origin が落ちている場合は 1033 ではなく、origin connection error 側へ変わることがある。

local hub が `Read-only file system` で落ちる

- Agent 実行環境の書き込み制限であることが多い。
- 実運用 `.env` を変更せず、検証コマンドだけ `WORK_DIR` / `LOCAL_STORAGE_BASE_DIR` を workspace 内に override する。

local hub の `/readyz` がMQTT未接続で503になる

- MQTT broker が起動していない、または `.env` の接続先へ到達できない。
- Hubは終了せず再接続する。broker復旧後に`/readyz`が200へ戻ることを確認する。
- Cloudflare tunnel の問題ではない。

`cloudflared` の ICMP proxy warning

- tunnel の HTTP forwarding 自体は動くことが多い。
- QUIC / TCP connectivity pre-check が PASS なら、通常は blocker にしない。

## 検証 checklist

コード・script の構文:

```bash
python3 -m py_compile scripts/cloudflare_access_setup.py scripts/cloudflare_tunnel_setup.py
bash -n scripts/cloudflare_tunnel_setup.sh scripts/cloudflare_tunnel_start.sh scripts/cloudflare_hosted_setup.sh scripts/cloudflare_hosted_up.sh
```

lint / format:

```bash
.venv/bin/ruff check scripts/cloudflare_access_setup.py scripts/cloudflare_tunnel_setup.py --diff
.venv/bin/ruff format scripts/cloudflare_access_setup.py scripts/cloudflare_tunnel_setup.py --check --diff
```

差分の空白:

```bash
git diff --check
```

Cloudflare 外形確認:

```bash
python3 scripts/cloudflare_access_setup.py audit
python3 scripts/cloudflare_tunnel_setup.py check
curl -I --max-time 15 "https://<CLOUDFLARE_HOSTED_PUBLIC_HOSTNAME>"
```

## ユーザーへ確認すべき時

- API token に不足権限がある。
- 既存 DNS record と衝突している。
- 同名 Cloudflare resource が複数存在する。
- Cloudflare resource を削除・統合する必要がある。
- `.env` の secret 値が不足していて、Agent から取得できない。
- local hub の端末内DB / MQTT / S3接続が失敗する。任意のremote Turso replicaを設定した既存導入先では、その接続が不明または停止している。

## 完了報告で伝えること

- 作成・再利用された Cloudflare resource の種類。
- 再実行時に no-op になることを確認したか。
- public hostname が Access redirect を返したか。
- local hub が起動できたか。できない場合は Cloudflare と local 依存のどちらで止まったか。
- 実行した検証コマンド。

secret 値、token 値、`.env` 全文は報告しない。
