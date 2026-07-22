# Hub Operations clients

Cloudflare Access Service Tokenを使い、公開Hubの`/operations/api/v1`を非対話で操作するクライアントです。

責務別に配置します。

- `devices/`: device、runtime config、firmware、OTA
- `fields/`: 圃場、区画、配置（対応API追加後に実装）
- `work/`: 作業計画、作業記録、栽培記録（対応API追加後に実装）
- `common/`: 認証、HTTP、env読み込み

既定では`~/.config/inas/operations-api.env`を読みます。

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
