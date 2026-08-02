# Flash layout JSON

GUIに表示する領域と、esptoolへ渡すアドレスを定義します。partition CSVを直接
使用しないのは、bootloaderやmerged imageがpartition tableの外側にあり、出荷時
の必須・任意・機密区分もCSVでは表現できないためです。

各region:

- `id`: 配置内で一意な識別子
- `label`: GUI表示名
- `address`: 書込み開始アドレス。整数または`0x`形式
- `max_size`: 任意。ファイルの最大サイズ
- `required`: その配置を使う工程で必須か
- `default_enabled`: 起動直後に選択するか
- `accepted_names`: 推奨ファイル名
- `description`: 用途
- `sensitive`: NVSやfilesystemのような個体設定領域か

`sensitive=true`は初期無効となり、書込み時の確認画面でも警告されます。
