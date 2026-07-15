import json
import math
from functools import lru_cache

from ina_device_hub.general_log import logger
from ina_device_hub.ina_db_connector import InaDBConnector

SENSOR_MEASUREMENT_DEFINITIONS = [
    {
        "metric": "air_temperature_c",
        "display_name": "気温",
        "unit": "degC",
        "category": "environment",
        "device_kinds": ["ENV", "WRS"],
        "value_type": "float",
        "description": "圃場またはハウス内の気温。",
    },
    {
        "metric": "air_humidity_percent",
        "display_name": "湿度",
        "unit": "%",
        "category": "environment",
        "device_kinds": ["ENV", "WRS"],
        "value_type": "float",
        "description": "圃場またはハウス内の相対湿度。",
    },
    {
        "metric": "soil_moisture_percent",
        "display_name": "土壌水分",
        "unit": "%",
        "category": "soil",
        "device_kinds": ["SOI", "ENV", "WTR", "WRS"],
        "value_type": "float",
        "description": "土壌の水分量。SOI/WTR は校正後の推定値、ENV/WRS は RS485 センサーの値。",
    },
    {
        "metric": "soil_temperature_c",
        "display_name": "地温",
        "unit": "degC",
        "category": "soil",
        "device_kinds": ["ENV", "WTR", "WRS"],
        "value_type": "float",
        "description": "土壌センサーが測定した地温。",
    },
    {
        "metric": "soil_ec_us_cm",
        "display_name": "土壌EC",
        "unit": "uS/cm",
        "category": "soil",
        "device_kinds": ["ENV", "WTR", "WRS"],
        "value_type": "float",
        "description": "土壌の電気伝導度。",
    },
    {
        "metric": "soil_ph",
        "display_name": "土壌pH",
        "unit": "pH",
        "category": "soil",
        "device_kinds": ["ENV", "WTR", "WRS"],
        "value_type": "float",
        "description": "土壌酸度。",
    },
    {
        "metric": "soil_n_mg_kg",
        "display_name": "窒素",
        "unit": "mg/kg",
        "category": "soil",
        "device_kinds": ["ENV", "WTR", "WRS"],
        "value_type": "float",
        "description": "土壌中の窒素量。",
    },
    {
        "metric": "soil_p_mg_kg",
        "display_name": "リン",
        "unit": "mg/kg",
        "category": "soil",
        "device_kinds": ["ENV", "WTR", "WRS"],
        "value_type": "float",
        "description": "土壌中のリン量。",
    },
    {
        "metric": "soil_k_mg_kg",
        "display_name": "カリウム",
        "unit": "mg/kg",
        "category": "soil",
        "device_kinds": ["ENV", "WTR", "WRS"],
        "value_type": "float",
        "description": "土壌中のカリウム量。",
    },
    {
        "metric": "par_umol_m2_s",
        "display_name": "光合成に使える光",
        "unit": "umol/m2/s",
        "category": "light",
        "device_kinds": ["ENV", "WTR", "WRS"],
        "value_type": "float",
        "description": "植物の光合成に使える光量。",
    },
    {
        "metric": "solar_radiation_w_m2",
        "display_name": "日射量",
        "unit": "W/m2",
        "category": "light",
        "device_kinds": ["ENV", "WRS"],
        "value_type": "float",
        "description": "全天日射量。日射センサーを接続した ENV/WRS で使用する。",
    },
]

_DEFINITION_BY_METRIC = {definition["metric"]: definition for definition in SENSOR_MEASUREMENT_DEFINITIONS}

_STATUS_METRICS = {
    "air_temperature_c": {"ok_keys": (), "raw_key": "raw_air_temperature"},
    "air_humidity_percent": {"ok_keys": (), "raw_key": "raw_air_humidity"},
    "par_umol_m2_s": {"ok_key": "par_ok", "raw_key": "raw_par"},
    "solar_radiation_w_m2": {"ok_key": "solar_radiation_ok", "raw_key": "raw_solar_radiation"},
    "soil_moisture_percent": {"ok_keys": ("soil_moisture_ok", "soil_rs485_ok"), "raw_key": "raw_soil_moisture"},
    "soil_temperature_c": {"ok_key": "soil_rs485_ok", "raw_key": "raw_soil_temperature"},
    "soil_ec_us_cm": {"ok_key": "soil_rs485_ok", "raw_key": "raw_soil_ec"},
    "soil_ph": {"ok_key": "soil_rs485_ok", "raw_key": "raw_soil_ph"},
    "soil_n_mg_kg": {"ok_key": "soil_rs485_ok", "raw_key": "raw_soil_nitrogen"},
    "soil_p_mg_kg": {"ok_key": "soil_rs485_ok", "raw_key": "raw_soil_phosphorus"},
    "soil_k_mg_kg": {"ok_key": "soil_rs485_ok", "raw_key": "raw_soil_potassium"},
}


