# ina-device-hub

英語版: [../../README.md](../../README.md)

この文書のコマンド例は、特記がない限り `hub/` ディレクトリで実行します。

検討中・一部提供・条件待ちの機能とコミュニティ提案の入口は [INAS 将来機能・コミュニティ提案一覧](../../../docs/jp/FUTURE_FEATURES.md) を参照してください。

AI Searchの現在の利用状態と、再開前に必要な再設計は [AI Search文書検索の現状](AI_SEARCH_OPERATIONS.md) を参照してください。

ina-device-hub は、MQTT で受信したセンサーデータやカメラ画像を集約し、ローカル／クラウドへ保存・連携する
軽量な IoT ハブです（Turso/libSQL、S3互換ストレージ対応、Flask による簡易 Web 表示、タイムラプス等）。

hub と client device を横断した全体仕様は [../../../docs/jp/SYSTEM_SPECIFICATION.md](../../../docs/jp/SYSTEM_SPECIFICATION.md) を参照してください。Cloudflare、デバイス種別、圃場データ、OTA の関係を図付きでまとめています。

Local Hubを親・子の両方として動かし、Edge Gatewayや下位Local Hubを集約する
構成、one-time credential、Sync v1 API、上位停止時の動作は
[Local Hub階層Sync v1運用](HIERARCHICAL_SYNC.md)を参照してください。

栽培カレンダーの施肥履歴、一般・独自肥料カタログ、土壌検査、施肥後の降雨・潅水、残効信頼度、初心者向けサジェストの実装方針は [施肥計画・肥料サジェスト実装方針](HUB_FERTILIZATION_RECOMMENDATION_POLICY.md) を参照してください。

点滴チューブ敷設時の1穴吐出量校正、生育・天候に応じた潅水提案、排液ECを使った真水による培地リセットの将来仕様は [点滴潅水の吐出量校正・潅水提案・培地リセット仕様](HUB_DRIP_IRRIGATION_CALIBRATION_AND_SUBSTRATE_RESET_SPEC.md) を参照してください。

定植・水やり・剪定・収穫をレール非依存で段階的に自動化する共通ライフサイクル、機器能力と設置先の照合、安全境界は [エージェンティック農作業の実装方針](HUB_AGENTIC_FARM_OPERATIONS_POLICY.md) を参照してください。

なにができるか（要点）

- デバイスからのデータ受信（MQTT）と加工
- `farm/{device_id}/telemetry` テレメトリの受信と保存
- デバイスごとの設定配信（MQTT request/reply/push）
- 画像／音声のローカル保存と S3 互換ストレージへのアップロード
- Local Hubごとに設定したTurso/libSQL replicaとの統合
- タイムラプス生成・スケジューリング（APScheduler）
- タイムラプス画像からの mp4 生成と Instagram Reel 自動投稿
- 簡易 Web 表示（Flask）

クイックスタート

1. uv を導入（未導入の場合）: https://docs.astral.sh/uv/getting-started/installation/

2. 依存を同期

```bash
uv sync
```

3. 対話式に初期設定と接続確認を行う

```bash
uv run ina-hub install
```

4. ローカルで起動（libSQL schema は起動時に自動準備）

```bash
uv run python src/ina_device_hub/serve.py
# デフォルト: http://localhost:39151
```

systemd による自動起動（推奨）

このリポジトリにはテンプレートユニット `systemd/inas-device-hub@.service` と
インストーラースクリプト `scripts/install_service.sh` が含まれます。インストーラーの主な動作は次の通りです。

- リポジトリを指定ディレクトリへコピー（既定: `/home/<user>/ina-device-hub`）
- インストール実行者（`sudo` で実行した場合は元のユーザー）をサービス実行ユーザーに設定
- `.default.env` を `.env` にコピー（無ければ簡易テンプレートを作成）
- 既存`.env`、MQTT設定、`WORK_DIR`内の運用データは上書きしない
- `uv.lock`どおりの依存同期、外部接続確認、状態バックアップ、`/readyz`確認
- `systemd/inas-device-hub@.service` を `/etc/systemd/system/` に配置し、
  テンプレート内の `@@INAS_HUB_DIR@@` と `@@INAS_HUB_USER@@` をターゲットのパス・ユーザーに置換
- Cloudflare Tunnel 設定がある場合は `systemd/inas-cloudflare-tunnel.service` も配置・有効化
- `inas-device-hub@main` を有効化・起動

インストール例（sudo）

