import copy

ACTION_WORK_PLAN_DEFAULTS = {
    "observation": {
        "targets": ["株全体と根域"],
        "checkpoints": ["葉色、萎れ、新梢、病斑など前回からの変化"],
        "methods": [("observe-and-record", "観察して記録", "observation")],
    },
    "fertilization": {
        "targets": ["根域・培地", "葉と新梢"],
        "checkpoints": ["葉色と樹勢", "土壌・排液のEC", "前回施肥日と施肥量"],
        "methods": [
            ("solid-fertilizer", "固形肥料を施す", "material_application"),
            ("liquid-fertilizer", "液肥を施す", "material_application"),
            ("fertilization-review", "状態を確認して今回は見送る", "observation"),
        ],
    },
    "pest_control": {
        "targets": ["葉・新芽・株元の病害虫"],
        "checkpoints": ["葉裏の虫体と卵", "若芽の食害・巻葉・変色", "株元の病斑と腐敗"],
        "methods": [
            ("pest-observation", "観察して記録", "observation"),
            ("physical-removal", "捕殺・被害部の除去", "physical"),
            ("physical-cleaning", "洗浄・清掃・隔離", "physical"),
        ],
    },
    "pruning": {
        "targets": ["枯枝・交差枝・徒長枝", "混み合った枝葉"],
        "checkpoints": ["剪定適期", "花芽・結果枝の位置", "樹形、採光、風通し"],
        "methods": [("prune", "剪定する", "manual"), ("pinch", "芽かき・摘心を行う", "manual")],
    },
    "girdling": {
        "targets": ["処理対象の主枝・亜主枝"],
        "checkpoints": ["樹勢と処理適期", "処理部位の太さと前年の回復状態"],
        "methods": [("girdling", "環状剥皮を行う", "manual")],
    },
    "pollination": {
        "targets": ["開花中の花・花房"],
        "checkpoints": ["開花率、花粉の状態、訪花昆虫、天候"],
        "methods": [("pollination-check", "自然受粉を確認", "observation"), ("hand-pollination", "人工受粉する", "manual")],
    },
    "gibberellin_treatment": {
        "targets": ["処理適期の花房・果房"],
        "checkpoints": ["満開日と処理適期", "作物・品種・目的に対する登録内容"],
        "methods": [("gibberellin-treatment", "登録内容に従って処理", "material_application")],
    },
    "harvest": {
        "targets": ["収穫適期の果実・作物"],
        "checkpoints": ["色、硬さ、糖度などの成熟状態", "傷みや病害虫被害"],
        "methods": [("harvest", "適熟のものを収穫", "manual")],
    },
    "repotting": {
        "targets": ["根鉢と用土"],
        "checkpoints": ["根詰まり、根腐れ、用土劣化", "植え替え適期と鉢サイズ"],
        "methods": [("repot", "植え替える", "manual"), ("soil-refresh", "用土を更新する", "manual")],
    },
    "watering": {
        "targets": ["根域・培地"],
        "checkpoints": ["潅水前後の土壌水分", "鉢底・排水口からの排水", "天候と直近の潅水記録"],
        "methods": [("manual-watering", "手動で潅水", "manual"), ("device-watering", "潅水設備で潅水", "device")],
    },
    "winter_care": {
        "targets": ["株全体と根域"],
        "checkpoints": ["最低気温、休眠状態、寒風、凍結・霜のリスク"],
        "methods": [("protect", "防寒・保温対策を行う", "manual"), ("seasonal-review", "季節管理を見直す", "observation")],
    },
    "other": {
        "targets": ["作業対象"],
        "checkpoints": ["実施前後の状態と変化"],
        "methods": [("planned-work", "計画した作業を行う", "manual")],
    },
}

