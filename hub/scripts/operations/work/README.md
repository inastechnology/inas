# Work operations

作業計画、作業記録、栽培記録を扱うOperations APIクライアントを置きます。現在のHub Operations API第1段階には作業系endpointがないため、未対応のlocal APIを迂回して呼び出すスクリプトは追加しません。

圃場のnote・日々の記録（events）の読み取りは、実装済みの [fieldsクライアント](../fields/README.md)を使います。`/work/*` の独立した作業管理APIは未実装です。