```bash
sudo ./scripts/install_service.sh

# --user と --target-dir で上書き可能。--user は既存ユーザーを指定してください。
sudo ./scripts/install_service.sh --user mysvcuser --target-dir /opt/ina-device-hub

# Cloudflare Tunnel も systemd 管理にする場合
sudo ./scripts/install_service.sh --production --target-dir "$PWD" --enable-cloudflare-tunnel
```

`--production`は初回のCloudflare本番構築または明示的な再構成時だけ使います。
通常更新では付けず、既存のMQTT・HTTP・認証・Turso・Cloudflare設定を維持します。
詳細は[運用ガイド](OPERATIONS.md)を参照してください。

サービス確認

```bash
systemctl status inas-device-hub@main

journalctl -u inas-device-hub@main -f
```

運用スクリプト

```bash
sudo ./scripts/hub_service.sh start
sudo ./scripts/hub_service.sh restart
./scripts/hub_service.sh status
./scripts/hub_service.sh logs
```

このLocal Hubは任意でCloudflare Access + Tunnelを遠隔入口にできますが、従来の
Turso/libSQL構成は変えません。Local Hubを運用しない顧客向けには、別実装の
[`hub-cloud`](../../../hub-cloud/README.md)を用意します。Cloud Hubは共有Worker
1つ、directory DB 1つ、顧客ごとの専用Turso DB 1つで構成し、Edge Gatewayから
認証付きHTTPS Syncを受けます。詳細は
[CLOUDFLARE_HOSTED_OPTION.md](CLOUDFLARE_HOSTED_OPTION.md)を参照してください。

Tunnel 版のネットワーク構成図は [NETWORK_ARCHITECTURE.md](NETWORK_ARCHITECTURE.md) を参照してください。

hub の管理 UI は、TOPで圃場を検索・選択し、選択後に圃場の現在状態、設置物、デバイス、栽培作業へ進む構成です。全デバイスをTOPへ列挙しません。設置ビューは空間ごとの北向きを保持し、Canvas 上の方位マークで常時確認できます。UI 改善方針は [HUB_ADMIN_UX_IMPLEMENTATION.md](HUB_ADMIN_UX_IMPLEMENTATION.md)、追加・編集画面のモーダル原則は [HUB_MODAL_EDITING_UX_POLICY.md](HUB_MODAL_EDITING_UX_POLICY.md)、状態ごとの操作可否と表示原則は [HUB_UI_STATE_ACTION_POLICY.md](HUB_UI_STATE_ACTION_POLICY.md)、設置ビューの操作とデータモデルは [HUB_INSTALLATION_LAYOUT_SPEC.md](HUB_INSTALLATION_LAYOUT_SPEC.md)、圃場・設置物・デバイスの階層と大量件数への対応は [HUB_FIELD_RESOURCE_HIERARCHY_SPEC.md](HUB_FIELD_RESOURCE_HIERARCHY_SPEC.md) を参照してください。

定植単位の年間計画、作業期間、優先度、防除対象、作業実績、LLM呼び出し条件、FAMIC/WAGRIを使う農薬検索方針は [HUB_PLANT_MANAGEMENT_CALENDAR_SPEC.md](HUB_PLANT_MANAGEMENT_CALENDAR_SPEC.md) にまとめています。

Hub全体のAI・システム設定は管理者用 `/settings`、タイムゾーンと日付形式はemail単位の `/preferences` に分離しています。個人設定の正本はLocal HubのTurso/libSQLです。Hubは日本語固定とし、翻訳はブラウザ機能を使用します。設置ビューはrevisionによる楽観ロックと三者比較を行い、同時編集時に変更を無言で上書きしません。詳細は [HUB_CONFIGURATION_MANAGEMENT.md](HUB_CONFIGURATION_MANAGEMENT.md) と [HUB_USER_SETTINGS_AND_CONCURRENT_EDITING.md](HUB_USER_SETTINGS_AND_CONCURRENT_EDITING.md) を参照してください。

