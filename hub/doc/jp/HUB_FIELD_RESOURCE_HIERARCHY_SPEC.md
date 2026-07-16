# Hub 圃場・設置物・デバイス階層設計

作成日: 2026-07-14

## 1. 目的

Hub の通常操作を圃場中心に統一し、圃場やデバイスが数千から数万件になっても、利用者が自分の作業対象だけを段階的に確認できるようにする。

次の原則を採用する。

- TOP は圃場を検索して選択する画面とし、デバイスを直接列挙しない。
- 圃場を選択してから、その圃場に設置された空間、培地・栽培設備、設備、デバイスを取得する。
- 物理的な包含関係と、潅水・計測などの作用対象を別の関係として管理する。
- 一覧 API は必ず検索条件とページング上限を持ち、全件取得を通常導線に置かない。

## 2. ドメイン階層

物理的な包含関係は次のツリーで表す。

```text
圃場 (Field)
  空間 (LayoutSpace: ハウス、露地、屋内、水耕設備)
    配置物 (Placement)
      培地・栽培設備: 畝、鉢、植木、水耕ベッド
      設備: 潅水機、センサー、タンク、植物育成ライト、噴霧器、送風機、空調
      デバイス配置: WTR/WRS、ENV、SOI、PAR、カメラ
        デバイス機能: MOSFET SW、センサー、カメラ
```

現行モデルでは、圃場を `FieldRepository`、空間と配置物を `FieldLayoutRepository` で管理する。配置物の `child_space_id` が空間階層を、`binding.device_id` と `binding.resource_id` がデバイス機能との結合を表す。

定植は圃場直下ではなく、畝、鉢、植木、水耕ベッドなどの配置物に属する。作物、品種、栽培方式、生育目標、植物管理カレンダーも定植単位で管理する。

## 3. 包含と作用対象

ツリーの親子は「その場所に物理的に含まれる」という1種類の意味に限定する。

潅水・計測の関係は `binding.target_placement_ids` で表し、包含ツリーとは別の有向関係として扱う。

例:

```text
北ハウス
  イチゴ畝A
  イチゴ畝B
  潅水制御盤 WRS-001
    潅水1系

潅水1系 --waters--> イチゴ畝A
潅水1系 --waters--> イチゴ畝B
土壌センサー --measures--> イチゴ畝A
```

この分離により、1つのデバイス機能が複数の畝を対象にしても、ツリー上でデバイスを重複させずに済む。デバイスの設置場所変更と潅水対象変更も独立して扱える。

培地に `waters` 相当の関連がない状態は `手動潅水` とする。物理的なホース・配管は施工資料の責務とし、Hubのリソース階層には含めない。自動潅水へ切り替える場合は、配置済み潅水機の `binding.target_placement_ids` に培地IDを追加する。

## 4. 画面遷移と取得境界

| 画面 | 取得してよい情報 | 取得してはいけない情報 |
|---|---|---|
| TOP `/` | 検索条件に一致する圃場18件と圃場単位サマリ | 全デバイス、全テレメトリ、全カメラ |
| 圃場一覧 `/fields` | 検索条件に一致する圃場18件と圃場単位サマリ | 全デバイスの状態 |
| 圃場詳細 `/fields/<field_id>` | 選択圃場のレイアウト、定植、紐付け済みデバイス、最新状態 | 他圃場のデバイス |
| 設置エディタ | 選択圃場のレイアウト、紐付け済み候補、利用者が検索した未割当候補 | 無条件の全国デバイス一覧 |
| 年間カレンダー `/fields/<field_id>/calendar` | 選択圃場の定植、栽培基準、予定、作業記録 | 設置エディタのCanvas、他圃場の定植 |
| 将来のデバイス検索 | device ID等に一致するページ単位の結果と所属圃場 | 初期表示での全件 |

### 4.1 相互ナビゲーション

圃場、配置物、デバイスは、同じ `FieldLayoutRepository` のIDを使って相互に移動できるようにする。

- 圃場詳細の設置プレビューと圃場構成ツリーから、`/fields/<field_id>/layout?space=<space_id>&placement=<placement_id>` を開く。設置エディタは指定空間を開き、配置物を選択した状態でプロパティを表示する。
- デバイス配置から `/mqtt-devices/<device_id>`、デバイス機能から `/mqtt-devices/<device_id>?tab=settings` を開く。
- 機器詳細は `binding.device_id` を逆引きして所属圃場と配置物を表示し、`binding.target_placement_ids` を潅水対象または計測対象としてリンク表示する。
- 圃場の `device_ids` にだけ登録され、配置物がまだない機器は `圃場全体` への割当として扱う。`未設置` は圃場にも配置物にも割当がない場合だけ表示する。
- 機器詳細専用の設置図や、機器メタデータ `location` を別の配置正本として持たない。`location` はAPI後方互換の保存値としてだけ残し、GUIでは編集しない。