ACTION_WORK_PLAN_GUIDANCE = {
    "observation": {
        "start_conditions": ["前回記録から状態が変化した、または定期確認日になった"],
        "skip_conditions": ["安全に観察できない天候・環境である"],
        "completion_criteria": ["前回からの変化を確認し、必要なら写真とメモを残した"],
    },
    "fertilization": {
        "start_conditions": ["活着しており、葉色・樹勢・ECなどから養分不足が疑われる"],
        "skip_conditions": ["根傷み、生育停止、過湿、EC高値、施肥直後のいずれかに該当する"],
        "completion_criteria": ["使用資材、量、施肥場所を記録し、葉や根へ直接触れた肥料がない"],
    },
    "pest_control": {
        "start_conditions": ["対象病害虫または疑わしい症状を確認した"],
        "skip_conditions": ["対象を同定できない、または製品ラベルの適用作物・使用条件を確認できない"],
        "completion_criteria": ["処理範囲と使用方法を記録し、次回の再発確認日を決めた"],
    },
    "pruning": {
        "start_conditions": ["作物・品種の剪定適期で、切る枝と残す枝を判別できる"],
        "skip_conditions": ["樹勢が弱い、強い雨や高温が続く、花芽・結果枝を判別できない"],
        "completion_criteria": ["切り残しや裂けを確認し、切り口と樹形を記録した"],
    },
    "girdling": {
        "start_conditions": ["目的、対象枝、処理適期を確認できる"],
        "skip_conditions": ["樹勢が弱い、前年処理部が回復していない、対象部位を判断できない"],
        "completion_criteria": ["処理幅と部位を記録し、回復確認日を決めた"],
    },
    "pollination": {
        "start_conditions": ["対象の花が適期に開花している"],
        "skip_conditions": ["花が濡れている、花粉状態が悪い、または開花適期外である"],
        "completion_criteria": ["処理した花・花房と方法を記録した"],
    },
    "gibberellin_treatment": {
        "start_conditions": ["対象作物・品種・目的に対する登録と処理適期を確認できる"],
        "skip_conditions": ["満開日、処理回数、濃度、適用条件のいずれかを確認できない"],
        "completion_criteria": ["処理した花房・果房、濃度、処理回数を記録した"],
    },
    "harvest": {
        "start_conditions": ["色、硬さ、糖度などが収穫基準に達している"],
        "skip_conditions": ["未熟、降雨直後、または病害虫・腐敗の選別ができない"],
        "completion_criteria": ["収穫量と品質、残した未熟果を記録した"],
    },
    "repotting": {
        "start_conditions": ["根詰まりや用土劣化を確認し、植え替え適期である"],
        "skip_conditions": ["極端な高温・低温、開花・結実の最盛期、または株が著しく弱っている"],
        "completion_criteria": ["根鉢、用土、鉢サイズ、植え替え後の潅水を記録した"],
    },
    "watering": {
        "start_conditions": ["培地の乾き、土壌水分、天候から潅水が必要と判断できる"],
        "skip_conditions": ["培地が十分湿っている、排水不良、降雨直前のいずれかに該当する"],
        "completion_criteria": ["根域全体へ水が届き、排水と潅水後の水分変化を確認した"],
    },
    "winter_care": {
        "start_conditions": ["最低気温や休眠状態から防寒・季節管理の変更が必要である"],
        "skip_conditions": ["対策により過湿、蒸れ、日照不足を招く可能性が高い"],
        "completion_criteria": ["対策後の温度、通気、乾き方を確認できる状態にした"],
    },
    "other": {
        "start_conditions": ["作業目的と対象を確認できる"],
        "skip_conditions": ["安全条件または実施判断の根拠を確認できない"],
        "completion_criteria": ["実施内容と作業後の状態を記録した"],
    },
}

