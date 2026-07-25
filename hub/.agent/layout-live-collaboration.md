# 設置ビューのライブ共同編集UXを段階導入する

このExecPlanは進行中の実装記録である。変更理由、互換性、検証結果を追記し、単独で実装の意図と完了条件を理解できる状態を保つ。

## 目的

現行の設置ビューは、`revision` による楽観ロック、HTTP 409、三者マージによって無言の上書きを防いでいる。しかし、別の利用者が同じ圃場を開いていることや、どの配置物を操作しているかは保存競合まで分からない。

第1段階では現行の保存契約を壊さず、同じ圃場を開いている利用者、選択中の空間・配置物、編集状態を共有する。別画面の保存を検出したら、未編集画面は最新版へ追従し、未保存入力がある画面は重ならない変更を自動統合する。同じ項目だけが変更された場合は既存の競合ダイアログを使う。

通信は現在の Flask + Waitress 構成を維持できる短いHTTP同期から開始する。Cloudflare TunnelはWebSocketを通せるが、WaitressはWSGIサーバーであり、WebSocket導入にはHTTPサーバー境界の変更が必要になる。第1段階で共同編集のドメイン契約とUXを検証し、後続で同じ契約をWebSocketへ載せ替えられるようにする。

## 進捗

- [x] (2026-07-23) 現行の保存API、revision、三者マージ、Canvas、認証、Cloudflare Tunnel、HTTPサーバー構成を調査した。
- [x] (2026-07-23) Hub内の圃場別roomと短いHTTP同期を第1段階に採用した。
- [x] (2026-07-23) Hub側に期限付きpresenceとlayout revisionを返す共同編集service/APIを追加した。
- [x] (2026-07-23) React側に参加者表示、遠隔選択表示、最新版追従、自動統合を追加した。
- [x] (2026-07-23) service/API/Reactの回帰試験と2画面browser smokeを追加した。
- [x] (2026-07-23) 型チェック、build、Python全試験、デスクトップ・モバイルのブラウザ確認を完了した。
- [x] (2026-07-23) 総合smokeの作業完了待機を、実績提出・管理者承認の現行フローへ追従させた。
- [x] (2026-07-23) TTL内の古いpresenceが残る連続実行でも共同編集smokeが収束するよう、画面数と遠隔選択の待機条件を改善した。

## 分かったこと

- `FieldLayoutRepository.upsert()` はファイルロック内でrevisionを比較し、成功時に `updated_by` と `updated_at` を保存する。
- Reactは `base`、`local`、409で返る `server` を使う三者マージを既に実装している。重ならない変更の自動統合ロジックを遠隔更新にも再利用できる。
- 現在の本番HTTPサーバーはWaitress、開発はFlaskである。依存追加なしで利用できるWebSocket経路は存在しない。
- Cloudflare TunnelはWebSocketをサポートするため、後続でHubのHTTPサーバー境界をASGI等へ変更すれば同じ公開hostnameを維持できる。
- `web_server.py`、生成済みbundle、`admin-ui/package.json` には別作業の未コミット変更がある。既存差分を保持し、生成物は最後に通常のbuildで更新する。
- ブラウザのタブ複製では `sessionStorage` も複製され得る。保存したseedだけを使うとclient IDが衝突するため、ページごとの乱数tokenを組み合わせた。
- 同じ認証利用者が複数画面を開く場合、参加者pillは利用者単位にまとめて「N画面」を表示する。Canvas上の同一配置物ラベルも重複をまとめ、人数が多い場合は省略表示する。
- 栽培作業の実績提出は即時完了ではなく `awaiting_review` へ移り、管理者承認後に `completed` となる。総合smokeの旧期待値がAPI成功後のtimeoutを起こしていた。
- ブラウザが強制終了するとleave beaconが届かず、TTLまでは以前の画面が参加者数へ残り得る。smokeは「2画面」という完全一致ではなく2画面以上を認識し、期待する遠隔選択が届くまでheartbeat周期を考慮して待つ必要がある。

## 設計判断

- roomのキーは `field_id` とする。tenantは現行どおり会社ごとに独立Hubを置く境界で分離される。
- presenceは永続化しない。`client_id`、認証済みemail、active space、selected placement、`viewing|editing|saving|conflict`、最終heartbeatを保持し、期限切れを除去する。
- actor emailはリクエストbodyを信用せず、Cloudflare Accessを検証した `CurrentUser` から取得する。
- クライアントは `sessionStorage` のseedとページごとの乱数tokenからclient IDを作る。同じ利用者の複数画面はpresence上では別clientとして保持し、UIでは利用者単位にまとめる。
- 初期実装は約2秒ごとの短いHTTP同期と、選択・保存状態変更時の即時同期を使う。ページ非表示時は頻度を落とす。
- presence応答には最新版の `revision`、`updated_by`、`updated_at` と参加者を含める。layout本体は既存GETから取得し、heartbeatごとに大きなJSONを返さない。
- 未編集画面は遠隔保存を自動反映する。未保存入力がある画面は三者マージし、競合がなければ自動統合して未保存のまま保つ。競合がある場合だけ既存ダイアログを開く。
- 現行の409と三者マージは、切断中、複数プロセス、将来のtransport障害に備える最終安全網として残す。
- Canvasでは別利用者が選択中の配置物を名前付き色枠で示す。色だけに依存せず、画面上部の参加者一覧とCanvasラベルにも名前を表示する。
- 第1段階ではhard lockやCRDTを導入しない。遠隔選択は注意表示とし、同一項目の実競合はrevision/三者マージで保護する。