圃場一覧では `＋ 圃場を追加` のモーダルから、名前、都道府県、市区町村、設置環境など圃場自体の基本情報だけを登録します。作物、品種、作物区分、樹齢、栽培方式、土壌・培地、目標レンジ、栽培カレンダーは圃場属性ではなく、設置ビュー上の培地に登録した定植単位で管理します。圃場詳細は `概要`、`環境・設備`、`栽培`、`記録`、`設定` のタブで分け、初期表示では現在の圃場状態と `次の判断候補` を先に表示します。土壌水分、EC、pH、湿度、PAR は現在値と作物目標の範囲をレンジグラフで比較し、目標内、下限未満、上限超過、目標未設定を区別します。時系列グラフは `環境・設備` で圃場全体から空間別へ整理し、`栽培` では作物情報、年間カレンダー、直近10件の経過を確認します。`記録` タブはデバイス0台でも使用でき、潅水時間、EC、pH、作物状態など必要な項目だけを検索して追加します。同日のデバイス値がある場合は複数デバイス・複数時刻を自動表示し、月間カレンダーから手入力、5段階絵文字評価、R2画像とともに振り返れます。詳細は [HUB_DEVICE_FREE_FIELD_RECORDING_SPEC.md](HUB_DEVICE_FREE_FIELD_RECORDING_SPEC.md) を参照してください。これらを前提条件として、hub は最新センサー値との差から灌水・液肥・噴霧などの判断候補を作ります。判断候補は将来、植物管理カレンダー、画像・気象判断、設備保守、定期作業を統合した圃場 TODO リストへ発展させます。現時点で hub から制御できるのは WTR/WRS の灌水のみで、液肥と噴霧は将来デバイス向けの候補として記録します。改善ループの仕様は [AGRI_IMPROVEMENT_LOOP.md](AGRI_IMPROVEMENT_LOOP.md) を参照してください。

実データがない開発環境では、サンプルデバイスと履歴を使って UI/UX を確認できます。設置ビューの紐づけ候補として WTR 3台、WRS 2台、ENV 2台、SOI 3台、PAR 1台、カメラ 1台を登録します。次のコマンドは Flask の web UI だけを起動し、MQTT やデバイス接続は開始しません。

```bash
python scripts/run_admin_demo_server.py
```

起動後に `http://127.0.0.1:39251/demo/mqtt-devices` を開きます。一覧カードで灌水・土壌水分・次回起床のサマリを確認し、カードを選ぶと水やり機詳細へ遷移します。詳細では Plotly で灌水推移と土壌水分推移を確認でき、表示期間は直近3日、2週間、1か月、全期間、カスタムから選べます。新しいデモ保存先には、1号ハウス、3本の畝、イチゴ「紅ほっぺ」36株、12か月分の作業、作業中・完了・見送りの例、施肥履歴を重複なく初期投入します。年間栽培カレンダーは `http://127.0.0.1:39251/fields/demo-strawberry-field/calendar` で確認できます。確認サーバは `.env` の実Turso URLを継承せず、`HUB_DEMO_WORK_DIR` 配下のローカルlibSQLだけを使用します。デモページ上の操作は実データへ保存されません。実データの管理画面は通常通り `/mqtt-devices` です。

Local Hubの既存`.env`からTunnelを構築する場合は、次のscriptを使用できます。

AI Agent に環境構築や Cloudflare hosted option のセットアップを依頼する場合は、先に [AI_AGENT_ENVIRONMENT_SETUP.md](AI_AGENT_ENVIRONMENT_SETUP.md) を読ませてください。`.env` を正として扱うこと、secret を出力しないこと、Cloudflare resource を idempotent script で作成・再利用することを前提にしています。

```bash
# Access / Tunnel / DNS を構築し、必要なら cloudflared を hub/.data/bin に入れる
bash scripts/cloudflare_hosted_setup.sh --install-cloudflared

# local hub と tunnel をまとめて foreground 起動する
bash scripts/cloudflare_hosted_up.sh --install-cloudflared
```

setup は再実行可能です。`.env` に保存済みの ID を優先して既存 resource を再利用し、同名 resource が複数ある場合や、同じ hostname に別用途の DNS record がある場合は自動上書きせず停止します。

`cloudflare_hosted_up.sh` は `.venv` の固定依存とWaitressでlocal hubを起動します。`WORK_DIR` / `LOCAL_STORAGE_BASE_DIR` が書き込み可能で、MQTT brokerなど `.env` の接続先へ到達できる必要があります。`/readyz` が制限時間内にMQTT接続を含む準備完了を返さなければTunnelを開始しません。

許可 email の追加・削除、tunnel 単体起動は次で行います。

```bash
python3 scripts/cloudflare_access_setup.py add user@example.com
python3 scripts/cloudflare_access_setup.py remove user@example.com
bash scripts/cloudflare_tunnel_start.sh
bash scripts/cloudflare_tunnel_daemon.sh --install-cloudflared start
bash scripts/cloudflare_tunnel_daemon.sh status
```