WORK_METHOD_GUIDANCE = {
    "solid-fertilizer": {
        "purpose": "根域へ養分を補給する",
        "application_method": "株元へ集中させず、製品表示に従って根域へ均等に施す",
        "procedure_steps": ["前回施肥日と現在の葉色・樹勢・ECを確認する", "製品表示の対象作物と使用量を確認する", "根域へ均等に施し、必要に応じて潅水する"],
        "completion_checks": ["肥料が葉や幹へ直接触れていない", "使用量と施肥場所を記録した"],
        "precautions": ["根傷み、過湿、EC高値のときは施肥しない"],
    },
    "liquid-fertilizer": {
        "purpose": "潅水と合わせて速やかに養分を補給する",
        "application_method": "製品表示の希釈倍率を守り、乾き切った根へ高濃度液を与えない",
        "procedure_steps": ["原液量と水量から希釈倍率を確認する", "必要なら先に培地を軽く湿らせる", "根域へ均等に施し、排液やEC変化を確認する"],
        "completion_checks": ["使用製品、希釈倍率、施用量を記録した"],
        "precautions": ["製品表示より濃くしない", "他資材との混用可否を推測しない"],
    },
    "prune": {
        "purpose": "樹形、採光、風通しを整える",
        "application_method": "切る枝と残す枝を先に決め、清潔な刃物で枝の付け根または適切な芽の上を切る",
        "procedure_steps": ["枯枝・病枝から確認する", "花芽・結果枝と樹形を確認して切る枝に印を付ける", "一度に切り過ぎず、切り口と全体のバランスを確認する"],
        "completion_checks": ["裂けた切り口や切り残しがない", "剪定前後の樹形を記録した"],
        "precautions": ["剪定適期と樹勢を確認し、判断できない枝は残す"],
    },
    "manual-watering": {
        "purpose": "根域へ必要な水分を補給する",
        "application_method": "根域全体へゆっくり与え、排水口または下層への到達を確認する",
        "procedure_steps": ["潅水前の培地と水分値を確認する", "表面だけでなく根域全体へゆっくり与える", "排水と潅水後の水分変化を確認する"],
        "completion_checks": ["根域全体へ水が届いた", "過剰な滞水がない"],
        "precautions": ["固定間隔だけで判断せず、天候と培地の乾きを優先する"],
    },
    "device-watering": {
        "purpose": "潅水設備で対象培地へ均一に給水する",
        "application_method": "対象系統、運転時間、流量を確認して運転し、末端の吐出と排水を確認する",
        "procedure_steps": ["対象培地と潅水系統が一致しているか確認する", "運転を開始して吐出・漏水・詰まりを確認する", "停止後に水分変化と排水を確認する"],
        "completion_checks": ["対象全体で吐出を確認した", "運転時間と水分変化を記録した"],
        "precautions": ["無人運転前に漏水、空運転、詰まりを確認する"],
    },
    "physical-removal": {
        "purpose": "確認した病害虫や被害部を物理的に除去する",
        "application_method": "対象を確認してから虫体または被害部を除去し、圃場外で適切に処理する",
        "procedure_steps": ["対象と被害範囲を確認する", "健全部への広がりを避けて除去する", "周辺株を確認し、再発確認日を決める"],
        "completion_checks": ["対象と処理範囲を記録した", "使用した器具を清掃した"],
        "precautions": ["病害が疑われる場合は器具を株間で使い回さない"],
    },
}

