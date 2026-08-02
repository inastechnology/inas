PIO ?= platformio
PYTHON ?= python3
ENV = seeed_xiao_esp32c6
PLATFORMIO_CORE_DIR ?= $(CURDIR)/.pio-core
BUILD_DIR := .pio/build/$(ENV)
REPO_ROOT := $(abspath ../..)
FIRMWARE_CHECKER ?= $(REPO_ROOT)/hub/scripts/check_firmware_manifest.py
USER_CONFIG := .env.user.ini
BOOT_APP0 ?= $(PLATFORMIO_CORE_DIR)/packages/framework-arduinoespressif32/tools/partitions/boot_app0.bin
AUTO_UPLOAD_PORT := $(shell ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null | head -n 1)
UPLOAD_PORT ?= $(AUTO_UPLOAD_PORT)
RELEASE_MODULE_ID := fertigation-device
RELEASE_MODULE_DEVICE_KIND := FGT
RELEASE_MODULE_DISPLAY_NAME := FGT Fertigation Device
RELEASE_MODULE_VERSION := 0.1.0

include ../common/make/esp32s3-release-module.mk

.PHONY: build test check-firmware buildfs upload monitor ports clean help

all: test build

$(USER_CONFIG): default.env.user.ini
	cp default.env.user.ini $(USER_CONFIG)

build: $(USER_CONFIG)
	PLATFORMIO_CORE_DIR="$(PLATFORMIO_CORE_DIR)" $(PIO) run --environment $(ENV)

test: $(USER_CONFIG)
	PLATFORMIO_CORE_DIR="$(PLATFORMIO_CORE_DIR)" $(PIO) test --environment native

check-firmware: build
	$(PYTHON) "$(FIRMWARE_CHECKER)" "$(BUILD_DIR)/firmware.bin"

buildfs: $(USER_CONFIG)
	PLATFORMIO_CORE_DIR="$(PLATFORMIO_CORE_DIR)" $(PIO) run --environment $(ENV) --target buildfs

upload: $(USER_CONFIG)
	@if [ -z "$(UPLOAD_PORT)" ]; then \
		echo "Upload port not found. Connect the FGT device, then run:"; \
		echo "  make upload UPLOAD_PORT=/dev/ttyACM0"; \
		exit 1; \
	fi
	PLATFORMIO_CORE_DIR="$(PLATFORMIO_CORE_DIR)" $(PIO) run --environment $(ENV) --target upload --upload-port "$(UPLOAD_PORT)"

monitor:
	@if [ -z "$(UPLOAD_PORT)" ]; then \
		echo "Monitor port not found. Set UPLOAD_PORT=/dev/ttyACM0"; \
		exit 1; \
	fi
	PLATFORMIO_CORE_DIR="$(PLATFORMIO_CORE_DIR)" $(PIO) device monitor --port "$(UPLOAD_PORT)" --baud 115200

ports:
	PLATFORMIO_CORE_DIR="$(PLATFORMIO_CORE_DIR)" $(PIO) device list

clean: $(USER_CONFIG)
	PLATFORMIO_CORE_DIR="$(PLATFORMIO_CORE_DIR)" $(PIO) run --environment $(ENV) --target clean

help:
	@echo "Available targets:"
	@echo "  test            - Run host-side FGT state-machine regression tests"
	@echo "  build           - Build firmware for XIAO ESP32-C6"
	@echo "  check-firmware  - Verify the embedded OTA manifest"
	@echo "  buildfs         - Build the LittleFS image"
	@echo "  package         - Create the F/W release module ZIP"
	@echo "  upload          - Upload locally (optional: UPLOAD_PORT=/dev/ttyACM0)"
	@echo "  monitor         - Open the 115200 baud serial monitor"
	@echo "  ports           - Show detected serial ports"
	@echo "  clean           - Clean the firmware build"
