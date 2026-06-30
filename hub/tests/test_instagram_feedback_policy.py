import unittest

from ina_device_hub.instagram_feedback_policy import (
    collect_comment_feedback,
    is_security_related,
    is_weekly_recap_day,
    sanitize_comment_text,
)


class InstagramFeedbackPolicyTest(unittest.TestCase):
    def test_sanitize_comment_text_removes_control_chars_and_limits_length(self):
        dirty = "abc\x00\x01" + ("x" * 300)
        cleaned = sanitize_comment_text(dirty)
        self.assertNotIn("\x00", cleaned)
        self.assertLessEqual(len(cleaned), 223)

    def test_is_security_related_matches_keywords_but_not_generic_word(self):
        self.assertTrue(is_security_related("API key を公開しないでください"))
        self.assertTrue(is_security_related("token の期限を確認しましょう"))
        self.assertFalse(is_security_related("今日の葉の動きが気になる"))
        self.assertFalse(is_security_related("keyaki の木が元気"))

    def test_collect_comment_feedback_respects_admin_and_filters_security(self):
        comments = [
            {"username": "inas_technologies.ja", "text": "明日は朝昼夜の比較を強めてください"},
            {"username": "guest_1", "text": "雨の日の葉の変化が面白いです"},
            {"username": "guest_2", "text": "token 設定を見直すべき"},
        ]
        feedback = collect_comment_feedback(comments, "inas_technologies.ja")
        self.assertEqual(
            feedback["admin_instructions"],
            ["明日は朝昼夜の比較を強めてください"],
        )
        self.assertEqual(
            feedback["general_topics"],
            ["雨の日の葉の変化が面白いです"],
        )
        self.assertEqual(feedback["total_comments"], 3)

    def test_is_weekly_recap_day_on_sunday_only(self):
        self.assertFalse(is_weekly_recap_day(0))
        self.assertFalse(is_weekly_recap_day(5))
        self.assertTrue(is_weekly_recap_day(6))


if __name__ == "__main__":
    unittest.main()