WORK_METHOD_GUIDANCE.update(
    {
        "observe-and-record": {
            "purpose": "株と根域の変化を早期に見つける",
            "application_method": "前回の写真・記録と同じ部位を同じ順で観察する",
            "procedure_steps": ["前回記録と生育段階を確認する", "株全体、葉裏、新梢、株元、培地の順に観察する", "変化がある部位を写真と数値で記録する"],
            "completion_checks": ["前回からの変化と変化がない項目を記録した"],
            "precautions": ["原因を断定できない症状は事実と推測を分けて記録する"],
        },
        "fertilization-review": {
            "purpose": "不要な施肥を避け、次回判断の根拠を残す",
            "application_method": "葉色、樹勢、培地または排液EC、前回施肥日を確認して見送り理由を記録する",
            "procedure_steps": ["前回施肥日と使用量を確認する", "葉色、伸長、EC、根域を確認する", "見送り理由と次回確認日を記録する"],
            "completion_checks": ["施肥しない理由と再確認条件を記録した"],
            "precautions": ["単一の症状だけで養分不足と断定しない"],
        },
        "pest-observation": {
            "purpose": "病害虫と被害範囲を確認し、対処の要否を判断する",
            "application_method": "新芽、葉表、葉裏、枝、株元を順に確認し、症状と虫体を分けて記録する",
            "procedure_steps": [
                "問題が出やすい部位を確認する",
                "虫体、卵、食害、病斑の有無と範囲を記録する",
                "同定できない場合は写真を残して薬剤処理を保留する",
            ],
            "completion_checks": ["対象、被害範囲、写真、次回確認日を記録した"],
            "precautions": ["症状だけで病害虫名を断定しない"],
        },
        "physical-cleaning": {
            "purpose": "伝染源や害虫の拡散経路を減らす",
            "application_method": "落葉、被害残渣、汚れを除去し、必要に応じて対象株を隔離する",
            "procedure_steps": ["処理範囲と健全部を分ける", "残渣を周囲へ広げず回収する", "器具と作業場所を清掃し、周辺株を確認する"],
            "completion_checks": ["残渣を回収し、周辺株と器具を確認した"],
            "precautions": ["病害が疑われる残渣を未処理のまま栽培場所へ残さない"],
        },
        "pinch": {
            "purpose": "不要な新梢を整理し、生育と着果のバランスを整える",
            "application_method": "残す芽と花・果実の位置を確認し、対象の芽または先端だけを除く",
            "procedure_steps": ["生育目的と残す芽を確認する", "対象だけを清潔な手または器具で除く", "作業後の葉数と全体のバランスを確認する"],
            "completion_checks": ["残す芽や結果部を傷めず、除去箇所を記録した"],
            "precautions": ["一度に除去し過ぎず、判断できない芽は残す"],
        },
        "girdling": {
            "purpose": "登録した栽培目的に対して同化産物の移動を一時的に調整する",
            "application_method": "対象枝、処理幅、深さ、時期を決め、木部を傷つけないよう処理する",
            "procedure_steps": ["樹勢、対象枝、前年処理部、実施目的を確認する", "処理位置と幅を記録してから作業する", "処理部を撮影し、癒合確認日を設定する"],
            "completion_checks": ["処理位置と幅を記録し、木部への過度な損傷がない"],
            "precautions": ["経験がない場合は作物・品種に詳しい指導者の確認を得る", "樹勢が弱い株や未回復の枝へ繰り返さない"],
        },
        "pollination-check": {
            "purpose": "自然受粉の成立条件と補助作業の要否を確認する",
            "application_method": "開花率、花粉、天候、訪花昆虫、異品種の開花を確認する",
            "procedure_steps": ["対象花と開花段階を確認する", "花粉状態、天候、訪花状況を確認する", "不足があれば人工受粉の対象と時刻を決める"],
            "completion_checks": ["受粉条件と人工受粉の要否を記録した"],
            "precautions": ["結実前に受粉成立を断定しない"],
        },
        "hand-pollination": {
            "purpose": "自然受粉を補助し、対象花へ適合する花粉を付着させる",
            "application_method": "適期の花から採った適合花粉を、乾いた対象花の柱頭へ付着させる",
            "procedure_steps": [
                "対象品種と花粉親の適合性、開花段階を確認する",
                "乾いた花から花粉を採り、対象花へ付着させる",
                "処理した花または花房と日時を記録する",
            ],
            "completion_checks": ["処理対象、花粉親、実施日時を記録した"],
            "precautions": ["濡れた花や適期外の花には実施しない"],
        },
        "gibberellin-treatment": {
            "purpose": "対象作物・品種で登録された目的に沿って生育または結実を調整する",
            "application_method": "製品ラベルの作物、品種、目的、時期、濃度、回数、処理方法を照合して実施する",
            "amount_or_rate": "対象製品の登録ラベルで濃度と処理量を確認",
            "procedure_steps": ["満開日、対象品種、処理目的、処理回数を確認する", "製品ラベルに従って調製する", "処理対象、濃度、日時、回数を記録する"],
            "completion_checks": ["対象、濃度、処理回数、実施日時を記録した"],
            "precautions": ["登録を確認できない作物・品種・目的には使用しない", "記憶や一般例だけで濃度を決めない"],
        },
        "harvest": {
            "purpose": "目標品質に達した作物を傷めずに収穫する",
            "application_method": "色、硬さ、糖度など作物ごとの成熟基準で選別して収穫する",
            "procedure_steps": [
                "収穫基準と前回の成熟状態を確認する",
                "病害虫や傷みを分けながら適熟のものだけを収穫する",
                "収穫量、品質、残した未熟果を記録する",
            ],
            "completion_checks": ["収穫量と品質を記録し、株や残果を傷めていない"],
            "precautions": ["農薬使用履歴がある場合は収穫前日数を確認する"],
        },
        "repot": {
            "purpose": "根詰まりを解消し、適切な根域と排水性を確保する",
            "application_method": "根鉢に合う鉢と用土を準備し、根を乾かさず同じ植え付け深さで植え替える",
            "procedure_steps": [
                "植え替え適期、根鉢、用土、次の鉢サイズを確認する",
                "傷んだ根を必要最小限だけ整理して植え付ける",
                "十分に潅水し、置き場所と確認日を記録する",
            ],
            "completion_checks": ["植え付け深さ、排水、株の固定を確認した"],
            "precautions": ["開花・結実最盛期や極端な高温・低温時は避ける"],
        },
        "soil-refresh": {
            "purpose": "劣化した用土の物理性と根域環境を改善する",
            "application_method": "根の状態を確認し、作物に適合する新しい用土へ必要範囲を更新する",
            "procedure_steps": ["用土劣化、排水、pH、EC、根を確認する", "更新範囲と用土配合を記録して交換する", "潅水後の排水と株の安定を確認する"],
            "completion_checks": ["用土、更新範囲、排水状態を記録した"],
            "precautions": ["必要なpHや保水・排水条件と合わない用土へ一括交換しない"],
        },
        "protect": {
            "purpose": "低温、霜、寒風による株と根域の障害を減らす",
            "application_method": "最低気温、風、株の耐寒性に合わせて根域保護、被覆、移動を選ぶ",
            "procedure_steps": ["予想最低気温と株の休眠・耐寒状態を確認する", "通気と日照を妨げ過ぎない方法で保護する", "対策後の温度、結露、乾き方を確認する"],
            "completion_checks": ["保護範囲、通気、固定状態を確認した"],
            "precautions": ["密閉による蒸れ、日中の高温、過湿を避ける"],
        },
        "seasonal-review": {
            "purpose": "季節変化に合わせて潅水、施肥、置き場所を見直す",
            "application_method": "気温、日長、休眠、生育速度と現在設定を照合する",
            "procedure_steps": ["直近の気温と生育変化を確認する", "潅水、施肥、防寒、置き場所を順に確認する", "変更内容と次回見直し条件を記録する"],
            "completion_checks": ["変更した設定と変更しなかった理由を記録した"],
            "precautions": ["複数条件を一度に大きく変えず、変化を追跡できるようにする"],
        },
        "planned-work": {
            "purpose": "登録した目的に沿って作業し、結果を追跡できるようにする",
            "application_method": "対象、開始条件、安全条件、終了条件を確認してから実施する",
            "procedure_steps": ["作業目的、対象、開始条件を確認する", "必要な安全対策を行って作業する", "作業後の状態と次回確認日を記録する"],
            "completion_checks": ["対象、実施内容、作業後の状態を記録した"],
            "precautions": ["実施条件を確認できない作業は保留する"],
        },
    }
)

