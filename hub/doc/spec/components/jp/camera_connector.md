# camera_connector (src/ina_device_hub/camera_connector.py)

## 目的

- RTSP カメラから静止画取得・MJPEG ストリーミングを行う。ffmpeg の Python API を利用するラッパー。

## 主要クラス / 関数

- class CameraConnector

  - __init__()
    - インスタンス化。内部で `camera_device_repository()` を取得する。

  - take_picture(device_id: str) -> bytes | None
    - 指定デバイスの RTSP URL を構築し、ffmpeg で 1フレームを取得してバイト列で返す。失敗時は None を返す。

  - stream_rtsp(device_id: str) -> subprocess.Process | None
    - ffmpeg を非同期実行して MJPEG 出力のプロセスを返す。失敗時は None。

  - stop_stream(device_id: str, process)
    - 指定プロセスを停止しクリーンアップする。

  - construct_rtsp_url(device_id: str) -> str | None
    - デバイス情報から RTSP URL を生成する。

  - get_rtsp_url(ip_address: str, username: str, password: str) -> str
    - 静的ヘルパー。

  - generate_frames(device_id) -> Iterator[bytes]
    - process.stdout を読み MJPEG フレーム境界で yield するジェネレータ。

## 依存

- ffmpeg（Python バインディング）
- `ina_device_hub.camera_device_repository`
- `ina_device_hub.general_log`

## 注意点 / 改善案

- ffmpeg プロセス管理やタイムアウト、エラーハンドリングを強化することを推奨。
- 認証情報（パスワード）をログに出さない運用ルールの徹底。
- ストリーミング中のメモリ消費を抑える仕組み（チャンクサイズの上限や一時ファイル利用）を検討。
