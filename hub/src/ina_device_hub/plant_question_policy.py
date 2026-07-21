"""Scope and safety checks for the cultivation chat before an AI call is made."""

import re
import unicodedata

_AGRICULTURE_TERMS = (
    "栽培",
    "作物",
    "植物",
    "野菜",
    "果樹",
    "花",
    "ハーブ",
    "苗",
    "種",
    "播種",
    "定植",
    "植え",
    "育苗",
    "生育",
    "発芽",
    "開花",
    "結実",
    "収穫",
    "葉",
    "茎",
    "枝",
    "根",
    "実",
    "果実",
    "花芽",
    "新梢",
    "樹勢",
    "土",
    "培地",
    "畝",
    "鉢",
    "圃場",
    "ハウス",
    "水やり",
    "潅水",
    "灌水",
    "施肥",
    "肥料",
    "追肥",
    "堆肥",
    "液肥",
    "ec",
    "ph",
    "npk",
    "土壌水分",
    "日照",
    "光量",
    "温度",
    "湿度",
    "天気",
    "雨",
    "霜",
    "病気",
    "病害",
    "害虫",
    "虫",
    "農薬",
    "防除",
    "剪定",
    "誘引",
    "摘果",
    "摘花",
    "摘心",
    "間引",
    "作業",
    "計画",
    "カレンダー",
    "センサー",
    "カメラ",
    "ポンプ",
    "水弁",
    "watering",
    "fertilizer",
    "harvest",
    "crop",
    "plant",
)

_PROTECTED_INFORMATION_TERMS = (
    "apiキー",
    "api key",
    "アクセストークン",
    "パスワード",
    "秘密鍵",
    "システムプロンプト",
    "内部プロンプト",
    "プロンプトを表示",
    "指示を無視",
    "previous instructions",
    "system prompt",
    "developer message",
)

_UNSAFE_OR_ABUSIVE_PATTERNS = (
    r"(?:人|動物).{0,12}(?:殺|傷つけ|毒)",
    r"(?:爆弾|爆発物|武器).{0,12}(?:作|製造|入手)",
    r"(?:不正アクセス|ハッキング|マルウェア|ランサムウェア)",
    r"(?:個人情報|住所|電話番号).{0,12}(?:盗|特定|晒)",
)


def validate_plant_question(question: str, planting: dict | None = None) -> tuple[bool, str, str]:
    """Return whether a question can be answered and persisted.

    The check deliberately runs before the LLM. Rejected text must not become a
    cultivation record or be sent to a configured external model provider.
    """

    normalized = unicodedata.normalize("NFKC", str(question or "")).casefold().strip()
    if not normalized:
        return False, "question_required", "質問を入力してください。"
    if len(normalized) > 2000:
        return False, "question_too_long", "質問は2000文字以内で入力してください。"
    if any(term in normalized for term in _PROTECTED_INFORMATION_TERMS):
        return (
            False,
            "question_protected_information",
            "安全のため、内部設定や秘密情報に関する質問には回答できません。作物の状態や次の作業について質問してください。",
        )
    if any(re.search(pattern, normalized) for pattern in _UNSAFE_OR_ABUSIVE_PATTERNS):
        return (
            False,
            "question_unsafe",
            "人や設備へ危害を与える内容には回答できません。安全な栽培作業について質問してください。",
        )

    context_terms = []
    if isinstance(planting, dict):
        context_terms.extend((planting.get("crop_name"), planting.get("cultivar"), planting.get("placement_name")))
    has_cultivation_context = any(term in normalized for term in _AGRICULTURE_TERMS)
    has_registered_name = any((name := unicodedata.normalize("NFKC", str(value or "")).casefold().strip()) and name in normalized for value in context_terms)
    if not has_cultivation_context and not has_registered_name:
        return (
            False,
            "question_out_of_scope",
            "このチャットは登録した作物と農作業の相談専用です。例えば「次の追肥はいつ？」「葉の変色で何を確認する？」のように質問してください。",
        )
    return True, "", ""