WORK_METHOD_FREQUENCY = {
    "observe-and-record": {"mode": "continuous", "basis": "生育段階と前回記録から定期確認日を決める"},
    "solid-fertilizer": {"mode": "interval", "basis": "製品表示、前回施肥日、葉色、樹勢、ECから次回要否を判断する"},
    "liquid-fertilizer": {"mode": "interval", "basis": "製品表示、前回施肥日、葉色、樹勢、ECから次回要否を判断する"},
    "fertilization-review": {"mode": "as_needed", "basis": "施肥開始条件が満たされるまで再確認する"},
    "pest-observation": {"mode": "continuous", "basis": "発生時期、被害程度、前回結果から確認間隔を決める"},
    "physical-removal": {"mode": "as_needed", "basis": "再発・残存を確認して追加除去を判断する"},
    "physical-cleaning": {"mode": "as_needed", "basis": "再発・拡大を確認して追加処置を判断する"},
    "prune": {"mode": "seasonal", "basis": "作物・品種の剪定適期と樹勢に基づく"},
    "pinch": {"mode": "seasonal", "basis": "新梢の伸長と生育段階に応じて判断する"},
    "girdling": {"mode": "seasonal", "max_applications": 1, "basis": "樹勢と前年処理部の回復を確認する"},
    "pollination-check": {"mode": "continuous", "basis": "開花期間中の花の進みと天候に応じて確認する"},
    "hand-pollination": {"mode": "seasonal", "basis": "開花期間と受粉適期に合わせる"},
    "gibberellin-treatment": {"mode": "seasonal", "basis": "製品ラベルの処理時期と使用回数に従う"},
    "harvest": {"mode": "continuous", "basis": "成熟の進みと収穫基準に応じて判断する"},
    "repot": {"mode": "as_needed", "basis": "根詰まり、用土劣化、鉢サイズから判断する"},
    "soil-refresh": {"mode": "as_needed", "basis": "用土劣化と根域状態から判断する"},
    "manual-watering": {"mode": "as_needed", "basis": "培地の乾き、土壌水分、天候、排水から都度判断する"},
    "device-watering": {"mode": "as_needed", "basis": "土壌水分、天候、運転後の変化から都度判断する"},
    "protect": {"mode": "seasonal", "basis": "予報、最低気温、株の休眠状態に応じて見直す"},
    "seasonal-review": {"mode": "seasonal", "basis": "季節の変わり目と生育状態に応じて見直す"},
    "planned-work": {"mode": "as_needed", "basis": "登録した作業規則と現在の状態で判断する"},
}


