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
os.environ.setdefault("MQTT_BROKER_USERNAME", "")
os.environ.setdefault("MQTT_BROKER_PASSWORD", "")
os.environ.setdefault("TIMELAPSE_INTERVAL", "600")

from ina_device_hub.fertilizer_effect import fertilizer_effect_summary


class FertilizerEffectTest(unittest.TestCase):
    def test_calculates_nutrient_kg_and_multi_year_remaining_effect(self):
        summary = fertilizer_effect_summary(
            [
                {
                    "id": "application-1",
                    "material_name": "牛ふん堆肥",
                    "applied_on": "2026-01-01",
                    "amount_kg": 1000,
                    "nutrient_percent": {"n": 2, "p2o5": 1, "k2o": 1.5, "mgo": 0.5},
                    "annual_available_percent": 10,
                    "effect_years": 3,
                    "start_delay_days": 0,
                }
            ],
            as_of="2027-01-01",
        )

        self.assertEqual(summary["nutrients"]["n"]["applied_kg"], 20)
        self.assertEqual(summary["nutrients"]["n"]["effective_total_kg"], 6)
        self.assertEqual(summary["nutrients"]["n"]["released_to_date_kg"], 2)
        self.assertEqual(summary["nutrients"]["n"]["remaining_kg"], 4)
        self.assertEqual(summary["nutrients"]["mgo"]["applied_kg"], 5)
        self.assertEqual(summary["nutrients"]["mgo"]["remaining_kg"], 1)
        self.assertEqual(summary["applications"][0]["state"], "active")

    def test_start_delay_keeps_effect_waiting(self):
        summary = fertilizer_effect_summary(
            [
                {
                    "material_name": "有機質肥料",
                    "applied_on": "2026-07-01",
                    "amount_kg": 10,
                    "nutrient_percent": {"n": 5, "p2o5": 0, "k2o": 0},
                    "annual_available_percent": 50,
                    "effect_years": 1,
                    "start_delay_days": 30,
                }
            ],
            as_of="2026-07-15",
        )

        self.assertEqual(summary["applications"][0]["state"], "waiting")
        self.assertEqual(summary["nutrients"]["n"]["released_to_date_kg"], 0)
        self.assertEqual(summary["nutrients"]["n"]["remaining_kg"], 0.25)
        self.assertGreater(summary["forecast"][0]["nutrients_kg"]["n"], 0)


if __name__ == "__main__":
    unittest.main()
