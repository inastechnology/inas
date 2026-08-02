# Makefile for wrapping PlatformIO commands

PIO ?= platformio
PYTHON ?= python3
ENV = seeed_xiao_esp32s3
BUILD_DIR := .pio/build/$(ENV)
REPO_ROOT := $(abspath ../..)
FIRMWARE_CHECKER ?= $(REPO_ROOT)/hub/scripts/check_firmware_manifest.py
PIO_PYTHON ?= $(HOME)/.platformio/penv/bin/python
ESPTOOL ?= $(HOME)/.platformio/packages/tool-esptoolpy/esptool.py
BOOT_APP0 ?= $(HOME)/.platformio/packages/framework-arduinoespressif32/tools/partitions/boot_app0.bin
MERGED_BIN ?= $(BUILD_DIR)/flash_merged.bin
FILESYSTEM_BIN ?= $(BUILD_DIR)/littlefs.bin
FLASH_MODE ?= keep
FLASH_FREQ ?= keep
FLASH_SIZE ?= keep
AUTO_UPLOAD_PORT := $(shell ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null | head -n 1)
UPLOAD_PORT ?= $(AUTO_UPLOAD_PORT)
RELEASE_MODULE_ID := environment-sensor-device
RELEASE_MODULE_DEVICE_KIND := ENV
RELEASE_MODULE_DISPLAY_NAME := ENV Environment Sensor
RELEASE_MODULE_VERSION := 0.1.0

include ../common/make/esp32s3-release-module.mk

.PHONY: build check-firmware buildfs merged-bin flash-merged upload ports remote-upload remote-monitor help

all: build

build:
	$(PIO) run --environment $(ENV)

check-firmware: build
	$(PYTHON) "$(FIRMWARE_CHECKER)" "$(BUILD_DIR)/firmware.bin"

buildfs:
	$(PIO) run --environment $(ENV) --target buildfs

merged-bin: build buildfs
	@if [ ! -f "$(BOOT_APP0)" ]; then \
		echo "boot_app0.bin not found: $(BOOT_APP0)"; \
		echo "If PlatformIO is installed in a custom location, override BOOT_APP0=/path/to/boot_app0.bin"; \
		exit 1; \
	fi
	@if [ ! -f "$(ESPTOOL)" ]; then \
		echo "esptool.py not found: $(ESPTOOL)"; \
		echo "If PlatformIO is installed in a custom location, override ESPTOOL=/path/to/esptool.py"; \
		exit 1; \
	fi
	@if [ ! -f "$(PIO_PYTHON)" ]; then \
		echo "PlatformIO Python not found: $(PIO_PYTHON)"; \
		echo "If PlatformIO uses a different virtualenv, override PIO_PYTHON=/path/to/python"; \
		exit 1; \
	fi
	$(PIO_PYTHON) $(ESPTOOL) --chip esp32s3 merge_bin \
		--output "$(MERGED_BIN)" \
		--flash_mode $(FLASH_MODE) \
		--flash_freq $(FLASH_FREQ) \
		--flash_size $(FLASH_SIZE) \
		0x0 "$(BUILD_DIR)/bootloader.bin" \
		0x8000 "$(BUILD_DIR)/partitions.bin" \
		0xe000 "$(BOOT_APP0)" \
		0x10000 "$(BUILD_DIR)/firmware.bin" \
		0x670000 "$(FILESYSTEM_BIN)"
	@echo "Merged image created: $(MERGED_BIN)"

flash-merged: merged-bin
	@if [ -z "$(UPLOAD_PORT)" ]; then \
		echo "Upload port not found."; \
		echo "Connect device, then run: make flash-merged UPLOAD_PORT=/dev/ttyACM0"; \
		echo "Detected ports:"; \
		$(PIO) device list || true; \
		exit 1; \
	fi
	@echo "Flashing merged image via $(UPLOAD_PORT)"
	$(PIO_PYTHON) $(ESPTOOL) --chip esp32s3 --port "$(UPLOAD_PORT)" --baud 460800 write_flash 0x0 "$(MERGED_BIN)"

upload:
	@if [ -z "$(UPLOAD_PORT)" ]; then \
		echo "Upload port not found."; \
		echo "Connect device, then run: make upload UPLOAD_PORT=/dev/ttyACM0"; \
		echo "Detected ports:"; \
		$(PIO) device list || true; \
		exit 1; \
	fi
	@echo "Uploading via $(UPLOAD_PORT)"
	$(PIO) run --target upload --environment $(ENV) --upload-port $(UPLOAD_PORT)

ports:
	$(PIO) device list
	@echo "Raw candidates: $(AUTO_UPLOAD_PORT)"

remote-upload:
	$(PIO) remote run --target upload --environment $(ENV)

remote-monitor:
	$(PIO) remote device monitor --environment $(ENV)

help:
	@echo "Available targets:"
	@echo "  build           - Build the project"
	@echo "  check-firmware  - Build firmware.bin and verify the embedded OTA manifest"
	@echo "  buildfs         - Build the LittleFS image from data/"
	@echo "  package         - Create the F/W release module ZIP"
	@echo "  merged-bin      - Build a single flashable image at $(MERGED_BIN)"
	@echo "  flash-merged    - Write the merged image to a connected board"
	@echo "  upload          - Upload locally (optional: UPLOAD_PORT=/dev/ttyACM0)"
	@echo "  ports           - Show detected serial ports"
	@echo "  remote-upload   - Upload remotely"
	@echo "  remote-monitor  - Serial monitor via PlatformIO Remote"
