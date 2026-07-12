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

from ina_device_hub.ina_db_connector import InaDBConnector  # noqa: E402
from ina_device_hub.sensor_measurement_repository import (  # noqa: E402
    SensorMeasurementRepository,
    extract_measurements_from_status,
)


class SensorMeasurementRepositoryTest(unittest.TestCase):
    def test_extract_env_measurements_from_status_payload(self):
        measurements = extract_measurements_from_status(
            "INADS-env",
            {
                "seq": 10,
                "device_kind": "ENV",
                "par_ok": True,
                "par_umol_m2_s": 1234.0,
                "raw_par": 1234,
                "soil_rs485_ok": True,
                "soil_moisture_percent": 42.1,
                "soil_temperature_c": 21.5,
                "soil_ec_us_cm": 820.0,
                "soil_ph": 6.5,
                "soil_n_mg_kg": 34.0,
                "soil_p_mg_kg": 18.0,
                "soil_k_mg_kg": 102.0,
                "raw_soil_moisture": 421,
                "raw_soil_temperature": 215,
                "raw_soil_ec": 820,
                "raw_soil_ph": 65,
                "raw_soil_nitrogen": 34,
                "raw_soil_phosphorus": 18,
                "raw_soil_potassium": 102,
                "env_par_calibrated": True,
                "env_soil_calibrated": False,
            },
            "2026-07-12T05:00:00+00:00",
        )

        by_metric = {item["metric"]: item for item in measurements}
        self.assertEqual(by_metric["par_umol_m2_s"]["value"], 1234.0)
        self.assertEqual(by_metric["par_umol_m2_s"]["unit"], "umol/m2/s")
        self.assertEqual(by_metric["soil_ph"]["raw_value"], 65.0)
        self.assertFalse(by_metric["soil_ec_us_cm"]["payload"]["calibrated"])

    def test_repository_creates_definitions_and_writes_measurements(self):
        connector = InaDBConnector()
        repository = SensorMeasurementRepository(connector)

        definitions = repository.list_definitions()
        self.assertIn("soil_ec_us_cm", {item["metric"] for item in definitions})

        recorded = repository.record_status_measurements(
            "INADS-env-measurement-test",
            {
                "seq": 11,
                "device_kind": "ENV",
                "par_ok": True,
                "par_umol_m2_s": 900.0,
                "raw_par": 900,
                "soil_rs485_ok": False,
            },
            "2026-07-12T05:00:00+00:00",
        )

        latest = repository.latest_for_device("INADS-env-measurement-test")
        self.assertEqual(len(recorded), 1)
        self.assertEqual(latest[0]["metric"], "par_umol_m2_s")
        self.assertEqual(latest[0]["value"], 900.0)


if __name__ == "__main__":
    unittest.main()
