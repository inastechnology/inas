# sensor data repository

from datetime import datetime, timezone, timedelta
import json

from ina_device_hub.ina_db_connector import InaDBConnector
from ina_device_hub.general_log import logger
from ina_device_hub.setting import setting


class SensorDataRepository:
    def __init__(self, db_connector: InaDBConnector):
        self.db_connector = db_connector
        self.tmp_sensor_data_dict = {}
        self.tmp_file_path = setting().get_work_dir() + "/tmp_sensor_data.json"

        # load tmp sensor data
        self.__load_tmp_sensor_data()

    def add(self, device_id: str, seqId: int, data: dict):
        # latest data record
        self.__insert_latest_data(device_id, data)

        # aggregate data record
        if device_id not in self.tmp_sensor_data_dict:
            self.tmp_sensor_data_dict[device_id] = {}

        current_yyyymmdd_hh = datetime.now(timezone.utc).strftime("%Y%m%d%H")
        if current_yyyymmdd_hh not in self.tmp_sensor_data_dict[device_id]:
            self.tmp_sensor_data_dict[device_id][current_yyyymmdd_hh] = []

        self.tmp_sensor_data_dict[device_id][current_yyyymmdd_hh].append(data)

        # save tmp sensor data
        self.__save_tmp_sensor_data()

        # whether aggregate or not
        # older than 1hours
        for yyyymmdd_hh in list(self.tmp_sensor_data_dict[device_id].keys()):
            if datetime.strptime(yyyymmdd_hh, "%Y%m%d%H").replace(tzinfo=timezone.utc) < (datetime.now(timezone.utc) - timedelta(hours=1)):
                logger.info(f"aggregate data: device_id={device_id}, yyyymmdd_hh={yyyymmdd_hh}")
                aggregated_data = self.__aggregate_data(device_id, yyyymmdd_hh)
                if aggregated_data:
                    self.__insert_aggreated_data(device_id, yyyymmdd_hh, aggregated_data)
                    del self.tmp_sensor_data_dict[device_id][yyyymmdd_hh]
                    self.__save_tmp_sensor_data()

    def get_latest(self, device_id: str):
        data_as_tupple = self.db_connector.fetch_latest_sensor_data(device_id)
        if data_as_tupple is None:
            return None

        # sensor_id, temp, tds, ec, ph, dissolved_oxygen, ammonia, nitrate, created_at, updated_at, extra
        try:
            extra = json.loads(data_as_tupple[10] or "{}")
        except (TypeError, json.JSONDecodeError):
            extra = {}
        telemetry = extra.get("telemetry", {}) if isinstance(extra, dict) else {}
        return {
            "device_id": data_as_tupple[0],
            "temp": data_as_tupple[1],
            "tds": data_as_tupple[2],
            "ec": data_as_tupple[3],
            "ph": data_as_tupple[4],
            "dissolved_oxygen": data_as_tupple[5],
            "ammonia": data_as_tupple[6],
            "nitrate": data_as_tupple[7],
            "created_at": datetime.strptime(data_as_tupple[8], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).astimezone(),
            "updated_at": datetime.strptime(data_as_tupple[9], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).astimezone(),
            "extra": extra,
            "telemetry": telemetry,
        }

    def get_latest_aggreated(self, device_id: str):
        data = self.db_connector.fetch_latest_aggregated_sensor_data(device_id)
        if data is None:
            return None

        # sensor_id, temp, tds, ec, ph, dissolved_oxygen, ammonia, nitrate, yyyymmddhh, created_at, extra
        ret = []
        for d in data:
            try:
                extra = json.loads(d[10] or "{}")
            except (TypeError, json.JSONDecodeError):
                extra = {}
            ret.append(
                {
                    "device_id": d[0],
                    "temp": d[1],
                    "tds": d[2],
                    "ec": d[3],
                    "ph": d[4],
                    "dissolved_oxygen": d[5],
                    "ammonia": d[6],
                    "nitrate": d[7],
                    "yyyymmddhh": datetime.strptime(str(d[8]), "%Y%m%d%H").replace(tzinfo=timezone.utc).astimezone(),
                    "created_at": d[9],
                    "extra": extra,
                }
            )
        return ret

    def get_aggreated_by_range(self, device_id: str, start: str, end: str):
        return self.db_connector.fetch_aggregated_sensor_data_by_range(
            device_id,
            start,
            end,
        )

    def force_aggregate(self, device_id):
        for yyyymmdd_hh in list(self.tmp_sensor_data_dict[device_id].keys()):
            aggregated_data = self.__aggregate_data(device_id, yyyymmdd_hh)
            if aggregated_data:
                self.__insert_aggreated_data(
                    device_id,
                    yyyymmdd_hh,
                    aggregated_data,
                )
                del self.tmp_sensor_data_dict[device_id][yyyymmdd_hh]
                self.__save_tmp_sensor_data()

    def __aggregate_data(self, device_id, yyyymmdd_hh):
        if device_id not in self.tmp_sensor_data_dict:
            return None

        if yyyymmdd_hh not in self.tmp_sensor_data_dict[device_id]:
            return None

        if len(self.tmp_sensor_data_dict[device_id][yyyymmdd_hh]) == 0:
            return None

        # aggregate
        temps = []
        tdss = []

        for data in self.tmp_sensor_data_dict[device_id][yyyymmdd_hh]:
            if "temp" in data and data["temp"] != -1000:
                temps.append(data["temp"])
            if "tds" in data and data["tds"] != -1000:
                tdss.append(data["tds"])

        avg_temp = sum(temps) / len(temps) if len(temps) > 0 else -1000
        avg_tds = sum(tdss) / len(tdss) if len(tdss) > 0 else -1000

        return {
            "temp": avg_temp,
            "tds": avg_tds,
        }

    def __insert_latest_data(self, device_id: str, data: dict):
        self.db_connector.upsert_latest_sensor_data(
            device_id,
            data,
        )

    def __insert_aggreated_data(self, device_id: str, yyyymmdd_hh: str, data: dict):
        self.db_connector.insert_aggregated_sensor_data(
            device_id,
            yyyymmdd_hh,
            data,
        )

    def __save_tmp_sensor_data(self):
        with open(self.tmp_file_path, "w") as f:
            json.dump(self.tmp_sensor_data_dict, f, indent=4)

    def __load_tmp_sensor_data(self):
        try:
            with open(self.tmp_file_path, "r") as f:
                self.tmp_sensor_data_dict = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load tmp sensor data: {e}")
            # create empty dict
            self.tmp_sensor_data_dict = {}
            self.__save_tmp_sensor_data()


# singleton instance
__instance = None


def sensor_data_repository(db_connector: InaDBConnector = None):
    global __instance
    if not __instance:
        if db_connector is None:
            raise ValueError("db_connector must be set")
        __instance = SensorDataRepository(db_connector)
    return __instance
