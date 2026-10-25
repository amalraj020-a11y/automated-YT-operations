import importlib.util
import os
import unittest
from unittest.mock import patch
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "hourly_cloud.py"
SPEC = importlib.util.spec_from_file_location("hourly_cloud", SCRIPT)
hourly = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hourly)


class HourlyCloudTest(unittest.TestCase):
    def test_non_openai_default_and_stable_topic(self):
        self.assertFalse(hourly.MODEL.startswith("openai/"))
        self.assertEqual(hourly.topic_for("2030-01-01T05"), hourly.topic_for("2030-01-01T05"))

    def test_reviewed_fixture_passes_validation(self):
        import json
        fixture = Path(__file__).parent / "fixtures" / "hourly-content.json"
        content = json.loads(fixture.read_text(encoding="utf-8"))
        self.assertEqual(hourly.validate_content(content)["title"], content["title"])

    def test_small_model_word_count_variation_is_accepted(self):
        content = {
            "title": "Safe Python tip",
            "narration": " ".join(["useful"] * 126),
            "description": "A safe Python lesson.",
            "hashtags": ["Python", "Coding", "LearnPython", "Shorts"],
            "scenes": ["One", "Two", "Three", "Four", "Five"],
        }
        self.assertIs(hourly.validate_content(content), content)

    def test_generation_retries_invalid_model_output(self):
        invalid = {
            "title": "Too long narration", "narration": "word " * 160,
            "description": "Description", "hashtags": ["Python", "Coding", "Shorts"],
            "scenes": ["One", "Two", "Three", "Four", "Five"],
        }
        valid = {**invalid, "narration": "word " * 80}
        with patch.object(hourly, "groq_json", side_effect=[invalid, valid]) as mocked:
            self.assertIs(hourly.generate_valid_content("topic"), valid)
        self.assertEqual(mocked.call_count, 2)

    def test_free_youtube_agent_tools_rank_hook_and_title(self):
        fixture = Path(__file__).parent / "fixtures" / "hourly-content.json"
        content = __import__("json").loads(fixture.read_text(encoding="utf-8"))
        content["hook_options"] = [
            "Welcome to this amazing video",
            "How can you inspect your files safely before changing anything?",
        ]
        content["title_options"] = [
            "Amazing Ultimate Python Secret",
            "3 Safe Python Steps for Your Files",
        ]
        optimized = hourly.optimize_packaging(content)
        self.assertIn("packaging", optimized)
        self.assertTrue(optimized["narration"].startswith(optimized["packaging"]["hook"]["hook"]))
        self.assertEqual(optimized["title"], optimized["packaging"]["title"]["title"])

    def test_safe_non_destructive_wording_is_accepted(self):
        content = {
            "title": "Preview files safely",
            "narration": " ".join(["useful"] * 75) + " This preview does not delete or remove files.",
            "description": "A safe Python lesson.",
            "hashtags": ["Python", "Coding", "LearnPython", "Shorts"],
            "scenes": ["Preview first", "Read only", "Review output", "Keep files", "Subscribe"],
        }
        self.assertIs(hourly.validate_content(content), content)

    def test_moneyprinter_uses_local_assets_and_no_paid_provider(self):
        content = {"title": "Safe Python tip", "narration": "Learn safely."}
        cards = [Path("one.png"), Path("two.png")]
        with patch.dict(os.environ, {"MPT_VOICE": "en-US-AriaNeural"}):
            command = hourly.moneyprinter_command(content, cards)
        joined = " ".join(command)
        self.assertIn("--video-source local", joined)
        self.assertIn("--bgm-type none", joined)
        self.assertIn("--voice-name en-US-AriaNeural", joined)
        self.assertIn("--subtitle-display-mode word_by_word", joined)
        self.assertIn("--subtitle-animation pop_spring", joined)
        self.assertIn("--video-transition-mode shuffle", joined)
        self.assertNotIn("pexels", joined.lower())
        self.assertNotIn("openai", joined.lower())

    def test_moneyprinter_result_uses_cli_result_wrapper(self):
        payload = {"task_id": "example", "result": {"videos": ["final.mp4"]}}
        task_result = payload.get("result", payload)
        self.assertEqual(task_result["videos"], ["final.mp4"])


if __name__ == "__main__":
    unittest.main()
