import os
import tempfile
import unittest

os.environ.setdefault("WORK_DIR", tempfile.mkdtemp())
os.environ.setdefault("TURSO_DATABASE_URL", "x")
os.environ.setdefault("TURSO_AUTH_TOKEN", "x")
os.environ.setdefault("S3_ENDPOINT_URL", "x")
os.environ.setdefault("S3_BUCKET_NAME", "x")
os.environ.setdefault("S3_BUCKET_REGION", "auto")
os.environ.setdefault("S3_ACCESS_KEY", "x")
os.environ.setdefault("S3_SECRET_KEY", "x")
os.environ.setdefault("MQTT_BROKER_URL", "localhost")
os.environ.setdefault("MQTT_BROKER_PORT", "1883")
os.environ.setdefault("MQTT_BROKER_USERNAME", "x")
os.environ.setdefault("MQTT_BROKER_PASSWORD", "x")
os.environ.setdefault("TIMELAPSE_INTERVAL", "600")

from ina_device_hub.cultivation_research_repository import CultivationResearchRepository
from ina_device_hub.cultivation_research_service import analyze_correlation, build_research_dataset


class CultivationResearchServiceTest(unittest.TestCase):
    def test_hypothesis_and_analysis_are_persisted(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "research.json")
            repository = CultivationResearchRepository(path)
            hypothesis = repository.add_hypothesis("field-1", {"title": "日照が収量に関係する"})
            repository.update_hypothesis("field-1", hypothesis["id"], {"status": "supported"})
            repository.add_analysis("field-1", {"method": "pearson", "coefficient": 0.8})

            reloaded = CultivationResearchRepository(path)

            self.assertEqual(reloaded.list_hypotheses("field-1")[0]["status"], "supported")
            self.assertEqual(reloaded.data["field-1"]["analyses"][0]["coefficient"], 0.8)

    def test_dataset_keeps_weather_and_human_provenance_separate(self):
        field = {
            "id": "field-1",
            "weather_location": {"timezone": "Asia/Tokyo"},
            "events": [
                {
                    "id": "event-1",
                    "occurred_at": "2026-07-01T08:00:00+09:00",
                    "target_placement_id": "ridge-1",
                    "record_values": [{"key": "harvest_weight_g", "value": "120"}],
                }
            ],
        }
        weather = [
            {
                "record_id": "weather-1",
                "source": {"type": "reanalysis", "provider": "open_meteo"},
                "daily_summaries": [
                    {"date": "2026-07-01", "precipitation_mm": 2.5, "data_quality": "reanalysis_grid_daily"}
                ],
            }
        ]

        dataset = build_research_dataset(field, weather)

        self.assertEqual(dataset["rows"][0]["weather"]["precipitation_mm"], 2.5)
        self.assertEqual(dataset["rows"][0]["field_records"]["harvest_weight_g"], 120.0)
        self.assertEqual(
            {item["kind"] for item in dataset["rows"][0]["provenance"]},
            {"external_analysis", "human_observation"},
        )

    def test_pearson_and_spearman_are_deterministic_and_not_causal(self):
        dataset = {
            "rows": [
                {"date": f"2026-07-0{index}", "weather": {"sunshine_hours": x}, "field_records": {"harvest_weight_g": y}}
                for index, (x, y) in enumerate([(1, 10), (2, 20), (3, 30), (4, 40)], start=1)
            ]
        }

        pearson = analyze_correlation(
            dataset, "weather.sunshine_hours", "field_records.harvest_weight_g", method="pearson"
        )
        spearman = analyze_correlation(
            dataset, "weather.sunshine_hours", "field_records.harvest_weight_g", method="spearman"
        )

        self.assertEqual(pearson["coefficient"], 1.0)
        self.assertEqual(spearman["coefficient"], 1.0)
        self.assertEqual(pearson["sample_size"], 4)
        self.assertFalse(pearson["causal_claim"])
        self.assertIn("因果関係", pearson["interpretation"])

    def test_returns_no_coefficient_for_too_few_pairs(self):
        dataset = {
            "rows": [
                {"date": "2026-07-01", "weather": {"rain_mm": 1}, "field_records": {"harvest_weight_g": 10}},
                {"date": "2026-07-02", "weather": {"rain_mm": 2}, "field_records": {"harvest_weight_g": 20}},
            ]
        }
        result = analyze_correlation(dataset, "weather.rain_mm", "field_records.harvest_weight_g")
        self.assertIsNone(result["coefficient"])
        self.assertEqual(result["sample_size"], 2)


if __name__ == "__main__":
    unittest.main()
