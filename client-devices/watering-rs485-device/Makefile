DEVICE_ID := watering-rs485-device
DEVICE_KIND := WRS
DEVICE_NAME := WRS RS485 Watering Device
DEVICE_VERSION := 0.1.0
PIO_ENV := seeed_xiao_esp32s3
ESP_CHIP := esp32s3
FLASH_SIZE := 8MB
HAS_FILESYSTEM := 1

include ../common/make/esp32-firmware.mk

.PHONY: remote-upload remote-monitor
remote-upload:
	$(PIO_RUN) remote run --target upload --environment $(PIO_ENV)

remote-monitor:
	$(PIO_RUN) remote device monitor --environment $(PIO_ENV)
