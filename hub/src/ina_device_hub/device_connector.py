from abc import ABC, abstractmethod


class DeviceConnector(ABC):
    @abstractmethod
    def get_status(self) -> dict:
        pass

    @abstractmethod
    def is_on(self) -> bool | None:
        pass

    @abstractmethod
    def turn_on(self) -> dict:
        pass

    @abstractmethod
    def turn_off(self) -> dict:
        pass

    @abstractmethod
    def toggle(self) -> dict:
        pass
