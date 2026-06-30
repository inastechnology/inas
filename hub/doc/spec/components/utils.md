# utils (src/ina_device_hub/utils.py)

## 目的

- グラフ作成などプロジェクト横断的に使われるユーティリティ関数を提供する。

## 公開 API

- class Utils

  - static create_latest_aggregated_graph_as_html(device_id, latest_aggregated_data) -> str | None
    - Plotly を使って温度/tds のグラフを HTML の div（埋め込み用）で返す。

## 依存

- `plotly` ライブラリ

## 注意点

- Plotly の出力はサイズが大きくなる可能性があるため、大規模データや高頻度更新では別の可視化戦略を検討。
