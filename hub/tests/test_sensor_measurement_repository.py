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
    metric_supported_for_device_kind,
)


class SensorMeasurementRepositoryTest(unittest.TestCase):
    def test_repository_initializes_definitions_in_one_batch(self):
        class DefinitionConnector:
            def __init__(self):
                self.definition_batches = []

            def upsert_sensor_measurement_definitions(self, definitions):
                self.definition_batches.append(list(definitions))

        connector = DefinitionConnector()

        SensorMeasurementRepository(connector)

        self.assertEqual(len(connector.definition_batches), 1)
        self.assertGreater(len(connector.definition_batches[0]), 1)

    def test_extract_env_measurements_from_status_payload(self):
        measurements = extract_measurements_from_status(
            "INADS-env",
            {
                "seq": 10,
                "device_kind": "ENV",
                "air_temperature_c": 24.5,
                "air_humidity_percent": 68.0,
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
        self.assertEqual(by_metric["air_temperature_c"]["value"], 24.5)
        self.assertEqual(by_metric["air_humidity_percent"]["unit"], "%")
        self.assertEqual(by_metric["par_umol_m2_s"]["value"], 1234.0)
        self.assertEqual(by_metric["par_umol_m2_s"]["unit"], "umol/m2/s")
        self.assertEqual(by_metric["soil_ph"]["raw_value"], 65.0)
        self.assertFalse(by_metric["soil_ec_us_cm"]["payload"]["calibrated"])

    def test_extract_wtr_rs485_measurements_from_status_payload(self):
        measurements = extract_measurements_from_status(
            "INADS-wtr",
            {
                "seq": 12,
                "device_kind": "WTR",
                "sensor_12v_power_requested": True,
                "sensor_12v_power_configured": True,
                "par_ok": True,
                "par_umol_m2_s": 700.0,
                "raw_par": 700,
                "soil_rs485_ok": True,
                "soil_temperature_c": 20.1,
                "soil_ec_us_cm": 640.0,
                "soil_ph": 6.4,
                "raw_soil_temperature": 201,
                "raw_soil_ec": 640,
                "raw_soil_ph": 64,
                "env_par_calibrated": False,
                "env_soil_calibrated": True,
            },
            "2026-07-12T05:00:00+00:00",
        )

        by_metric = {item["metric"]: item for item in measurements}
        self.assertEqual(by_metric["soil_ec_us_cm"]["device_kind"], "WTR")
        self.assertEqual(by_metric["soil_temperature_c"]["raw_value"], 201.0)
        self.assertTrue(by_metric["soil_ph"]["payload"]["calibrated"])

    def test_extract_wrs_rs485_measurements_from_status_payload(self):
        measurements = extract_measurements_from_status(
            "INADS-wrs",
            {
                "seq": 13,
                "device_kind": "WRS",
                "par_ok": True,
                "par_umol_m2_s": 810.0,
                "raw_par": 810,
                "soil_rs485_ok": True,
                "soil_moisture_percent": 44.2,
                "soil_temperature_c": 19.8,
                "soil_ec_us_cm": 710.0,
                "raw_soil_moisture": 442,
                "raw_soil_temperature": 198,
                "raw_soil_ec": 710,
            },
            "2026-07-12T05:00:00+00:00",
        )

        by_metric = {item["metric"]: item for item in measurements}
        self.assertEqual(by_metric["soil_moisture_percent"]["device_kind"], "WRS")
        self.assertEqual(by_metric["soil_ec_us_cm"]["value"], 710.0)
        self.assertEqual(by_metric["par_umol_m2_s"]["raw_value"], 810.0)

    def test_extract_soi_analog_soil_moisture_from_status_payload(self):
        measurements = extract_measurements_from_status(
            "INADS-soi",
            {
                "seq": 14,
                "device_kind": "SOI",
                "soil_moisture_ok": True,
                "soil_moisture_percent": 33,
                "raw_soil_moisture": 2810,
                "soil_calibration_calibrated": True,
            },
            "2026-07-12T05:00:00+00:00",
        )

        self.assertEqual(len(measurements), 1)
        self.assertEqual(measurements[0]["metric"], "soil_moisture_percent")
        self.assertEqual(measurements[0]["device_kind"], "SOI")
        self.assertEqual(measurements[0]["raw_value"], 2810.0)
        self.assertTrue(measurements[0]["payload"]["calibrated"])

    def test_extract_fgt_ignores_unsupported_ph_and_npk_values(self):
        measurements = extract_measurements_from_status(
            "INADS-fgt",
            {
                "seq": 15,
                "device_kind": "FGT",
                "soil_rs485_ok": True,
                "soil_moisture_percent": 26.7,
                "soil_temperature_c": 25.0,
                "soil_ec_us_cm": 81.0,
                "soil_ph": 4.4,
                "soil_n_mg_kg": 40.0,
                "soil_p_mg_kg": 0.0,
                "soil_k_mg_kg": 0.0,
            },
            "2026-08-06T06:52:21+09:00",
        )

        self.assertEqual(
            {item["metric"] for item in measurements},
            {"soil_moisture_percent", "soil_temperature_c", "soil_ec_us_cm"},
        )
        self.assertFalse(metric_supported_for_device_kind("soil_ph", "FGT"))
        self.assertTrue(metric_supported_for_device_kind("soil_ph", "ENV"))
        self.assertTrue(metric_supported_for_device_kind("soil_ph", "NEW"))

    def test_repository_creates_definitions_and_writes_measurements(self):
        connector = InaDBConnector()
        repository = SensorMeasurementRepository(connector)

        definitions = repository.list_definitions()
        by_metric = {item["metric"]: item for item in definitions}
        self.assertIn("soil_ec_us_cm", by_metric)
        self.assertIn("SOI", by_metric["soil_moisture_percent"]["device_kinds"])
        self.assertIn("WTR", by_metric["soil_ec_us_cm"]["device_kinds"])
        self.assertIn("WRS", by_metric["soil_ec_us_cm"]["device_kinds"])
        self.assertIn("FGT", by_metric["soil_ec_us_cm"]["device_kinds"])
        self.assertNotIn("FGT", by_metric["soil_ph"]["device_kinds"])
        self.assertIn("WTR", by_metric["par_umol_m2_s"]["device_kinds"])
        self.assertIn("WRS", by_metric["par_umol_m2_s"]["device_kinds"])
        self.assertIn("FGT", by_metric["par_umol_m2_s"]["device_kinds"])

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

        in_range = repository.between_for_devices(
            ["INADS-env-measurement-test"],
            "2026-07-12T00:00:00+00:00",
            "2026-07-13T00:00:00+00:00",
        )
        soil_only = repository.between_for_devices(
            ["INADS-env-measurement-test"],
            "2026-07-12T00:00:00+00:00",
            "2026-07-13T00:00:00+00:00",
            metric="soil_moisture_percent",
        )
        out_of_range = repository.between_for_devices(
            ["INADS-env-measurement-test"],
            "2026-07-13T00:00:00+00:00",
            "2026-07-14T00:00:00+00:00",
        )
        self.assertEqual(len(in_range), 1)
        self.assertEqual(soil_only, [])
        self.assertEqual(out_of_range, [])


if __name__ == "__main__":
    unittest.main()
