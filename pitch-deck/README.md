# INAS Startup Pitch Deck

INAS Technologiesの日本語スタートアップピッチです。16:9のHTMLスライド、発表者ノート、出典一覧、PDF export scriptで構成しています。

## 想定

- 聴衆: startup pitch event、投資家、事業・実証partner
- 発表時間: 約7分
- 枚数: 13枚
- 状態: productはworking system、価格・unit economics・market tractionは検証中

未確認の導入件数、売上、価格、削減率を実績として表示しないでください。先行実証で得られた値だけをslide 12へ追加します。

表紙とslide 4の`lp/assets/hero.webp`は既存のmarketing visualです。創業者本人や実証圃場の証拠写真として説明しないでください。外部pitchの最終版では、許諾を得た開発者本人・実圃場の写真へ差し替えることを推奨します。

## ローカル表示

repository rootでserverを起動します。

```bash
python3 -m http.server 4330
```

以下をbrowserで開きます。

```text
http://127.0.0.1:4330/pitch-deck/
```

操作:

- 次へ: `→`、`↓`、`PageDown`、Space
- 前へ: `←`、`↑`、`PageUp`
- 最初・最後: `Home`、`End`
- 右下のbutton: 前後移動、fullscreen

## 検証とPDF出力

serverを起動した状態で実行します。`docs-site/node_modules`の`puppeteer-core`を利用します。

```bash
node pitch-deck/scripts/smoke.mjs
node pitch-deck/scripts/export-pdf.mjs
```

生成物は`pitch-deck/artifacts/`へ出力され、Git管理されません。

## 内容を確定する前に必要な情報

- 代表者名、役職、創業年月、team構成
- 発表先と持ち時間
- 調達目的、希望調達額、runway
- 先行利用数、継続利用数、LOI、売上などのtraction
- 公式H/Wの原価、販売価格、粗利仮説
- 導入前後で比較した作業時間、水使用量、異常対応時間

これらが確定したら、slide 10・12・13を投資家向けに更新します。