Cloudflare の Error 1033 が出る場合は、DNS / Access ではなく Tunnel connector が動いていない可能性が高いです。まず `bash scripts/cloudflare_tunnel_daemon.sh status` で `cloudflared` の常駐状態を確認してください。

Git 管理外ローカルファイルの引っ越し

`.env`、デバイス一覧 JSON、`data/`、`logs/` など Git 管理外のローカルファイルは、次のコマンドで zip に退避・復元できます。`.env` には secrets が含まれるため、zip は非公開の経路で共有してください。

```bash
bash scripts/migrate_local_files.sh list
bash scripts/migrate_local_files.sh export-zip /tmp/ina-device-hub-local-files.zip
bash scripts/migrate_local_files.sh import-zip /tmp/ina-device-hub-local-files.zip --overwrite
```

実行時の `WORK_DIR`（既定: `~/.ina-device-hub`）も含める場合は `--include-work-dir` を付けます。

```bash
bash scripts/migrate_local_files.sh export-zip /tmp/ina-device-hub-local-files.zip --include-work-dir
bash scripts/migrate_local_files.sh import-zip /tmp/ina-device-hub-local-files.zip --include-work-dir --overwrite
```

旧デバイスのストレージを新デバイスにマウントして直接コピーできる場合は、`move-device` で repository 配下のローカル設定と `WORK_DIR` をまとめて移せます。

```bash
bash scripts/migrate_local_files.sh move-device \
  --source-dir /mnt/old-device/path/to/ina-device-hub \
  --target-dir /path/to/ina-device-hub \
  --source-work-dir /mnt/old-device/path/to/.ina-device-hub \
  --target-work-dir /path/to/.ina-device-hub \
  --overwrite
```

実行前確認だけなら `--dry-run` を付けます。`WORK_DIR` を移さない場合は `--no-work-dir` を指定してください。

手動でテンプレートを配置する場合

```bash
sudo ./scripts/install_service.sh --target-dir "$PWD"
sudo systemctl daemon-reload
sudo systemctl enable --now inas-device-hub@main
```

開発ワークフロー（短く）

- フォーマット

```bash
uv run ruff format .
```

- リント

```bash
uv run ruff check .
uv run ruff format --check .
```

主要ファイル（概要）

- `pyproject.toml` — Python依存とツール設定
- `src/ina_device_hub/` — アプリ本体（`setting.py`, `hub_mqtt_client.py`, `camera_connector.py` など）
- `data/instagram_caption_prompt.txt` — Instagram 投稿文生成プロンプトのテンプレート
- `data/plant_calendar_evaluation_cases.json` — AI栽培計画の代表評価ケース
- `scripts/evaluate_plant_calendars.py` — 栽培計画の安全性・作業負荷・具体性・年間網羅性を採点（`--live` で保存済みAI設定を使用）
- `doc/AI_AGENT_ENVIRONMENT_SETUP.md` — AI Agent 向け環境構築・Cloudflare setup 手順
- `doc/CLOUDFLARE_HOSTED_OPTION.md` — Cloudflare hosted option の実装方針
- `../../../hub-cloud/` — 共有Cloud Hub frontend/backendとEdge Gateway出荷tool
- `systemd/inas-device-hub@.service` — systemd テンプレートユニット
- `scripts/install_service.sh` — systemd インストールスクリプト

主要な環境変数（要約）

詳細は `src/ina_device_hub/setting.py` を参照してください。主に次が必須です:

- TURSO_DATABASE_URL, TURSO_AUTH_TOKEN
- S3_ENDPOINT_URL, S3_BUCKET_NAME, S3_BUCKET_REGION, S3_ACCESS_KEY, S3_SECRET_KEY
- MQTT_BROKER_URL, MQTT_BROKER_PORT, MQTT_BROKER_USERNAME, MQTT_BROKER_PASSWORD
- TIMELAPSE_INTERVAL
- WEATHER_RECORD_ENABLED, WEATHER_RECORD_INTERVAL_SECONDS
- WEATHER_PROVIDER, WEATHER_LATITUDE, WEATHER_LONGITUDE, WEATHER_TIMEZONE, WEATHER_BACKFILL_DAYS
- WEATHER_OPEN_METEO_ARCHIVE_URL
- WEATHER_FORECAST_URL, WEATHER_AREA_NAME, WEATHER_OFFICE_NAME, WEATHER_FORECAST_TITLE
- DEVICE_CONFIG_DEFAULT_NTP_SERVER, DEVICE_CONFIG_DEFAULT_TIMEZONE_OFFSET_SEC, DEVICE_CONFIG_DEFAULT_MOISTURE_THRESHOLD

