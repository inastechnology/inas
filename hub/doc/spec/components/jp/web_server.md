# web_server (src/ina_device_hub/web_server.py)

## 目的

- Flask を用いたローカル管理 UI と API を提供するモジュール。デバイス一覧、カメラプレビュー、画像取得等のエンドポイントを持つ。

## 主要エンドポイント（抜粋）

- GET / : ダッシュボード（devices, cameras, locations）
- GET /devices/<device_id> : デバイス詳細とグラフ
- GET /devices/<device_id>/latest_image : 最新画像の一覧（テンプレート `image_page.html` を使用）
- GET /local/api/images/<path:image_path> : 画像をバイトで返す
- GET /local/api/camera/<device_id>/video_feed : MJPEG ストリーム（camera_connector.generate_frames を利用）

## 依存

- Flask
- sensor_* リポジトリ、camera_connector、storage_connector、utils

## 注意点

- テンプレートは簡易 inline 実装で拡張性が低い。将来的に Jinja テンプレートファイルへ分離することを推奨。
- エンドポイントは認証なしで動作するためローカル限定で運用するか、認証レイヤの追加を推奨。