class SensorMeasurementRepository:
    def __init__(self, db_connector: InaDBConnector):
        self.db_connector = db_connector
        self.ensure_definitions()

    def ensure_definitions(self):
        self.db_connector.upsert_sensor_measurement_definitions(SENSOR_MEASUREMENT_DEFINITIONS)

    def record_status_measurements(self, device_id: str, status: dict, measured_at: str):
        measurements = extract_measurements_from_status(device_id, status, measured_at)
        if not measurements:
            return []
        self.db_connector.insert_sensor_measurements(measurements)
        return measurements

    def list_definitions(self):
        rows = self.db_connector.fetch_sensor_measurement_definitions()
        return [_definition_row_to_dict(row) for row in rows]

    def latest_for_device(self, device_id: str, limit: int = 100):
        rows = self.db_connector.fetch_latest_sensor_measurements(device_id, limit=limit)
        return [_measurement_row_to_dict(row) for row in rows]

    def between_for_devices(self, device_ids: list[str], start_at: str, end_at: str, limit: int = 5000):
        rows = self.db_connector.fetch_sensor_measurements_for_devices(device_ids, start_at, end_at, limit=limit)
        return [_measurement_row_to_dict(row) for row in rows]


def extract_measurements_from_status(device_id: str, status: dict, measured_at: str):
    if not isinstance(status, dict):
        return []

    device_kind = status.get("device_kind")
    result = []
    for metric, options in _STATUS_METRICS.items():
        ok_keys = options.get("ok_keys")
        if ok_keys is None:
            ok_keys = (options["ok_key"],)
        present_ok_keys = [key for key in ok_keys if key in status]
        if present_ok_keys and not any(status.get(key) is True for key in present_ok_keys):
            continue
        value = _safe_number(status.get(metric))
        if value is None:
            continue
        definition = _DEFINITION_BY_METRIC[metric]
        result.append(
            {
                "device_id": device_id,
                "device_kind": device_kind,
                "measured_at": measured_at,
                "metric": metric,
                "value": value,
                "unit": definition.get("unit"),
                "quality": "ok",
                "raw_value": _safe_number(status.get(options["raw_key"])),
                "source": "mqtt_status",
                "payload": {
                    "seq": status.get("seq"),
                    "calibrated": _metric_calibrated(status, metric),
                },
            }
        )
    return result


def _metric_calibrated(status: dict, metric: str):
    if metric == "par_umol_m2_s":
        return status.get("env_par_calibrated")
    if metric == "soil_moisture_percent" and "soil_calibration_calibrated" in status:
        return status.get("soil_calibration_calibrated")
    if metric.startswith("soil_"):
        return status.get("env_soil_calibrated")
    return None


def _safe_number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float) and math.isfinite(value):
        return float(value)
    return None


def _definition_row_to_dict(row):
    try:
        device_kinds = json.loads(row[4] or "[]")
    except json.JSONDecodeError:
        device_kinds = []
    return {
        "metric": row[0],
        "display_name": row[1],
        "unit": row[2],
        "category": row[3],
        "device_kinds": device_kinds,
        "value_type": row[5],
        "description": row[6],
    }


def _measurement_row_to_dict(row):
    try:
        payload = json.loads(row[9] or "{}")
    except json.JSONDecodeError:
        payload = {}
    return {
        "device_id": row[0],
        "device_kind": row[1],
        "measured_at": row[2],
        "metric": row[3],
        "value": row[4],
        "unit": row[5],
        "quality": row[6],
        "raw_value": row[7],
        "source": row[8],
        "payload": payload,
    }


@lru_cache(maxsize=1)
def sensor_measurement_repository(db_connector: InaDBConnector | None = None):
    if db_connector is None:
        db_connector = InaDBConnector()
    return SensorMeasurementRepository(db_connector)


def safe_record_status_measurements(device_id: str, status: dict, measured_at: str):
    try:
        return sensor_measurement_repository().record_status_measurements(device_id, status, measured_at)
    except Exception:
        logger.exception("Failed to record sensor measurements for device_id=%s", device_id)
        return []