Instagram 自動投稿を使う場合は、追加で次を設定してください。

- S3_TMP_ENDPOINT_URL, S3_TMP_BUCKET_NAME, S3_TMP_BUCKET_REGION, S3_TMP_ACCESS_KEY, S3_TMP_SECRET_KEY
- S3_TMP_BASE_URL
- INSTAGRAM_USER_ID, INSTAGRAM_ACCESS_TOKEN
- INSTAGRAM_SENSOR_ID
- INSTAGRAM_WEATHER_FORECAST_URL, INSTAGRAM_WEATHER_AREA_NAME
- INSTAGRAM_WEATHER_OFFICE_NAME, INSTAGRAM_WEATHER_FORECAST_TITLE
- AI_IMAGE_ANALYZE_API_KEY, AI_TEXT_ANALYZE_API_KEY

AI栽培計画の「公的な栽培根拠を検索」を有効にすると、公式OpenAI APIを設定している場合に限り、計画作成前に農林水産省・農研機構・自治体の資料をResponses Web Searchで検索します。検索結果は出典URLと取得日付きで保存され、同じ栽培条件では既定30日間キャッシュを再利用します。検索の有効・無効と再検索までの日数は「アプリ設定」から変更できます。OpenAI互換接続先がResponses Web Searchに対応しない場合は検索せず、従来の一般基準へ安全にフォールバックします。

AI有効/無効、AI APIキー、Base URL、モデル、Instagram投稿処理開始時刻、投稿元カメラ、植物位置の補足はHubの `/settings`、ユーザーのタイムゾーンと日付形式は `/preferences` で管理します。AI APIキーの保存値は画面へ再表示されません。

Instagram 自動投稿フロー

- `TIMELAPSE_INTERVAL` ごとに RTSP から静止画を取得し、S3 とローカルの `timelapse_frames/` に保存します。
- `WEATHER_RECORD_INTERVAL_SECONDS` ごとに Open-Meteo から指定緯度経度の日別気象データを取得し、`WORK_DIR/weather_records.jsonl` に生育気象ログとして追記します。
- `/settings` のInstagram投稿処理開始時刻になると、通常日は前回投稿以降、日曜は直近7日分の静止画から mp4 を生成します。
- 生成した動画と代表画像を `S3_TMP_*` にアップロードし、公開 URL を作成します。
- AI に代表画像、タイムラプス動画 URL、センサースナップショット、前回投稿時に保存した広域天気予報、画面で設定した植物位置の補足を渡して投稿文を生成します。
- 投稿完了後、次回投稿用に `INSTAGRAM_WEATHER_FORECAST_URL` の JMA feed から `INSTAGRAM_WEATHER_OFFICE_NAME` と `INSTAGRAM_WEATHER_FORECAST_TITLE` に一致する最新 XML を選び、`INSTAGRAM_WEATHER_AREA_NAME` の天気予報を状態ファイルに保存します。
- Instagram Graph API を使って Reel を投稿します。

注意:

- Instagram 投稿には公開アクセス可能な `S3_TMP_BASE_URL` が必要です。非公開バケット URL では投稿できません。
- 投稿元カメラは `/settings` で登録済みのカメラデバイスから選択してください。
- `INSTAGRAM_SENSOR_ID` を設定すると、最新センサーデータを投稿文生成に含めます。
- 指示コメントとして扱う自分のInstagramユーザー名はGraph APIから自動取得します。その他ユーザーのコメントは一般話題のみ参照し、セキュリティ関連話題は無視します。
- Instagram 投稿用の天気予報はArea単位の天気と降水確率だけを投稿文生成に含めます。観測地点名、観測所コード、住所、地点気温は含めません。
- `weather_records.jsonl` は1行1 JSONの追記ログです。Open-Meteo の日別データは `source.type=reanalysis` として、`daily_summaries` に日別の降水量、降雨時間、日照時間、日射量、ET0、最高/最低気温を保持します。
- 投稿文テンプレートを変更する場合は `data/instagram_caption_prompt.txt` を編集してください（必須プレースホルダーが欠けた場合は安全のため内蔵テンプレートにフォールバックします）。

カメラ RTSP 設定

