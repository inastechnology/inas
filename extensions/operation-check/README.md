# Extension 動作確認プラグイン

Hub Extension API v1の表示経路を確認するための宣言型プラグインです。WTRの機器詳細に、概要カードと「拡張確認」タブを追加します。

確認対象は次のとおりです。

- 同梱レジストリへの登録
- `device_kinds` によるWTRだけへの適用
- `overview_cards` の描画
- `process_flow`、`metric_grid`、`callout` の描画
- `device`、`status`、`config` の許可済み値の解決
- PCと390pxスマートフォンのレイアウト

実行コード、機器操作、設定送信、外部通信、秘密情報へのアクセスは含みません。通常運用で不要になった場合は、このフォルダを削除してレジストリを再生成します。

```bash
cd hub
UV_CACHE_DIR=.uv-cache uv run python scripts/build_extension_registry.py
UV_CACHE_DIR=.uv-cache uv run python scripts/build_extension_registry.py --check
PYTHON_DOTENV_DISABLED=1 UV_CACHE_DIR=.uv-cache uv run python -m unittest discover -s tests -p 'test_extension_registry.py'
```