def default_action_work_plan(action_type: str):
    definition = ACTION_WORK_PLAN_DEFAULTS.get(action_type, ACTION_WORK_PLAN_DEFAULTS["other"])
    guidance = ACTION_WORK_PLAN_GUIDANCE.get(action_type, ACTION_WORK_PLAN_GUIDANCE["other"])
    return {
        "targets": copy.deepcopy(definition["targets"]),
        "start_conditions": copy.deepcopy(guidance["start_conditions"]),
        "skip_conditions": copy.deepcopy(guidance["skip_conditions"]),
        "checkpoints": copy.deepcopy(definition["checkpoints"]),
        "method_options": [_method_option(item) for item in definition["methods"]],
        "completion_criteria": copy.deepcopy(guidance["completion_criteria"]),
    }


def _method_option(value):
    method_id, label, method_type = value
    guidance = WORK_METHOD_GUIDANCE.get(method_id, {})
    frequency = WORK_METHOD_FREQUENCY.get(method_id, {})
    return {
        "id": method_id,
        "label": label,
        "method_type": method_type,
        "material_name": "",
        "registration_number": "",
        "purpose": guidance.get("purpose", label),
        "application_method": guidance.get("application_method", label),
        "amount_or_rate": guidance.get("amount_or_rate", ""),
        "procedure_steps": copy.deepcopy(guidance.get("procedure_steps", [label])),
        "completion_checks": copy.deepcopy(guidance.get("completion_checks", [])),
        "precautions": copy.deepcopy(guidance.get("precautions", [])),
        "frequency": {
            "mode": frequency.get("mode", "as_needed"),
            "min_interval_days": frequency.get("min_interval_days"),
            "preferred_interval_days": frequency.get("preferred_interval_days"),
            "max_interval_days": frequency.get("max_interval_days"),
            "max_applications": frequency.get("max_applications"),
            "basis": frequency.get("basis", "作業規則と現在の状態で判断する"),
        },
        "instructions": "",
        "follow_up_days_default": None,
        "source_name": "",
        "source_url": "",
        "source_checked_at": "",
    }
