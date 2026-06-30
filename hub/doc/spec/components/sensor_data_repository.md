# sensor_data_repository (src/ina_device_hub/sensor_data_repository.py)

## 目的

- センサーデータの一時保存（ファイル）と DB への集計・永続化を担うリポジトリ。

## 主要挙動

- add(device_id: str, seqId: int, data: dict)

  - 最新データを DB に upsert。
  - 時間（YYYYMMDDHH）単位で一時バッファ (`tmp_sensor_data.json`) にデータを蓄積し、1時間経過したバケットを集計して DB に保存。

- get_latest(device_id) / get_latest_aggreated(device_id) / get_aggreated_by_range(device_id, start, end)

  - DB からのフェッチを行い、JSON 文字列をデコードして辞書を返す。

- force_aggregate(device_id)

  - バッファ内のデータを強制集計する。

## 依存

- `InaDBConnector`, `setting`, `general_log`

## 注意点

- 一時データをファイルに保存する設計は再起動耐性を提供するが、ファイル破損や同時アクセスの考慮が必要。
- 集計ロジックは現状 `temp`, `tds` の平均のみを計算。拡張時は欠損値や外れ値処理を検討。