管理画面の「機器保守」から「カメラを登録」を選び、表示名、カメラ方式、IPアドレスまたはホスト名、RTSP認証情報を入力します。保存前に「接続を確認」を実行すると、HubがLAN内のカメラから1フレーム取得できるか確認できます。登録・編集・削除・接続確認は管理者だけが実行できます。

- `reolink`: チャンネルと `main` / `sub` ストリームを選択します。
- `tapo`: 既定の `/stream1` を使用します。
- `custom`: RTSPパスを入力します。
- カメラが圃場、設置ビュー、Instagram投稿元から参照されている間は登録を削除できません。
- パスワードは一般のカメラ一覧とは別の権限 `0600` の認証情報ファイルへ保存され、APIには返されません。

既存環境の `.camera_device_list.json` は引き続き読み取れます。従来形式のカメラを管理画面から更新すると、ユーザー名とパスワードが保護された認証情報ファイルへ移されます。手動で確認する場合のメタデータ形式は次のとおりです。

```json
{
  "INACD-example": {
    "id": "INACD-example",
    "name": "garden",
    "camera_type": "reolink",
    "ip_address": "192.168.1.84",
    "channel": 1,
    "stream": "main",
    "timelapse": true
  }
}
```

- `tapo`: `/stream1`
- `reolink`: `/Preview_<channel>_<stream>`
- `rtsp_path` を指定すると、種別ごとの既定パスより優先します。

貢献

PR・Issue を歓迎します。作業前に`uv sync`で依存を同期し、`uv run ruff format .`、`uv run ruff check .`、`uv run ruff format --check .`を実行してください。

デバイス設定配信

- デバイスは `/<device_id>/kinds/config/request` へ publish します。
- Hub は `/<device_id>/kinds/config/reply` へ設定 JSON を返します。
- 即時反映が必要な場合は `/<device_id>/kinds/config/push` に同じ JSON を publish できます。
- 設定は `WORK_DIR/.device_configs.json` に保存されます。

Farm Telemetry 受信

- Hub は `farm/+/telemetry` を購読します。
- payload は JSON として解釈し、`device_id` ごとの最新値を保存します。
- `soil_moisture_*`, `soil_temp_c`, `battery_v`, `rssi`, `timestamp` は `latest_sensor_data.extra.telemetry` に保持します。
- `soil_temp_c` は既存の温度グラフ互換のため `latest_sensor_data.temp` にも反映します。
- `null` を含む payload を許容します。欠損値があっても受信処理が落ちない前提です。
- デバイス詳細画面では最終受信時刻、電圧しきい値、未着時間に基づく簡易監視表示を出します。

Sensor Measurements

- MQTT device status から抽出できる測定値は `sensor_measurements` に縦持ちで保存します。
- 測定項目の表示名、単位、対応 device_kind は `sensor_measurement_definitions` に定義します。
- 初期定義には `SOI` / `WTR` の土壌水分、`ENV` の PAR、土壌水分、地温、EC、pH、N/P/K、将来の日射量を含みます。
- `latest_sensor_data` は既存互換として残し、ENV の多項目測定は `sensor_measurements` を正とします。

ローカル API

- `GET /local/api/device-configs`
- `GET /local/api/device-configs/<device_id>`
- `PUT /local/api/device-configs/<device_id>`
- `POST /local/api/device-configs/<device_id>/push`

`PUT /local/api/device-configs/<device_id>?push=true` に設定 JSON を送ると、保存後に `push` まで実行します。

設定 JSON 例

```json
{
  "ntp_server": "my_device.local",
  "timezone_offset_sec": 32400,
  "moisture_threshold": 35,
  "schedules": [
    {
      "hour": 6,
      "minute": 30,
      "duration_sec": 20,
      "channel_mask": 1
    },
    {
      "hour": 18,
      "minute": 0,
      "duration_sec": 30,
      "channel_mask": 3
    }
  ]
}
```

NTP サーバ運用

- NTP サーバは MQTT Hub と同じ PC 上で、アプリとは別の OS サービスとして動かしてください。
- `ntp_server` には、ファームから名前解決できるホスト名または固定 IP を設定してください。
- ローカルネットワークから UDP 123 で到達できる必要があります。
- Hub 自体は `ntp_server` の値を配信するだけなので、実際の NTP 提供は `chronyd` や `ntpd` のような既存サービスで構成する前提です。

ライセンス

MIT ライセンス（`LICENSE` を参照）

---

必要であれば、Raspberry Pi 固有のセットアップ手順や systemd の環境ファイル対応を README に追記します。
