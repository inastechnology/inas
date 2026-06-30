# センサーデバイスから受信したデータを保持するクラス
# 以下の機能を提供する
# - センサーデータ保存用のデータベースを作成する
# - センサーデータ保存用のテーブルを作成する
# - センサーデータをデータベースに保存する
# - センサーデータをデータベースから取得する

import json
from datetime import UTC, datetime

import libsql

from ina_device_hub.setting import setting


def commit_and_sync(func):
    """
    関数実行後、必ず commit と sync を実行するデコレーター
    """

    def wrapper(self, *args, **kwargs):
        try:
            result = func(self, *args, **kwargs)
            return result
        except Exception as e:
            # エラーハンドリング（必要に応じてログ出力等）
            print("Error occurred:", e)
            raise
        finally:
            print("Commit and sync")
            self.conn.commit()
            _sync_if_supported(self.conn)

    return wrapper


def _is_sync_url(url: str | None):
    return bool(url and (url.startswith("libsql://") or url.startswith("http://") or url.startswith("https://")))


def _sync_if_supported(conn):
    try:
        conn.sync()
    except ValueError as exc:
        if "Sync is not supported" not in str(exc):
            raise


class InaDBConnector:
    def __init__(self):
        turso_settings = setting().get("turso")
        db_path = turso_settings.get("local_db_path")
        url = turso_settings.get("database_url")
        auth_token = turso_settings.get("auth_token")
        if _is_sync_url(url):
            self.conn = libsql.connect(db_path, sync_url=url, auth_token=auth_token)
            self.conn.sync()
        else:
            self.conn = libsql.connect(db_path)
        self.ensure_device_event_table()

    def ensure_device_event_table(self):
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS device_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                occurred_at TEXT NOT NULL,
                event_type TEXT NOT NULL,
                direction TEXT NOT NULL,
                device_id TEXT,
                topic TEXT,
                category TEXT,
                action TEXT,
                kind TEXT,
                seq_id TEXT,
                mqtt_rc INTEGER,
                retain INTEGER,
                next_sleep_sec REAL,
                next_wake_at TEXT,
                payload TEXT
            )
            """
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_device_events_occurred_at ON device_events (occurred_at)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_device_events_device_id ON device_events (device_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_device_events_event_type ON device_events (event_type)")
        self.conn.commit()
        _sync_if_supported(self.conn)

    @commit_and_sync
    def insert_device_event(self, event: dict):
        self.conn.execute(
            """
            INSERT INTO device_events (
                occurred_at, event_type, direction, device_id, topic, category, action, kind,
                seq_id, mqtt_rc, retain, next_sleep_sec, next_wake_at, payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.get("occurred_at"),
                event.get("event_type"),
                event.get("direction"),
                event.get("device_id"),
                event.get("topic"),
                event.get("category"),
                event.get("action"),
                event.get("kind"),
                str(event.get("seq_id")) if event.get("seq_id") is not None else None,
                event.get("mqtt_rc"),
                int(event["retain"]) if event.get("retain") is not None else None,
                event.get("next_sleep_sec"),
                event.get("next_wake_at"),
                json.dumps(event.get("payload"), ensure_ascii=True, separators=(",", ":")),
            ),
        )

    def fetch_device_events(
        self,
        *,
        limit: int = 100,
        device_id: str = None,
        event_type: str = None,
        direction: str = None,
        connection_events_only: bool = False,
    ):
        where = []
        params = []
        if device_id:
            where.append("device_id = ?")
            params.append(device_id)
        if event_type:
            where.append("event_type = ?")
            params.append(event_type)
        if direction:
            where.append("direction = ?")
            params.append(direction)
        if connection_events_only:
            where.append(
                "event_type IN ("
                "'mqtt_client_connected',"
                "'mqtt_client_disconnected',"
                "'mqtt_client_connection_attempt',"
                "'mqtt_broker_log',"
                "'mqtt_hub_connected',"
                "'mqtt_hub_connect_failed'"
                ")"
            )

        query = (
            "SELECT id, occurred_at, event_type, direction, device_id, topic, category, action, kind, seq_id, mqtt_rc, retain, next_sleep_sec, next_wake_at, payload "
            "FROM device_events"
        )
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        return self.conn.execute(query, tuple(params)).fetchall()

    @commit_and_sync
    def upsert_device_info(
        self,
        device_id: str,
        info: dict,
        device_type: str = None,
        firmware_version: str = None,
        installation_date: datetime = None,
        location: str = None,
        customer_id: str = None,
        device_group: str = None,
    ):
        """
        デバイス情報をデータベースに保存（更新）します。
        ※ 新たにデバイス種別、ファームウェア、設置日、設置場所、顧客ID、グループも登録可能です。
        """
        query = (
            "INSERT INTO device_info (device_id, info, customer_id, device_group, device_type, firmware_version, installation_date, location) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(device_id) DO UPDATE SET "
            "info = excluded.info, "
            "customer_id = excluded.customer_id, "
            "device_group = excluded.device_group, "
            "device_type = excluded.device_type, "
            "firmware_version = excluded.firmware_version, "
            "installation_date = excluded.installation_date, "
            "location = excluded.location, "
        )
        self.conn.execute(
            query,
            (
                device_id,
                json.dumps(info),
                customer_id,
                device_group,
                device_type,
                firmware_version,
                installation_date,
                location,
            ),
        )
        self.conn.sync()

    @commit_and_sync
    def upsert_device_status(self, device_id: str, status: str):
        """
        デバイスのステータスを登録／更新します。
        """
        self.conn.execute(
            "INSERT INTO device_status (device_id, status) VALUES (?, ?) ON CONFLICT(device_id) DO UPDATE SET status = excluded.status",
            (device_id, status),
        )

    @commit_and_sync
    def upsert_latest_sensor_data(self, device_id: str, data: dict):
        """
        最新センサーデータ（拡張版：溶存酸素、アンモニア、硝酸塩追加）を登録／更新します。
        INSERT 時は created_at が自動設定され、UPDATE 時は updated_at に CURRENT_TIMESTAMP が自動で設定されます。
        """
        self.conn.execute(
            "INSERT INTO latest_sensor_data (sensor_id, temp, tds, ec, ph, dissolved_oxygen, ammonia, nitrate, extra) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(sensor_id) DO UPDATE SET "
            "temp = excluded.temp, "
            "tds = excluded.tds, "
            "ec = excluded.ec, "
            "ph = excluded.ph, "
            "dissolved_oxygen = excluded.dissolved_oxygen, "
            "ammonia = excluded.ammonia, "
            "nitrate = excluded.nitrate, "
            "updated_at = CURRENT_TIMESTAMP, "
            "extra = excluded.extra",
            (
                device_id,
                data.get("temp", -1000.0),
                data.get("tds", -1000.0),
                data.get("ec", -1000.0),
                data.get("ph", -1000.0),
                data.get("dissolved_oxygen", -1000.0),
                data.get("ammonia", -1000.0),
                data.get("nitrate", -1000.0),
                json.dumps(data.get("extra", {})),
            ),
        )

    @commit_and_sync
    def insert_aggregated_sensor_data(self, device_id: str, yyyymmdd_hh: str, data: dict):
        """
        集計済センサーデータ（拡張版）を登録します。複合キー（sensor_id, yyyymmddhh）。
        """
        self.conn.execute(
            "INSERT INTO aggregated_sensor_data (sensor_id, temp, tds, ec, ph, dissolved_oxygen, ammonia, nitrate, yyyymmddhh, extra) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                device_id,
                round(data.get("temp", -1000.0), 2),
                round(data.get("tds", -1000.0), 2),
                round(data.get("ec", -1000.0), 2),
                round(data.get("ph", -1000.0), 2),
                round(data.get("dissolved_oxygen", -1000.0), 2),
                round(data.get("ammonia", -1000.0), 2),
                round(data.get("nitrate", -1000.0), 2),
                yyyymmdd_hh,
                json.dumps(data.get("extra", {})),
            ),
        )

    def fetch_latest_sensor_data(self, device_id: str):
        """
        最新センサーデータを取得します。
        """
        return self.conn.execute(
            "SELECT sensor_id, temp, tds, ec, ph, dissolved_oxygen, ammonia, nitrate, created_at, updated_at, extra "
            "FROM latest_sensor_data WHERE sensor_id = ?",
            (device_id,),
        ).fetchone()

    def fetch_latest_aggregated_sensor_data(self, device_id: str, limit: int = 50):
        """
        最新集計済センサーデータを取得します。
        """
        return self.conn.execute(
            "SELECT sensor_id, temp, tds, ec, ph, dissolved_oxygen, ammonia, nitrate, yyyymmddhh, created_at, extra "
            "FROM aggregated_sensor_data WHERE sensor_id = ? ORDER BY yyyymmddhh DESC LIMIT ?",
            (device_id, limit),
        ).fetchall()

    def fetch_aggregated_sensor_data_by_range(self, device_id: str, start: str, end: str):
        """
        集計済センサーデータを取得します。
        """
        return self.conn.execute(
            "SELECT sensor_id, temp, tds, ec, ph, dissolved_oxygen, ammonia, nitrate, yyyymmddhh, created_at, extra "
            "FROM aggregated_sensor_data WHERE sensor_id = ? AND yyyymmddhh BETWEEN ? AND ?",
            (device_id, start, end),
        ).fetchall()

    @commit_and_sync
    def insert_sensor_image_data(self, device_id: str, yyyymmddhhmmss: str, image_path: str):
        """
        センサー画像データを登録します。
        """
        self.conn.execute(f'INSERT INTO sensor_image_data (device_id, yyyymmddhhmmss, image_path) VALUES ("{device_id}", "{yyyymmddhhmmss}", "{image_path}")')

    def fetch_sensor_latest_image(self, device_id: str, num: int = 1):
        """
        センサー画像データを取得します。
        """
        return self.conn.execute(
            "SELECT * FROM sensor_image_data WHERE device_id = ? ORDER BY yyyymmddhhmmss DESC LIMIT ?",
            (device_id, num),
        ).fetchall()

    @commit_and_sync
    def insert_user_note(self, device_id: str, note: str):
        """
        ユーザーノートを登録します。
        """
        self.conn.execute(f'INSERT INTO user_note (device_id, note) VALUES ("{device_id}", "{note}")')

    @commit_and_sync
    def upsert_sensor_info(
        self,
        sensor_id: str,
        device_id: str,
        sensor_type: str,
        calibration_date: datetime,
        location: str,
    ):
        """
        センサー情報（センサーID、種別、校正日、設置位置）を登録／更新します。
        """
        self.conn.execute(
            "INSERT INTO sensor_info (sensor_id, device_id, sensor_type, calibration_date, location) "
            "VALUES ("
            f'"{sensor_id}", "{device_id}", "{sensor_type}", "{calibration_date.strftime("%Y-%m-%d %H:%M:%S")}", "{location}"'
            ") "
            "ON CONFLICT(sensor_id) DO UPDATE SET "
            "device_id = excluded.device_id, sensor_type = excluded.sensor_type, "
            "calibration_date = excluded.calibration_date, location = excluded.location",
        )

    @commit_and_sync
    def insert_system_alert(
        self,
        device_id: str,
        alert_type: str,
        severity: str,
        description: str,
        resolved: int = 0,
    ):
        """
        システムアラートを登録します。
        """
        self.conn.execute(
            "INSERT INTO system_alerts (device_id, alert_type, severity, description, event_timestamp, resolved) "
            "VALUES ("
            f'"{device_id}", "{alert_type}", "{severity}", "{description}", "{datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")}", {resolved}'
            ")"
        )

    @commit_and_sync
    def insert_maintenance_log(
        self,
        device_id: str,
        maintenance_date: datetime,
        performed_by: str,
        description: str,
        status: str,
    ):
        """
        メンテナンスログ（定期点検、修理履歴等）を登録します。
        """
        maintenance_date_str_as_utc = maintenance_date.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")
        self.conn.execute(
            "INSERT INTO maintenance_logs (device_id, maintenance_date, performed_by, description, status) "
            "VALUES ("
            f'"{device_id}", "{maintenance_date_str_as_utc}", "{performed_by}", "{description}", "{status}"'
            ")"
        )

    @commit_and_sync
    def upsert_plant_growth_data(
        self,
        plant_id: str,
        species: str,
        growth_stage: str,
        last_measurement_date: datetime,
        height: float,
        health_status: str,
    ):
        """
        植物成長データを登録／更新します。
        """
        self.conn.execute(
            "INSERT INTO plant_growth_data (plant_id, species, growth_stage, last_measurement_date, height, health_status) "
            "VALUES ("
            f'"{plant_id}", "{species}", "{growth_stage}", "{last_measurement_date.strftime("%Y-%m-%d %H:%M:%S")}", {height}, "{health_status}"'
            ") "
            "ON CONFLICT(plant_id) DO UPDATE SET "
            "species = excluded.species, growth_stage = excluded.growth_stage, "
            "last_measurement_date = excluded.last_measurement_date, height = excluded.height, "
            "health_status = excluded.health_status",
        )

    @commit_and_sync
    def upsert_fish_tank_info(
        self,
        tank_id: str,
        fish_species: str,
        stocking_density: float,
        water_volume: float,
        last_maintenance_date: datetime,
    ):
        """
        水槽情報（魚種、飼育密度、水量、最終メンテナンス日）を登録／更新します。
        """
        self.conn.execute(
            "INSERT INTO fish_tank_info (tank_id, fish_species, stocking_density, water_volume, last_maintenance_date) "
            "VALUES ("
            f'"{tank_id}", "{fish_species}", {stocking_density}, {water_volume}, "{last_maintenance_date.strftime("%Y-%m-%d %H:%M:%S")}"'
            ") "
            "ON CONFLICT(tank_id) DO UPDATE SET "
            "fish_species = excluded.fish_species, stocking_density = excluded.stocking_density, "
            "water_volume = excluded.water_volume, last_maintenance_date = excluded.last_maintenance_date, ",
        )
