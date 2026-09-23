# Hub Operations clients

Cloudflare Access Service Tokenを使い、公開Hubの`/operations/api/v1`を非対話で操作するクライアントです。

Cloudflare Access のブラウザログインと公開 Hub UI は人間用です。AI エージェントはこの機械用 API を利用し、人間用経路へブラウザや `curl` でアクセスしたり、人間の Cookie・JWT を流用したりしません。Service Token は人間用 UI や `/local/api/*` の呼び出しには使いません。認証情報や対応 API がなければ制約を報告し、人間用ログインや認証設定の緩和で回避しません。ローカルでの確認方法は [AI Agent 向け環境構築ガイド](../../doc/jp/AI_AGENT_ENVIRONMENT_SETUP.md)を参照してください。

責務別に配置します。

- `devices/`: device、runtime config、firmware、OTA
- `fields/`: 許可圃場の一覧、note・記録検索、保存済みカメラ画像・記録添付画像の読み取り
- `work/`: 作業計画、作業記録、栽培記録（対応API追加後に実装）
- `common/`: 認証、HTTP、env読み込み
- `mcp_server/`: 上記読み取りAPIを呼ぶローカルstdio MCP（[日本語の利用ガイド](../../doc/jp/MCP_USAGE.md)、[実装・設定の詳細](mcp_server/README.md)）

既定では`~/.config/inas/operations-api.env`を読みます。

収集用MCPは別の `~/.config/inas/operations-collector.env` を既定で読みます。Hub側では `HUB_OPERATIONS_READ_GRANTS` に収集用Service ID・参照scope・圃場IDを指定します。収集用IDを既存のdevice/OTA用 `HUB_OPERATIONS_SERVICE_IDS` に入れないでください。両方に含まれるIDは拒否します。収集用IDでは更新操作とdevice一覧を利用できません。

```env
CF_ACCESS_CLIENT_ID=...
CF_ACCESS_CLIENT_SECRET=...
INAS_HUB_OPERATIONS_URL=https://hub.example.com/operations/api/v1
```

firmware rolloutは常にdry-runを先に実行してください。

```bash
python hub/scripts/operations/devices/publish_firmware.py \
  client-devices/watering-device/.pio/build/seeed_xiao_esp32s3/firmware.bin \
  --device-kind WTR \
  --version 0.0.4

python hub/scripts/operations/devices/publish_firmware.py \
  client-devices/watering-device/.pio/build/seeed_xiao_esp32s3/firmware.bin \
  --device-kind WTR \
  --version 0.0.4 \
  --apply
```

`--apply`を指定しても、スクリプトは最初にdry-runを行い、候補が同一であることを確認してから更新予約を適用します。