## 実装手順

`field_layout_collaboration_service.py` にthread-safeなroom管理を追加する。入力を正規化し、期限切れpresenceを除去し、layout metadataと参加者のsnapshotを返す。serviceはtransportやUI文言を持たない。

`web_server.py` に同じ圃場の共同編集状態を更新・取得するAPIを追加する。圃場存在確認、認証済み利用者の利用、body sizeと列挙値の検証、`Cache-Control: no-store` を実装する。既存layout PUT成功時にもroomへ最新版metadataを通知する。

`types.ts` と `api.ts` に共同編集契約を追加する。`App.tsx` はtab ID、heartbeat、参加者state、同期状態、遠隔revision取得と三者マージを管理する。既存保存処理と競合解決処理は共通helperへ寄せ、競合中の再取得ループを防ぐ。

`InstallationCanvas.tsx` は遠隔選択を描画する。`styles.css` は参加者、同期状態、遠隔更新通知をデスクトップ・モバイル・高コントラストで判別できるようにする。

Python unit testでpresenceの分離、期限切れ、なりすまし防止、layout metadata更新を確認する。Web API testで認証email、validation、no-storeを確認する。ブラウザsmokeは2ページを開き、参加者表示、遠隔選択、別項目変更の自動統合、保存結果を確認する。同じ項目の競合判定は決定的なmerge unit testで確認する。

## 検証と完了条件

同じ圃場を2画面で開くと、双方に利用者と選択対象が表示される。片方が保存したとき、もう片方が未編集なら自動で最新版になる。もう片方に未保存変更があり、変更箇所が重ならなければ、その入力を保持したまま遠隔変更が自動統合される。同じ項目の場合だけ競合ダイアログが表示される。通信が一時失敗しても編集を妨げず、再接続後にrevisionで追いつく。現行の手動保存、Undo/Redo、409競合は維持される。

実行する検証は次の通り。

    cd hub && TMPDIR=/tmp TEMP=/tmp TMP=/tmp PYTHON_DOTENV_DISABLED=1 UV_CACHE_DIR=.uv-cache uv run python -m unittest discover -s tests
    cd hub/admin-ui && npm run typecheck
    cd hub/admin-ui && npm run test:merge
    cd hub/admin-ui && npm run build
    cd hub/admin-ui && HUB_URL=http://127.0.0.1:39252 npm run smoke
    cd hub/admin-ui && HUB_URL=http://127.0.0.1:39252 npm run smoke:collaboration
    git diff --check

## 検証結果

- Python全405試験が成功した。既定の一時ディレクトリが `/mnt/c` 配下になる環境では秘密ファイルの0600 mode検証だけが失敗するため、Linux側の `/tmp` を明示した。
- `npm run typecheck`、`npm run test:merge`、`npm run build` が成功した。
- 最新production bundleに対する2画面共同編集smokeが成功した。参加者2画面、遠隔選択、片方の未保存memoを保ったまま他方の名称変更を自動統合し、双方の保存結果を確認した。
- デスクトップとモバイルの参加者popoverがviewport内に収まり、Canvas上の遠隔選択が名前と状態を伴って表示されることを画像で確認した。
- 総合 `npm run smoke` を現行の「実績提出→確認待ち→管理者承認→完了」へ更新し、新規データ領域で最後まで成功した。承認済みwork logとcalendar actionの `review_status=approved` も永続化結果から確認する。
- 同じHubで総合smoke直後に共同編集smokeを実行し、TTL内の旧presenceを含む「1人・3画面」状態でも、2つの新しい画面が遠隔選択と自動統合まで収束することを確認した。

## 回復性

presenceはプロセス内の一時状態だけであり、Hub再起動時に消えてもlayout正本には影響しない。共同編集APIが失敗しても既存のGET/PUT、revision、409、三者マージで編集を継続できる。新しいUIを外しても保存データ形式は変わらない。

Revision note (2026-07-23): 現行実装とCloudflare/HTTPサーバー境界の調査を基に初版を作成した。

Revision note (2026-07-23): Hub内room coordinator、共同編集UX、回帰試験、2画面smokeを実装し、最終検証結果を反映した。

Revision note (2026-07-23): 総合smokeを管理者承認フローへ更新し、TTL内presenceが残る連続実行の待機条件を堅牢化した。
