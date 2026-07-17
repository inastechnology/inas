DEFAULT_PLANT_CALENDAR_PROMPT_TEMPLATE = """{default_instructions}

対象利用者向けの説明方針:
{experience_instruction}

登録条件(JSON):
{context_json}

採用済みユーザー編集例(JSON):
{guidance_json}"""

PLANT_CALENDAR_PROMPT_REQUIRED_PLACEHOLDERS = (
    "{default_instructions}",
    "{context_json}",
    "{guidance_json}",
)
PLANT_CALENDAR_PROMPT_MAX_LENGTH = 12000


def validate_plant_calendar_prompt_template(value: str):
    template = str(value or "").strip()
    if not template:
        return DEFAULT_PLANT_CALENDAR_PROMPT_TEMPLATE
    if len(template) > PLANT_CALENDAR_PROMPT_MAX_LENGTH:
        raise ValueError(f"AI栽培計画プロンプトは{PLANT_CALENDAR_PROMPT_MAX_LENGTH}文字以内にしてください")
    missing = [token for token in PLANT_CALENDAR_PROMPT_REQUIRED_PLACEHOLDERS if token not in template]
    if missing:
        raise ValueError("AI栽培計画プロンプトに必須項目がありません: " + ", ".join(missing))
    return template


def render_plant_calendar_prompt_template(
    template: str,
    *,
    default_instructions: str,
    experience_instruction: str,
    context_json: str,
    guidance_json: str,
):
    rendered = validate_plant_calendar_prompt_template(template)
    replacements = {
        "{default_instructions}": default_instructions,
        "{experience_instruction}": experience_instruction,
        "{context_json}": context_json,
        "{guidance_json}": guidance_json,
    }
    for token, replacement in replacements.items():
        rendered = rendered.replace(token, replacement)
    return rendered
