from ina_device_hub.device_connector import DeviceConnector
from ina_device_hub.setting import setting
from ina_device_hub.switchbot_api_client import SwitchBotAPIClient


class SwitchBotPlugMiniConnector(DeviceConnector):
    POWER_ON = "ON"
    POWER_OFF = "OFF"

    def __init__(self, device_id: str | None = None, client: SwitchBotAPIClient | None = None):
        switchbot_settings = setting().get("switchbot") or {}
        self.device_id = (device_id if device_id is not None else switchbot_settings.get("plug_mini_device_id", "")).strip()
        self.client = client or SwitchBotAPIClient()
        if not self.device_id:
            raise ValueError("SwitchBot Plug Mini device ID must be configured")

    def get_status(self) -> dict:
        return self.client.get_device_status(self.device_id)

    def is_on(self) -> bool | None:
        status = self.get_status()
        power = status.get("power") or status.get("powerState")
        if isinstance(power, str):
            normalized_power = power.upper()
            if normalized_power == self.POWER_ON:
                return True
            if normalized_power == self.POWER_OFF:
                return False

        switch_status = status.get("switchStatus")
        if switch_status == 1:
            return True
        if switch_status == 0:
            return False
        return None

    def turn_on(self) -> dict:
        return self.client.send_device_command(self.device_id, "turnOn")

    def turn_off(self) -> dict:
        return self.client.send_device_command(self.device_id, "turnOff")

    def toggle(self) -> dict:
        return self.client.send_device_command(self.device_id, "toggle")


__instance = None


def switchbot_plug_mini_connector():
    global __instance  # noqa: PLW0603
    if not __instance:
        __instance = SwitchBotPlugMiniConnector()
    return __instance
