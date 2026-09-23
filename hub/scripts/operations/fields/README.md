# Fields operations

`read_client.py` の `FieldReadClient` は、許可された圃場一覧、note・日々の記録検索、カメラ一覧、保存済みカメラ画像、note・記録の添付画像を読み取ります。取得処理はすべて `/operations/api/v1/fields/*` を使います。

Service Tokenの権限設定とAIからの使い方は [読み取り用MCP](../mcp_server/README.md)を参照してください。区画・配置の変更、記録の追加・削除は未対応です。
