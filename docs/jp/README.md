# INAS Documentation

このディレクトリは、hub と client device を横断する仕様書と図を置く。

- [SYSTEM_SPECIFICATION.md](SYSTEM_SPECIFICATION.md): INAS 全体仕様。最初に読む入口。
- [DOCUMENTATION_GUIDE.md](DOCUMENTATION_GUIDE.md): ドキュメントの言語、配置、リンク、図の管理ルール。
- [CULTIVATION_SYSTEM_ORCHESTRATION.md](CULTIVATION_SYSTEM_ORCHESTRATION.md): イチゴ点滴栽培のような作物別システムを、複数デバイスと hub のオーケストレーションとして扱う設計方針。
- [assets/inas_system_diagrams.drawio](assets/inas_system_diagrams.drawio): 全体構成、データ/制御フロー、デバイス配置、OTA の draw.io 編集元。

図を更新する場合は、SVG や draw.io を直接編集せず、次のコマンドで再生成する。

```sh
python3 docs/assets/generate_system_diagrams.py
```
