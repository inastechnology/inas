# Hub Operations API

## Purpose

Cloudflare Access Service Tokenで認証した非対話クライアントが、公開Hubへ安全かつ再現可能に運用変更を適用できるAPIを追加する。第1段階はデバイス系として、登録デバイス検索、firmware artifact登録、dry-run付きOTA一括更新予約を提供する。将来の圃場系・作業系APIも同じ認証基盤とURL名前空間へ追加できるようにする。

## Progress

- [x] 現行Cloudflare Access認証、OTA service、管理APIを確認した。
- [x] Service Token JWTの検証とservice ID allowlistを実装した。
- [x] `/operations/api/v1/devices/*` APIを実装した。
- [x] 認証、権限、dry-run、冪等実行、artifact検証のテストを追加した。
- [x] 環境変数とCloudflare Access Service Auth policyのデプロイ手順を文書化した。

## Decisions

- Cloudflareが検証後にoriginへ渡す`Cf-Access-Jwt-Assertion`をHubでも署名・issuer・audience検証する。client secret自体はHubへ保存しない。
- service JWTの`common_name`を主体IDとし、`HUB_OPERATIONS_SERVICE_IDS`の明示allowlistに一致するものだけ許可する。
- ブラウザー用email JWTはoperations APIで受け付けない。ブラウザー管理APIのsame-origin防御とは別経路にする。
- firmware binaryは現行どおりHubの`WORK_DIR/firmware`へ保存する。R2移行はdeviceのHTTPS検証対応後に別変更として扱う。
- rolloutは既定dry-runとし、`dry_run=false`が明示された場合だけ更新予約を保存する。retired deviceは対象外とする。

## Validation

operations APIのfocused tests、web security tests、OTA tests、Ruffを実行する。デプロイ後はService Tokenを使い、health、WTR一覧、0.0.4 artifact登録、dry-run、適用、再取得を順に確認する。
