import os
import socket
import threading


def notify(message: str) -> bool:
    address = os.environ.get("NOTIFY_SOCKET")
    if not address:
        return False
    if address.startswith("@"):
        address = f"\0{address[1:]}"
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
        client.connect(address)
        client.sendall(message.encode("utf-8"))
    return True


class WatchdogNotifier:
    def __init__(self, stop_event: threading.Event):
        watchdog_usec = os.environ.get("WATCHDOG_USEC", "")
        self.interval_seconds = max(1.0, int(watchdog_usec) / 2_000_000) if watchdog_usec.isdigit() else None
        self.stop_event = stop_event
        self._thread = threading.Thread(target=self._run, name="systemd-watchdog", daemon=True)

    def start(self) -> None:
        if self.interval_seconds is not None:
            self._thread.start()

    def stop(self) -> None:
        if self._thread.is_alive():
            self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self.stop_event.wait(self.interval_seconds):
            notify("WATCHDOG=1")
