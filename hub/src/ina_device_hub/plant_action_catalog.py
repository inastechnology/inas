import copy

_ACTION_TYPES = (
    {
        "code": "fertilization",
        "label": "追肥",
        "todo_label": "追肥の確認",
        "illustration_url": "/static/plant-actions/fertilization.webp",
        "accent": "#6f7f39",
        "keywords": ["施肥", "追肥", "肥料", "液肥", "養分", "fertilization", "feeding"],
    },
    {
        "code": "pest_control",
        "label": "防除",
        "todo_label": "病害虫と防除の確認",
        "illustration_url": "/static/plant-actions/pest-control.webp",
        "accent": "#9a5b34",
        "keywords": ["防除", "消毒", "農薬", "散布", "病害虫", "害虫", "pest control", "spraying"],
    },
    {
        "code": "pruning",
        "label": "剪定",
        "todo_label": "剪定の確認",
        "illustration_url": "/static/plant-actions/pruning.webp",
        "accent": "#3f7661",
        "keywords": ["剪定", "切り戻し", "摘心", "枝切り", "pruning", "trim"],
    },
    {
        "code": "girdling",
        "label": "環状剥皮",
        "todo_label": "環状剥皮の判断",
        "illustration_url": "",
        "accent": "#7f654d",
        "keywords": ["環状剥皮", "環状はく皮", "girdling"],
    },
    {
        "code": "pollination",
        "label": "受粉・結実",
        "todo_label": "受粉条件の確認",
        "illustration_url": "/static/plant-actions/pollination.webp",
        "accent": "#ad7733",
        "keywords": ["受粉", "人工授粉", "結実", "開花", "pollination", "fruit set"],
    },
    {
        "code": "gibberellin_treatment",
        "label": "ジベレリン処理",
        "todo_label": "ジベレリン処理の確認",
        "illustration_url": "/static/plant-actions/gibberellin-treatment.webp",
        "accent": "#665b9b",
        "keywords": ["ジベレリン", "ジベ処理", "GA3", "植物成長調整剤", "gibberellin", "growth regulator"],
    },
    {
        "code": "harvest",
        "label": "収穫",
        "todo_label": "収穫判断",
        "illustration_url": "/static/plant-actions/harvest.webp",
        "accent": "#a8463f",
        "keywords": ["収穫", "摘み取り", "採果", "harvest", "picking"],
    },
    {
        "code": "repotting",
        "label": "植え替え",
        "todo_label": "植え替え判断",
        "illustration_url": "",
        "accent": "#75644e",
        "keywords": ["植え替え", "鉢増し", "移植", "repotting", "transplanting"],
    },
    {
        "code": "watering",
        "label": "潅水",
        "todo_label": "潅水判断",
        "illustration_url": "/static/plant-actions/watering.webp",
        "accent": "#397d91",
        "keywords": ["潅水", "灌水", "水やり", "点滴", "給水", "watering", "irrigation"],
    },
    {
        "code": "observation",
        "label": "観察",
        "todo_label": "生育確認",
        "illustration_url": "",
        "accent": "#64746a",
        "keywords": ["観察", "確認", "巡回", "生育", "observation", "inspection"],
    },
    {
        "code": "winter_care",
        "label": "越冬・季節管理",
        "todo_label": "季節管理の見直し",
        "illustration_url": "",
        "accent": "#57758a",
        "keywords": ["越冬", "冬越し", "季節管理", "防寒", "winter care", "dormancy"],
    },
    {
        "code": "other",
        "label": "その他",
        "todo_label": "作業確認",
        "illustration_url": "",
        "accent": "#77736c",
        "keywords": ["その他", "作業", "other"],
    },
)

_ACTION_TYPE_BY_CODE = {item["code"]: item for item in _ACTION_TYPES}
_ACTION_TYPE_ALIASES = {
    "施肥": "fertilization",
    "追肥": "fertilization",
    "fertilizer": "fertilization",
    "fertilizing": "fertilization",
    "feeding": "fertilization",
    "防除": "pest_control",
    "病害虫防除": "pest_control",
    "spraying": "pest_control",
    "pesticide": "pest_control",
    "剪定": "pruning",
    "trim": "pruning",
    "trimming": "pruning",
    "環状剥皮": "girdling",
    "受粉": "pollination",
    "人工授粉": "pollination",
    "artificial_pollination": "pollination",
    "fruit_set": "pollination",
    "ジベレリン": "gibberellin_treatment",
    "ジベレリン処理": "gibberellin_treatment",
    "ジベ処理": "gibberellin_treatment",
    "gibberellin": "gibberellin_treatment",
    "gibberellin_application": "gibberellin_treatment",
    "ga3_treatment": "gibberellin_treatment",
    "plant_growth_regulator": "gibberellin_treatment",
    "収穫": "harvest",
    "植え替え": "repotting",
    "潅水": "watering",
    "灌水": "watering",
    "水やり": "watering",
    "irrigation": "watering",
    "water": "watering",
    "観察": "observation",
    "inspection": "observation",
    "越冬": "winter_care",
    "季節管理": "winter_care",
    "seasonal_care": "winter_care",
}


def plant_action_types():
    return copy.deepcopy(list(_ACTION_TYPES))


def plant_action_type_codes():
    return frozenset(_ACTION_TYPE_BY_CODE)


def normalize_plant_action_type(value, default="other"):
    code = str(value or "").strip().casefold().replace("-", "_").replace(" ", "_")
    code = _ACTION_TYPE_ALIASES.get(code, code)
    return code if code in _ACTION_TYPE_BY_CODE else default


def is_known_plant_action_type(value):
    marker = "__unknown__"
    return normalize_plant_action_type(value, marker) != marker


def plant_action_type(value):
    code = normalize_plant_action_type(value)
    return copy.deepcopy(_ACTION_TYPE_BY_CODE[code])