現行JSON版はデバイス詳細表示時にレイアウトを走査して逆引きする。DB版では `device_assignments(device_id)` の索引を必須とし、全圃場走査へ移行しない。

TOP と圃場一覧の検索条件は `q`、`prefecture`、`environment_type`、`page` とする。画面は1ページ18件、圃場APIは `page_size` を最大100件に制限する。

圃場詳細は設置レイアウトに含まれる `device_id` を先に抽出し、そのIDだけを `DeviceConfigService.find_record()` で取得する。全デバイス取得後に画面側で絞り込む実装は禁止する。

## 5. API 契約

### 5.1 圃場一覧

`GET /local/api/fields?q=&prefecture=&environment_type=&page=1&page_size=50`

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "page_size": 50,
  "page_count": 1
}
```

ページ番号方式は現行JSONリポジトリの初版契約である。DB移行後、更新頻度や件数によりページずれが問題になる場合は、`name + id` または `updated_at + id` を使うカーソル方式を追加する。

### 5.2 圃場詳細

`GET /local/api/fields/<field_id>` は指定圃場だけを返す。テレメトリ履歴は用途別APIへ分離し、期間と最大件数を必須にする。

### 5.3 デバイス割当

現行の `GET /local/api/fields/<field_id>/layout/devices` は設置エディタ用である。大規模運用へ移行する前に、次の検索契約へ置き換える。

- `q` または導入コードを必須にする。
- `field_id`、`assignment_state`、`device_kind`で絞り込む。
- 最大件数を50件程度に制限する。
- 他テナントのデバイスは検索結果に含めない。
- 割当操作は revision または一意制約で二重割当を防ぐ。

## 6. 永続化の移行

`.fields.json`、`.field_layouts.json` は単一Hub・小規模運用向けの現行実装である。多数圃場、多拠点、複数ユーザー運用では、リポジトリの公開メソッドを維持したままDB実装へ切り替える。

推奨テーブル:

| テーブル | 主な列 |
|---|---|
| `fields` | `id`, `tenant_id`, `name`, `prefecture`, `municipality`, `environment_type`, `updated_at` |
| `layout_spaces` | `id`, `field_id`, `parent_placement_id`, `space_type`, `name`, `revision` |
| `placements` | `id`, `field_id`, `space_id`, `preset`, `name`, 座標・寸法 |
| `device_assignments` | `device_id`, `field_id`, `placement_id`, `resource_type`, `resource_id` |
| `placement_relations` | `source_placement_id`, `relation_type`, `target_placement_id` |
| `plantings` | `id`, `field_id`, `placement_id`, 作物・品種・定植条件 |
| `field_summaries` | `field_id`, 状態件数、定植件数、配置件数、最新更新日時 |

必須索引:

- `fields(tenant_id, name, id)`
- `fields(tenant_id, prefecture, municipality, id)`
- `fields(tenant_id, environment_type, id)`
- `layout_spaces(field_id, parent_placement_id)`
- `placements(field_id, space_id, z, id)`
- `device_assignments(field_id, device_id)`
- `device_assignments(device_id)` の一意制約
- `placement_relations(source_placement_id, relation_type)`
- `placement_relations(target_placement_id, relation_type)`
- `plantings(field_id, status, placement_id)`

TOP用の配置件数、定植件数、注意件数を各カード表示時に全テーブルから集計しない。イベント更新時に `field_summaries` を更新するか、短時間キャッシュを使う。

## 7. 規模に対する制約

- 1リクエストで返す圃場は最大100件、画面では18件とする。
- 圃場詳細のデバイス取得数は、その圃場へ実際に紐付いた件数を上限とする。
- テレメトリ履歴は期間、集約粒度、件数上限を必須にする。
- 設置ビューは現行上限の50空間、各空間500配置を維持する。上限超過時は圃場分割または空間単位APIへ移行する。
- ブラウザへ全レイアウトを送る方式が重くなった場合、`space_id`単位で遅延ロードする。
- 検索結果とID解決には必ず `tenant_id` または利用者の所属範囲を適用する。

## 8. 将来のデバイス検索

デバイス検索は営農TOPとは別ページで実装する。目的は保守、交換、未割当デバイスの設置先確認であり、通常の圃場作業ではない。

検索結果には次を表示する。

- device ID、名称、種別、状態、最終通信。
- 所属圃場名と圃場詳細への導線。
- `圃場 / ハウス / 配置物` の設置パス。
- 未割当、割当済み、交換待ちなどの割当状態。

現段階では専用画面を作らず、TOPにも代替の全デバイス一覧を置かない。
