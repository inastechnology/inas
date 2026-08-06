DEVICE_ID := fertigation-device
DEVICE_KIND := FGT
DEVICE_NAME := FGT Fertigation Device
DEVICE_VERSION := 0.2.3
PIO_ENV := seeed_xiao_esp32c6
ESP_CHIP := esp32c6
FLASH_SIZE := 4MB
HAS_FILESYSTEM := 1
HAS_NATIVE_TESTS := 1
USER_CONFIG := .env.user.ini

$(USER_CONFIG): default.env.user.ini
	cp default.env.user.ini $(USER_CONFIG)

include ../common/make/esp32-firmware.mk
