import logging
import os
import signal
import threading

from ina_edge_runtime.store import EdgeStore

from ina_edge_gateway.commands import GatewayCommandExecutor
from ina_edge_gateway.config import GatewayConfig
from ina_edge_gateway.controller import DeviceMessageController
from ina_edge_gateway.health import GatewayHealth, MaintenanceHTTPServer
from ina_edge_gateway.identity import load_edge_identity
from ina_edge_gateway.mqtt_client import GatewayMQTTClient
from ina_edge_gateway.runtime_status import RuntimeStatus
from ina_edge_gateway.sync_client import GatewaySyncClient, ParentSyncTransport
from ina_edge_gateway.systemd_notify import WatchdogNotifier, notify

LOGGER = logging.getLogger(__name__)


class GatewayService:
    def __init__(self, config: GatewayConfig):
        self.config = config
        self.config.data_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.node_id = load_edge_identity(config.identity_file)
        self.store = EdgeStore(config.store_path)
        os.chmod(config.store_path, 0o600)
        self.stop_event = threading.Event()
        self._stop_lock = threading.Lock()
        self._stopped = False
        self.status = RuntimeStatus(node_id=self.node_id, parent_configured=config.parent is not None)
        self.mqtt_client = GatewayMQTTClient(config=config.mqtt, node_id=self.node_id, status=self.status)
        self.controller = DeviceMessageController(store=self.store, node_id=self.node_id, publisher=self.mqtt_client)
        self.mqtt_client.set_message_handler(self.controller.handle_message)
        self.command_executor = GatewayCommandExecutor(store=self.store, node_id=self.node_id, publisher=self.mqtt_client)
        self.health = GatewayHealth(config=config, store=self.store, status=self.status, mqtt_client=self.mqtt_client)
        self.maintenance_server = MaintenanceHTTPServer(host=config.health.bind_host, port=config.health.port, health=self.health)
        self.sync_client = self._sync_client()
        self.sync_thread = (
            threading.Thread(target=self.sync_client.run, args=(self.stop_event,), name="edge-parent-sync", daemon=True)
            if self.sync_client is not None
            else None
        )
        self.command_thread = threading.Thread(target=self._run_commands, name="edge-command-worker", daemon=True)
        self.watchdog = WatchdogNotifier(self.stop_event)

    def run(self) -> None:
        self.command_executor.recover_interrupted_commands()
        self.maintenance_server.start()
        self.mqtt_client.start()
        self.command_thread.start()
        if self.sync_thread is not None:
            self.sync_thread.start()
        self.watchdog.start()
        notify(f"READY=1\nSTATUS=Edge Gateway running as {self.node_id}")
        LOGGER.info("Edge Gateway started node_id=%s", self.node_id)
        try:
            self.stop_event.wait()
        finally:
            self.stop()

    def stop(self) -> None:
        with self._stop_lock:
            if self._stopped:
                return
            self._stopped = True
            notify("STOPPING=1")
            self.stop_event.set()
            if self.sync_thread is not None:
                self.sync_thread.join(timeout=30)
            self.command_thread.join(timeout=5)
            self.watchdog.stop()
            self.mqtt_client.stop()
            self.maintenance_server.stop()
            self.store.close()
            LOGGER.info("Edge Gateway stopped node_id=%s", self.node_id)

    def _sync_client(self) -> GatewaySyncClient | None:
        if self.config.parent is None:
            return None
        return GatewaySyncClient(
            store=self.store,
            node_id=self.node_id,
            transport=ParentSyncTransport(self.config.parent),
            health_provider=self.health.sync_document,
            command_executor=self.command_executor,
            status=self.status,
        )

    def _run_commands(self) -> None:
        while not self.stop_event.is_set():
            try:
                self.command_executor.process()
            except Exception:
                LOGGER.exception("Local command worker failed")
            self.stop_event.wait(1)


def install_signal_handlers(service: GatewayService) -> None:
    def request_stop(_signum, _frame):
        service.stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
