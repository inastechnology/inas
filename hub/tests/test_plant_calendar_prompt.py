import unittest

from ina_device_hub.plant_calendar_prompt import (
    DEFAULT_PLANT_CALENDAR_PROMPT_TEMPLATE,
    render_plant_calendar_prompt_template,
    validate_plant_calendar_prompt_template,
)


class PlantCalendarPromptTest(unittest.TestCase):
    def test_blank_template_resolves_to_default(self):
        self.assertEqual(validate_plant_calendar_prompt_template(""), DEFAULT_PLANT_CALENDAR_PROMPT_TEMPLATE)

    def test_missing_required_placeholders_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "context_json"):
            validate_plant_calendar_prompt_template("{default_instructions}\n{guidance_json}")

    def test_renderer_does_not_treat_json_braces_as_template_syntax(self):
        rendered = render_plant_calendar_prompt_template(
            DEFAULT_PLANT_CALENDAR_PROMPT_TEMPLATE,
            default_instructions="指示",
            experience_instruction="上級者",
            context_json='{"crop":"ライチ"}',
            guidance_json='[{"title":"観察"}]',
        )

        self.assertIn('{"crop":"ライチ"}', rendered)
        self.assertIn('[{"title":"観察"}]', rendered)
