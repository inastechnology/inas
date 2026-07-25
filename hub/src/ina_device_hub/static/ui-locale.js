(() => {
  "use strict";

  const requestedLocale = new URLSearchParams(window.location.search).get("lang");
  const locale = requestedLocale === "en" ? "en" : "ja";
  const JAPANESE_TEXT = /[\u3040-\u30ff\u3400-\u9fff]/;
  const SKIPPED_ELEMENTS = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEXTAREA"]);
  const TRANSLATABLE_ATTRIBUTES = ["aria-label", "title", "placeholder", "alt", "data-empty-message"];

  const english = new Map(Object.entries({
    // Shared navigation and controls.
    "圃場へ戻る": "Back to field",
    "圃場一覧": "Fields",
    "機器一覧": "Devices",
    "機器保守": "Device maintenance",
    "概要": "Overview",
    "環境・設備": "Environment & equipment",
    "栽培": "Cultivation",
    "記録": "Records",
    "設定": "Settings",
    "現在値・履歴": "Live data & history",
    "動作設定": "Operation settings",
    "機器を更新": "Device updates",
    "保守・管理": "Maintenance",
    "困ったとき": "Troubleshooting",
    "閉じる": "Close",
    "キャンセル": "Cancel",
    "削除": "Delete",
    "検索": "Search",
    "再読込": "Reload",
    "未取得": "Not received",
    "未設定": "Not set",
    "更新なし": "Up to date",
    "稼働中": "Active",
    "待機中": "Standing by",
    "おすすめ": "Recommended",
    "必須": "Required",
    "好みで": "Optional",
    "やった方がよい": "Advised",
    "今やる": "Due now",
    "期限超過": "Overdue",
    "まもなく": "Upcoming",
    "今日": "Today",
    "明日": "Tomorrow",
    "通常": "Normal",
    "毎日": "Daily",
    "日にちごと": "By date",
    "曜日指定": "By weekday",
    "評価": "Rating",
    "とても悪い": "Very poor",
    "悪い": "Poor",
    "普通": "Fair",
    "良い": "Good",
    "とても良い": "Excellent",
    "処理中...": "Working...",
    "件": " tasks",
    "人時": " person-hours",
    "人": " person",
    "人で": " person",
    "で": "",
    "ほど": " approx.",
    "秒": " sec",
    "箇所": " locations",
    "配置": " placements",
    "項目": " items",

    // Demo fixture names and data labels. User-authored names otherwise remain unchanged.
    "イチゴ実証圃場": "Strawberry Trial Field",
    "イチゴ": "Strawberry",
    "イチゴ畝A": "Strawberry Bed A",
    "イチゴ畝B": "Strawberry Bed B",
    "1号ハウス": "Greenhouse 1",
    "圃場（屋外）": "Field (outdoor)",
    "デモ潅水機1": "Demo Irrigation Controller 1",
    "水やり機": "Irrigation controller",
    "点滴潅水コントローラー": "Drip irrigation controller",
    "潅水1系": "Irrigation Line 1",
    "気温": "Air temperature",
    "湿度": "Humidity",
    "土壌水分": "Soil moisture",
    "光合成有効光量": "Photosynthetically active radiation",
    "気温の目標値を新しいタブで設定": "Open air temperature target settings in a new tab",
    "湿度の目標値を新しいタブで設定": "Open humidity target settings in a new tab",
    "土壌水分の目標値を新しいタブで設定": "Open soil moisture target settings in a new tab",
    "光合成有効光量の目標値を新しいタブで設定": "Open PAR target settings in a new tab",
    "長野県伊那市 西箕輪 / ハウス・温室内": "Ina, Nagano / Greenhouse",
    "ハウス・温室内": "Greenhouse",
    "内部内": "inside",
    "原水タンク": "Source Water Tank",
    "屋外環境センサー": "Outdoor Environment Sensor",
    "育苗ベッド": "Nursery Bed",
    "畝A 土壌センサー": "Bed A Soil Sensor",
    "ハウス温湿度・光センサー": "Greenhouse Climate & Light Sensor",
    "生育記録カメラ": "Growth Record Camera",

    // Field overview and actions.
    "生育モニタ": "Growth monitor",
    "個人設定 ↗": "Preferences ↗",
    "アプリ設定 ↗": "App settings ↗",
    "現在の圃場": "Current field",
    "取得中の環境値": "Latest field readings",
    "今日の記録": "Today's records",
    "目標範囲内": "Within target range",
    "目標内": "On target",
    "要確認": "Needs review",
    "目標未設定": "Target not set",
    "目標値を設定": "Set target",
    "人間が行うこと": "Human work",
    "作業TODO": "Work TODO",
    "作業詳細を開く ›": "Open work details ›",
    "センサー・現在値からの判断": "Decision from sensors and current readings",
    "追加制御は保留して観察を継続": "Keep observing before adding control",
    "現在の最新値と目標レンジから、すぐに制御すべき明確な差分は見つかっていません。": "Current readings show no clear gap that requires immediate control.",
    "観察": "Observation",
    "候補を記録": "Save candidate",
    "カメラで生育状態を確認": "Review growth with cameras",
    "個人設定を新しいタブで開く": "Open preferences in a new tab",
    "アプリ設定を新しいタブで開く": "Open app settings in a new tab",
    "圃場詳細メニュー": "Field detail menu",
    "圃場詳細": "Field details",
    "の目標値を新しいタブで設定": " target settings in a new tab",
    "の詳細を新しいタブで開く": " details in a new tab",
    "の作業イラスト": " work illustration",
    "を新しいタブで編集": " in a new tab",
    "の設置ビュー": " installation view",
    "場所、培地、機器を検索": "Search locations, growing media, and devices",
    "培地、空間、圃場を検索": "Search growing media, spaces, or fields",
    "既存タグを選択、または新しいタグを入力": "Choose an existing tag or enter a new one",
    "作業、作物、場所、値、タグを検索": "Search work, crops, locations, values, or tags",
    "都道府県を検索": "Search prefectures",
    "潅水、EC、収穫など": "Irrigation, EC, harvest, and more",
    "バージョン、ビルドを検索": "Search versions or builds",
    "圃場構成を検索": "Search field structure",
    "圃場の設置階層": "Field installation hierarchy",
    "、圃場詳細を開く（新しいタブ）": ", open field details (new tab)",
    "、配置詳細を開く（新しいタブ）": ", open placement details (new tab)",
    "、機器詳細を開く（新しいタブ）": ", open device details (new tab)",
    "追肥": "Supplemental fertilization",
    "追肥の作業イラスト": "Supplemental fertilization work illustration",
    "2: 悪い": "2: Poor",
    "3: 普通": "3: Fair",
    "4: 良い": "4: Good",
    "イチゴに今、追肥の確認が必要です": "Check now whether the strawberries need supplemental fertilizer",
    "入力された肥効モデルでは、基準日時点の残存見込みが N 0.1158kg, P₂O₅ 0.0579kg, K₂O 0.0869kg あります。追加前に残効と作物の吸収状況を確認するためです。": "The nutrient model estimates 0.1158 kg N, 0.0579 kg P₂O₅, and 0.0869 kg K₂O remaining. Check residual nutrients and crop uptake before adding more.",
    "設置状況": "Installation status",
    "設置ビュー": "Installation view",
    "設置場所と機器": "Locations and devices",
    "圃場構成": "Field structure",

    // Work board and annual outlook.
    "年間栽培カレンダー": "Annual cultivation calendar",
    "年間カレンダーを読み込んでいます": "Loading annual calendar",
    "栽培計画と作業記録を時系列に並べています": "Arranging the cultivation plan and work records on a timeline",
    "年間カレンダーを使用するには JavaScript を有効にしてください。": "Enable JavaScript to use the annual calendar.",
    "圃場の作業": "Field work",
    "全作物をまとめて確認": "Review all crops together",
    "作物別の栽培計画": "Crop plans",
    "栽培基準・施肥・AI計画": "Standards, fertilizer & AI plan",
    "栽培計画の見通し": "Annual work outlook",
    "開始月": "Start month",
    "表示期間": "Range",
    "今月に戻す": "Return to this month",
    "今月から12か月に戻す": "Reset to 12 months from this month",
    "12か月の栽培計画": "12-month cultivation plan",
    "カレンダー表示期間": "Calendar display range",
    "選択した期間に予定または実施記録はありません。": "No planned or completed work in the selected range.",
    "圃場の管理作業": "Field work board",
    "作業を追加": "Add work",
    "この日に行う作業": "Work scheduled for this period",
    "表示する作物": "Crop filter",
    "圃場のすべての作物（8件）": "All crops in this field (8 tasks)",
    "担当者": "Assignee",
    "すべての担当者（おすすめ）": "All assignees (recommended)",
    "未完了": "Planned",
    "作業中": "In progress",
    "確認待ち": "Awaiting review",
    "完了・見送り": "Completed / skipped",
    "担当者未設定": "Unassigned",
    "メンバー別の完遂状況": "Completion by member",
    "あなたの作業実績": "Your work record",
    "管理者が承認した作業だけを「完遂」に集計": "Only manager-approved work counts as completed",
    "現在の称号": "Current milestone",
    "最初の一歩": "First step",
    "スタート地点": "Starting point",
    "着実な実践者": "Steady contributor",
    "頼れるメンバー": "Trusted team member",
    "圃場の達人": "Field expert",
    "継続の名手": "Consistency champion",
    "件 完遂": "completed",
    "件 確認待ち": "awaiting review",
    "最初の承認を待っています": "Waiting for the first approval",
    "すべての節目を達成しました": "All milestones reached",
    "速さや順位ではなく、承認済みの積み重ねを表示します。報酬額や送金状態はまだ扱いません。": "This shows accumulated approved work, not speed or rankings. Payments and transfers are not included yet.",
    "認証済みメンバーの提出記録はまだありません。": "No submissions from authenticated members yet.",
    "着手待ちの作業はありません。": "No planned work.",
    "作業中の項目はありません。": "No work in progress.",
    "管理者の確認を待つ作業はありません。": "No work awaiting manager review.",
    "完了した作業はありません。": "No completed work.",
    "件を状態別に管理": " tasks by status",
    "栽培カレンダー": "Cultivation calendar",
    "へ戻る": " — back",
    "の表示": " view",
    "現在の提案": "Current suggestions",
    "管理作業": "Managed work",
    "管理作業を追加": "Add managed work",
    "作業期間に含まれる日": "Date within the work window",
    "管理作業を検索": "Search managed work",
    "作物、場所、作業名、資材をあいまい検索": "Search field work",
    "担当者で絞り込む": "Filter by assignee",
    "作業ボードの使い方の説明を開く": "Open work board help",
    "作業ボードの使い方の説明": "Work board help",
    "管理作業カンバン": "Managed work board",
    "とはの説明を開く": " help",
    "とはの説明": " help",
    "の詳細を開く": " details",
    "ドラッグして状態を変更": "Drag to change status",

    // Demo crop plan action titles and types.
    "現在の生育状態と直近作業を確認": "Check current growth and recent work",
    "畝に残る肥効と追肥要否を確認": "Check residual nutrients and fertilizer need",
    "病害虫を観察して防除要否を判断": "Inspect pests and decide whether treatment is needed",
    "枝葉の混み具合を確認": "Check canopy density",
    "季節変化に合わせた管理を確認": "Review seasonal management",
    "手動潅水の要否を確認": "Check whether manual irrigation is needed",
    "開花と受粉環境を整える": "Prepare flowering and pollination conditions",
    "適熟果を選んで収穫・品質記録": "Harvest ripe fruit and record quality",
    "収穫": "Harvest",
    "受粉・結実": "Pollination & fruit set",
    "越冬・季節管理": "Overwintering & seasonal care",
    "剪定": "Pruning",
    "防除": "Crop protection",
    "潅水": "Irrigation",

    // Plant question panel visible beside the board.
    "この作物について質問": "Ask about this crop",
    "イチゴの計画と記録を参照": "Using the strawberry plan and records",
    "栽培専用": "Cultivation only",
    "栽培の疑問をすぐ相談できます": "Ask cultivation questions here",
    "計画、作業、施肥、病害虫など、この作物に関する質問を入力してください。": "Ask about this crop's plan, work, fertilizer, pests, or diseases.",
    "栽培について質問する": "Ask a cultivation question",
    "質問を送る": "Send question",
    "質問するには": "To ask a question",
    "質問を入力してください": "Enter a question",
    "の計画と記録を参照": " plan and records",
    "の栽培相談": " cultivation help",
    "過去の栽培相談を検索": "Search previous cultivation questions",
    "過去の質問と回答を検索": "Search previous questions and answers",
    "例：追肥は今必要ですか？": "Example: Is supplemental fertilizer needed now?",
    "実行できません:": "Unavailable:",
    "登録作物と農作業以外の質問は回答・保存しません。農薬は対象作物の登録、ラベル、地域指針を必ず確認してください。": "Questions outside registered crops and farm work are not answered or saved. Always verify pesticide registration, labels, and local guidance.",

    // Work detail and manager review.
    "管理作業の詳細": "Work details",
    "作業詳細を閉じる": "Close work details",
    "作業期間": "Work window",
    "今回の計画開始時": "At plan creation",
    "担当: demo-operator@ina.local": "Assignee: demo-operator@ina.local",
    "担当: demo-worker@ina.local": "Assignee: demo-worker@ina.local",
    "樹勢維持": "Maintain plant vigor",
    "作業履歴確認": "Review work history",
    "今回の作業ノート": "Work decision note",
    "なぜやる？ どう決める？ 何をする？": "Why, how to decide, and what to do",
    "左から順にたどると、今日の判断が分かります。": "Follow the steps to understand today's decision.",
    "この作業を考えたきっかけ": "Why this work was considered",
    "なぜ今、見るの？": "Why check now?",
    "定植後の経過と入力された施肥・防除履歴を現在の樹勢、葉色、用土の状態と照合し、次の作業要否を判断するためです。": "Compare growth since planting and recorded fertilizer and treatment history with current vigor, leaf color, and substrate condition to decide the next action.",
    "作物を見て決める": "Decide from the crop",
    "やるか、今日は見送るか": "Proceed or skip today",
    "やる目安": "Proceed when",
    "前回記録から状態が変化した、または定期確認日になった": "Conditions changed since the previous record, or the scheduled review date has arrived",
    "見送る目安": "Stop when",
    "安全に観察できない天候・環境である": "Weather or field conditions do not allow safe observation",
    "いちばん大切なところ": "Key point",
    "今日やること": "Today's work",
    "過去の作業を再実施扱いにせず、現在の状態と直近作業日を写真・メモで記録します。": "Record current conditions and the latest work date with photos and notes without treating past work as newly completed.",
    "迷わないための作業メモ": "Work checklist",
    "見る場所": "Where to look",
    "株全体と根域": "Whole plant and root zone",
    "見ておくこと": "What to check",
    "葉色、萎れ、新梢、病斑など前回からの変化": "Changes in leaf color, wilting, new shoots, lesions, and other signs",
    "やり方": "Method",
    "観察して記録": "Observe and record",
    "目的": "Purpose",
    "株と根域の変化を早期に見つける": "Detect changes in the plant and root zone early",
    "方法": "Procedure",
    "前回の写真・記録と同じ部位を同じ順で観察する": "Inspect the same areas in the same order as the previous photos and records",
    "頻度": "Frequency",
    "継続確認 / 生育段階と前回記録から定期確認日を決める": "Ongoing / schedule reviews from growth stage and the previous record",
    "手順": "Steps",
    "前回記録と生育段階を確認する": "Review the previous record and growth stage",
    "株全体、葉裏、新梢、株元、培地の順に観察する": "Inspect the whole plant, leaf undersides, new shoots, crown, and substrate in order",
    "変化がある部位を写真と数値で記録する": "Record changed areas with photos and measurements",
    "終了確認": "Completion check",
    "前回からの変化と変化がない項目を記録した": "Changes and unchanged items since the previous check are recorded",
    "注意": "Caution",
    "原因を断定できない症状は事実と推測を分けて記録する": "Separate observed facts from hypotheses when the cause is uncertain",
    "ここまでできたら完了": "Done when",
    "前回からの変化を確認し、必要なら写真とメモを残した": "Changes were checked and photos and notes were saved where needed",
    "この作業の実施準備": "Work readiness",
    "人が確認して実施します": "A person reviews and performs this work",
    "作業ガイド": "Work guide",
    "現在は作業手順と確認点を案内し、人が実施して結果を記録します。": "The Hub provides steps and checkpoints; a person performs the work and records the result.",
    "始める前": "Before starting",
    "この場合は止める": "Stop in this case",
    "終わったら": "After finishing",
    "自動実行はまだ行いません": "No automatic execution",
    "この作業は現在、機器による実行対象ではありません。": "This work is not currently executed by a device.",
    "2026年7月23日 に作業者が実施: 葉色・新葉・土壌水分を確認。生育は安定しており、写真記録も保存しました。": "Completed by the worker on July 23, 2026: checked leaf color, new growth, and soil moisture. Growth was stable and photo evidence was saved.",
    "作業者: demo-operator@ina.local": "Worker: demo-operator@ina.local",
    "作業者:": "Worker:",
    "に作業者が実施: 葉色・新葉・土壌水分を確認。生育は安定しており、写真記録も保存しました。": " — completed by the worker: checked leaf color, new growth, and soil moisture. Growth was stable and photo evidence was saved.",
    "に作業者が実施": " — completed by the worker",
    ": 葉色・新葉・土壌水分を確認。生育は安定しており、写真記録も保存しました。": ": checked leaf color, new growth, and soil moisture. Growth was stable and photo evidence was saved.",
    "実施日から": "About",
    "日後を目安": "days after completion",
    "管理者へ確認を依頼済み": "Submitted for manager review",
    "実施手段": "Work method",
    "次回確認": "Next review",
    "作業実績の確認": "Review work evidence",
    "証跡を見て承認または差戻し": "Approve or return after reviewing the evidence",
    "確認メモ": "Review note",
    "承認メモは任意。差戻し時は修正点を入力してください": "An approval note is optional. For a return, describe what needs correction.",
    "作業者へ差し戻す": "Return to worker",
    "確認して承認": "Approve work",

    // Irrigation device overview.
    "Hub 管理パネル": "Hub Admin",
    "現在値、出力先、動作設定、機器更新を確認します。": "Review live values, outputs, operation settings, and device updates.",
    "ページ移動": "Page navigation",
    "水やり機 / イチゴ実証圃場 / 1号ハウス / 点滴潅水コントローラー ↗": "Irrigation controller / Strawberry Trial Field / Greenhouse 1 / Drip irrigation controller ↗",
    "機器番号を確認（上級者向け）": "View device ID (advanced)",
    "問い合わせや機器交換のときに使用する識別番号です。": "Identifier used for support and device replacement.",
    "現在の潅水判断": "Current irrigation decision",
    "運用判断に必要な情報": "Information for the next operational decision",
    "次の潅水": "Next irrigation",
    "潅水1系 / 1秒": "Irrigation Line 1 / 1 sec",
    "設定を変更 →": "Change setting →",
    "土壌水分しきい値": "Soil moisture threshold",
    "この値以下で潅水を判断": "Irrigate at or below this value",
    "現在の土壌水分": "Current soil moisture",
    "推移を見る →": "View history →",
    "現在の潅水状態": "Current irrigation state",
    "最後に受信した状態から判断": "Based on the latest received status",
    "機器詳細メニュー": "Device detail menu",
    "設置場所・関連先": "Installation & related targets",
    "圃場の設置ビューを正本として、機器の設置先と作用対象を表示します。": "Shows the installation and target based on the field installation view.",
    "動作確認": "Readiness check",
    "動作確認の見方": "Readiness check guide",
    "動作確認の見方を開く": "Open readiness check guide",
    "通信、設定、時刻、出力先を順番に確認します。橙色の項目だけ対応すれば運用を始められます。": "Check communication, configuration, time, and outputs in order. Only amber items require action before operation.",
    "設定を確認": "Review settings",
    "灌水予約": "Irrigation schedules",
    "機器の通信・更新": "Device communication & updates",
    "最終通信": "Last communication",
    "次回起動": "Next wake",
    "現在のバージョン": "Current version",
    "更新状態": "Update status",
    "拡張確認": "Extension check",
    "潅水設備 / デバイス機能": "Irrigation equipment / Device capability",
    "潅水対象": "Irrigation targets",
    "圃場を開く ↗": "Open field ↗",
    "設置ビューを編集 ↗": "Edit installation view ↗",
    "機器と通信": "Device communication",
    "直近の状態を受信済み": "Latest status received",
    "設定の受信": "Configuration receipt",
    "受信済み": "Received",
    "機器がHub設定を読み込みました": "The device loaded the Hub configuration",
    "設定送信後、次回起動を待ちます": "After sending settings, wait for the next wake",
    "時刻合わせ": "Time synchronization",
    "同期済み": "Synchronized",
    "予約時刻の基準は正常です": "Schedule time synchronization is healthy",
    "次回起動時に時刻同期を確認します": "Time sync will be checked at the next wake",
    "出力先": "Outputs",
    "1 系統": "1 line",
    "有効なポンプ・バルブ・電源": "Active pumps, valves, and power outputs",
    "この機器の追加ガイド": "Additional device guidance",
    "Extension 動作確認プラグイン が提供する補助情報です。": "Supplemental information from the Extension readiness plugin.",
    "プラグインが動作しています": "Extension is running",
    "このカードが表示されていれば、WTR向けの概要拡張をHubが安全に読み込めています。": "This card confirms that the Hub safely loaded the WTR overview extension.",
    "1秒 / 潅水1系": "1 sec / Irrigation Line 1",
    "を新しいタブで開く": " in a new tab",
    "圃場を新しいタブで開く": "Open field in a new tab",
    "設置場所と関連先": "Installation and related targets",
    "農業用センサーと制御機器のイラスト": "Illustration of agricultural sensors and controllers",
    "プラグインによる追加情報": " extension information",

    // Irrigation setup and schedule editor.
    "この機器の呼び名": "Device name",
    "表示名": "Display name",
    "メモ": "Notes",
    "水やりセットアップ": "Irrigation setup",
    "水やりセットアップの手順": "Irrigation setup steps",
    "設備をつなぐ": "Connect equipment",
    "接続口から水の行き先を組み立てる": "Build the water route from controller outputs",
    "水やりを決める": "Set irrigation rules",
    "土の乾き具合から判断条件を決める": "Set rules based on soil moisture",
    "予約を組む": "Schedule irrigation",
    "次の起動時刻に合わせて水やりを予約する": "Schedule irrigation for a future wake cycle",
    "水やりの判断": "Irrigation rules",
    "土の乾き具合を見て、水やりを始める目安を決めます。": "Use soil moisture to decide when irrigation should run.",
    "灌水しきい値": "Irrigation threshold",
    "設備のつながり": "Equipment connections",
    "制御ボックスから水を送る設備まで、今のつながりを確認できます。接続図を選ぶとルートを変更できます。": "Review the route from the controller to the irrigation equipment. Select the diagram to edit it.",
    "現在の水やりルートを変更": "Change the current irrigation route",
    "水やりルートを組み立てる": "Build the irrigation route",
    "時刻": "Time",
    "灌水時間（秒）": "Irrigation duration (sec)",
    "水を送る接続先": "Water output",
    "頻度": "Frequency",
    "－ 削除": "− Remove",
    "＋ 水やり予約を追加": "+ Add irrigation schedule",
    "分割灌水": "Pulse irrigation",
    "次回起動時に診断ログを送る": "Send diagnostics at the next wake",
    "下書きを保存": "Save draft",
    "組み立てた設定を機器へ送る": "Send configured settings to device",
    "保存済み設定をもう一度反映": "Send saved settings again"
    ,"機器情報は変更されていません。": "Device information has not changed.",
    "表示情報を保存": "Save display information",
    "水分の目安と予約時刻を決める": "Set the moisture threshold and schedule",
    "センサーを合わせる": "Calibrate sensors",
    "いつもの土に表示を合わせる": "Match readings to the field soil",
    "この値以下を灌水判定に使います": "Use this value or lower for irrigation decisions",
    "強制灌水": "Forced irrigation",
    "はい": "Yes",
    "ON の場合、条件に関わらず予約時刻に灌水します": "When ON, irrigation runs at the scheduled time regardless of conditions",
    "予約数": "Schedule count",
    "最大 8 件まで登録できます": "Up to 8 schedules can be registered",
    "予約時刻には水分条件を無視して灌水する": "Ignore the moisture condition at scheduled times",
    "電源投入時の敷設試験": "Startup installation test",
    "電源投入またはリセット後に一度だけ、選んだ接続口へ短時間通水します。通常運転ではOFFにしてください。": "After power-on or reset, briefly run water through the selected output once. Keep this OFF during normal operation.",
    "敷設試験を有効にする": "Enable installation test",
    "通水時間（秒）": "Run time (sec)",
    "試験する接続口": "Output to test",
    "接続口1": "Output 1",
    "接続口2": "Output 2",
    "接続口1と2": "Outputs 1 and 2",
    "電源を入れるたびに水が出ます。配管と排水を確認し、人が立ち会う敷設試験中だけ有効にしてください。": "Water runs whenever power is applied. Enable this only during a supervised installation test after checking plumbing and drainage.",
    "通信・開発者向け設定": "Communication & developer settings",
    "現在の水やりルート": "Current irrigation route",
    "クリックして変更": "Select to edit",
    "制御": "Control",
    "ボックス": "box",
    "デモ点滴ラインA": "Demo Drip Line A",
    "接続口 1": "Output 1",
    "保存済み設定に、この機種では編集できない接続が 1 件あります。既存値は維持されます。": "The saved configuration contains one connection that this model cannot edit. Its existing value will be preserved.",
    "分割灌水を使う": "Use pulse irrigation",
    "水を出す時間（秒）": "Water-on duration (sec)",
    "水を止める時間（秒）": "Pause duration (sec)",
    "繰り返し回数": "Repeat count",
    "土壌水分計の基準合わせ": "Soil moisture calibration",
    "乾いた状態と十分に湿った状態を順番に記録すると、0〜100%の表示が圃場に合いやすくなります。": "Record dry and fully wet conditions in sequence to calibrate the 0–100% reading for this field.",
    "基準未設定": "Not calibrated",
    "手順を見ながら設定": "Open calibration guide",
    "上級者設定": "Advanced settings",
    "動作設定は変更されていません。": "Operation settings have not changed.",
    "表示情報の説明を開く": "Open display information help",
    "表示情報について": "About display information",
    "水やり判断の説明を開く": "Open irrigation rule help",
    "水やりの判断とは": "About irrigation rules",
    "の説明を開く": " help",
    "制御機器から潅水設備やセンサーへつながるイラスト": "Illustration connecting the controller to irrigation equipment and sensors",
    "予約を削除": "Remove schedule"
  }));

  const phraseTranslations = [...english.entries()]
    .filter(([source, target]) => source.length >= 3 && target)
    .sort(([left], [right]) => right.length - left.length);

  const monthNames = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
  ];

  function translateExact(value) {
    return english.has(value) ? english.get(value) : value;
  }

  function translateDynamic(value) {
    let translated = value;

    translated = translated.replace(/(\d{4})年(\d{1,2})月(\d{1,2})日/g, (_match, year, month, day) => (
      `${monthNames[Number(month) - 1]} ${Number(day)}, ${year}`
    ));
    translated = translated.replace(/(\d{1,2})月(\d{1,2})日/g, (_match, month, day) => (
      `${monthNames[Number(month) - 1]} ${Number(day)}`
    ));
    translated = translated.replace(/(\d{4})年(\d{1,2})月/g, (_match, year, month) => (
      `${monthNames[Number(month) - 1]} ${year}`
    ));
    translated = translated.replace(/〜/g, " – ");
    translated = translated.replace(/^(\d+(?:\.\d+)?)件$/, "$1 tasks");
    translated = translated.replace(/^(\d+) \/ (\d+)件$/, "$1 / $2 tasks");
    translated = translated.replace(/^(\d+(?:\.\d+)?)人時$/, "$1 person-hours");
    translated = translated.replace(/^(\d+)人で$/, "$1 person");
    translated = translated.replace(/^(\d+)人$/, "$1 person");
    translated = translated.replace(/^(\d+)時間$/, "$1 hr");
    translated = translated.replace(/^(\d+)分ほど$/, "About $1 min");
    translated = translated.replace(/^(\d+)分$/, "$1 min");
    translated = translated.replace(/^(\d+)秒$/, "$1 sec");
    translated = translated.replace(/^(\d+)秒前$/, "$1 sec ago");
    translated = translated.replace(/^(\d+)\s+箇所$/, "$1 locations");
    translated = translated.replace(/^(\d+)配置$/, "$1 placements");
    translated = translated.replace(/^(\d+)項目$/, "$1 items");
    translated = translated.replace(/^栽培場所\s+(\d+)件$/, "$1 growing locations");
    translated = translated.replace(/^(\d+)か月$/, "$1 months");
    translated = translated.replace(/^今日\s+(.+)$/, "Today $1");
    translated = translated.replace(/^明日\s+(.+)$/, "Tomorrow $1");
    translated = translated.replace(/^(\d+)分前$/, "$1 min ago");
    translated = translated.replace(/^予定\s+(.+)$/, "Window $1");
    translated = translated.replace(/^しきい値まで\s+(\d+)\s+ポイント$/, "$1 points above threshold");
    translated = translated.replace(/^取得できた(\d+)項目は目標範囲内です$/, "$1 available readings are within target range");
    translated = translated.replace(/^(\d+)件を状態別に管理$/, "Manage $1 tasks by status");
    translated = translated.replace(/^あと(\d+)件で「(.+)」$/, (_match, count, title) => (
      `${count} more to “${translateExact(title)}”`
    ));
    translated = translated.replace(/^最新実施\s+(.+)$/, "Last completed $1");
    translated = translated.replace(/^実施日から\s+(\d+)\s+日後を目安$/, "About $1 days after completion");
    translated = translated.replace(/^目標\s+(.+)$/, "Target $1");
    translated = translated.replace(/^(.*)の設定を変更$/, "Change $1 settings");
    translated = translated.replace(/^(.*)の履歴を見る$/, "View $1 history");
    if (JAPANESE_TEXT.test(translated)) {
      for (const [source, target] of phraseTranslations) {
        if (translated.includes(source)) translated = translated.replaceAll(source, target);
      }
    }
    return translated;
  }

  function translateString(input) {
    if (locale !== "en" || !input || !JAPANESE_TEXT.test(input)) return input;
    const leading = input.match(/^\s*/)?.[0] || "";
    const trailing = input.match(/\s*$/)?.[0] || "";
    const core = input.slice(leading.length, input.length - trailing.length || undefined);
    if (!core) return input;
    const exact = translateExact(core);
    const translated = exact === core ? translateDynamic(core) : exact;
    return `${leading}${translated}${trailing}`;
  }

  function translateElementAttributes(element) {
    for (const name of TRANSLATABLE_ATTRIBUTES) {
      if (!element.hasAttribute(name)) continue;
      const current = element.getAttribute(name) || "";
      const translated = translateString(current);
      if (translated !== current) element.setAttribute(name, translated);
    }
  }

  function translateTree(root) {
    if (locale !== "en" || !root) return;
    if (root.nodeType === Node.TEXT_NODE) {
      const parent = root.parentElement;
      if (!parent || SKIPPED_ELEMENTS.has(parent.tagName)) return;
      const translated = translateString(root.nodeValue || "");
      if (translated !== root.nodeValue) root.nodeValue = translated;
      return;
    }
    if (!(root instanceof Element) && root !== document) return;
    if (root instanceof Element) translateElementAttributes(root);
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
    let node = walker.nextNode();
    while (node) {
      if (node.nodeType === Node.ELEMENT_NODE) {
        translateElementAttributes(node);
      } else {
        const parent = node.parentElement;
        if (parent && !SKIPPED_ELEMENTS.has(parent.tagName)) {
          const translated = translateString(node.nodeValue || "");
          if (translated !== node.nodeValue) node.nodeValue = translated;
        }
      }
      node = walker.nextNode();
    }
  }

  function localeUrl(nextLocale) {
    const url = new URL(window.location.href);
    if (nextLocale === "en") url.searchParams.set("lang", "en");
    else url.searchParams.delete("lang");
    return `${url.pathname}${url.search}${url.hash}`;
  }

  function buildLocaleSwitcher() {
    const nav = document.createElement("nav");
    nav.className = "ina-locale-switcher";
    nav.dataset.uiLocaleSwitcher = "true";
    nav.setAttribute("aria-label", locale === "en" ? "Language" : "表示言語");
    for (const option of [
      { value: "ja", label: "JA", aria: locale === "en" ? "Switch to Japanese" : "日本語に切り替え" },
      { value: "en", label: "EN", aria: locale === "en" ? "English" : "英語に切り替え" },
    ]) {
      const link = document.createElement("a");
      link.href = localeUrl(option.value);
      link.dataset.localeOption = option.value;
      link.textContent = option.label;
      link.setAttribute("aria-label", option.aria);
      if (option.value === locale) link.setAttribute("aria-current", "true");
      nav.append(link);
    }
    return nav;
  }

  function ensureLocaleSwitcher() {
    if (document.querySelector("[data-ui-locale-switcher]")) return;
    const destination = document.querySelector(".header-actions")
      || document.querySelector(".topbar .nav")
      || document.querySelector(".calendar-header")
      || document.querySelector(".topbar");
    if (!destination) return;
    const switcher = buildLocaleSwitcher();
    if (destination.matches(".header-actions, .nav")) destination.prepend(switcher);
    else destination.append(switcher);
  }

  function preserveLocaleInLinks(root = document) {
    if (locale !== "en") return;
    const links = root instanceof HTMLAnchorElement ? [root] : root.querySelectorAll?.("a[href]") || [];
    for (const link of links) {
      if (link.dataset.localeOption || link.dataset.localePreserved === "true") continue;
      const rawHref = link.getAttribute("href") || "";
      if (!rawHref || rawHref.startsWith("#") || rawHref.startsWith("mailto:") || rawHref.startsWith("javascript:")) continue;
      let url;
      try {
        url = new URL(link.href, window.location.href);
      } catch {
        continue;
      }
      if (url.origin !== window.location.origin || url.pathname.startsWith("/static/")) continue;
      url.searchParams.set("lang", "en");
      link.href = `${url.pathname}${url.search}${url.hash}`;
      link.dataset.localePreserved = "true";
    }
  }

  function finishPass(root = document) {
    translateTree(root);
    preserveLocaleInLinks(root);
    ensureLocaleSwitcher();
  }

  function start() {
    document.documentElement.lang = locale;
    finishPass(document);
    document.title = translateString(document.title);

    let scheduled = false;
    const pendingRoots = new Set();
    const flush = () => {
      scheduled = false;
      for (const root of pendingRoots) finishPass(root);
      pendingRoots.clear();
      finishPass(document);
      document.body.dataset.uiLocaleReady = "true";
    };
    const schedule = (root) => {
      pendingRoots.add(root);
      if (scheduled) return;
      scheduled = true;
      window.requestAnimationFrame(flush);
    };
    const observer = new MutationObserver((records) => {
      for (const record of records) {
        if (record.type === "characterData") schedule(record.target);
        if (record.type === "attributes") schedule(record.target);
        for (const node of record.addedNodes) schedule(node);
      }
    });
    observer.observe(document.body, {
      subtree: true,
      childList: true,
      characterData: true,
      attributes: true,
      attributeFilter: TRANSLATABLE_ATTRIBUTES,
    });
    document.body.dataset.uiLocaleReady = "true";
    window.INA_UI_LOCALE = Object.freeze({ locale, translate: translateString });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
