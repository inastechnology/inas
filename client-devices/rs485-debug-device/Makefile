# Makefile for the standalone ESP32-S3 RS485 diagnostic firmware.

PIO ?= platformio
PYTHON ?= python3
ENV ?= seeed_xiao_esp32s3
BUILD_DIR := .pio/build/$(ENV)
REPO_ROOT := $(abspath ../..)
PIO_HOME_DIR ?= $(HOME)/.platformio
PIO_PYTHON ?= $(PIO_HOME_DIR)/penv/bin/python
ESPTOOL ?= $(PIO_HOME_DIR)/packages/tool-esptoolpy/esptool.py
BOOT_APP0 ?= $(PIO_HOME_DIR)/packages/framework-arduinoespressif32/tools/partitions/boot_app0.bin
APP_BIN ?= $(BUILD_DIR)/firmware.bin
MERGED_BIN ?= $(BUILD_DIR)/rs485-debug-device-esp32s3.bin
RELEASE_ZIP ?= release/rs485-debug-device-esp32s3.zip
FLASH_MODE ?= keep
FLASH_FREQ ?= keep
FLASH_SIZE ?= keep
AUTO_UPLOAD_PORT := $(shell ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null | head -n 1)
UPLOAD_PORT ?= $(AUTO_UPLOAD_PORT)
RELEASE_MODULE_ID := rs485-debug-device
RELEASE_MODULE_DEVICE_KIND := RS485-DEBUG
RELEASE_MODULE_DISPLAY_NAME := RS485 Debug Device
RELEASE_MODULE_VERSION := 0.1.0
RELEASE_MODULE_PACKAGE_DEPS := build
RELEASE_MODULE_FILESYSTEM :=

include ../common/make/esp32s3-release-module.mk

.PHONY: all build firmware merged-bin upload flash-merged monitor ports clean help

all: firmware

build:
	$(PIO) run --environment $(ENV)

firmware: merged-bin
	@echo "Application firmware: $(APP_BIN)"
	@echo "Complete flash image: $(MERGED_BIN)"

merged-bin: build
	@if [ ! -f "$(BOOT_APP0)" ]; then \
		echo "boot_app0.bin not found: $(BOOT_APP0)"; \
		echo "Override BOOT_APP0 when PlatformIO is installed elsewhere."; \
		exit 1; \
	fi
	@if [ ! -f "$(ESPTOOL)" ]; then \
		echo "esptool.py not found: $(ESPTOOL)"; \
		echo "Override ESPTOOL when PlatformIO is installed elsewhere."; \
		exit 1; \
	fi
	@if [ ! -f "$(PIO_PYTHON)" ]; then \
		echo "PlatformIO Python not found: $(PIO_PYTHON)"; \
		echo "Override PIO_PYTHON when PlatformIO is installed elsewhere."; \
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
		0x10000 "$(APP_BIN)"
	@echo "Complete flash image created: $(MERGED_BIN)"

upload:
	@if [ -z "$(UPLOAD_PORT)" ]; then \
		echo "Upload port not found."; \
		echo "Connect the board, then run: make upload UPLOAD_PORT=/dev/ttyACM0"; \
		$(PIO) device list || true; \
		exit 1; \
	fi
	$(PIO) run --target upload --environment $(ENV) --upload-port "$(UPLOAD_PORT)"

flash-merged: merged-bin
	@if [ -z "$(UPLOAD_PORT)" ]; then \
		echo "Upload port not found."; \
		echo "Connect the board, then run: make flash-merged UPLOAD_PORT=/dev/ttyACM0"; \
		$(PIO) device list || true; \
		exit 1; \
	fi
	$(PIO_PYTHON) $(ESPTOOL) --chip esp32s3 --port "$(UPLOAD_PORT)" \
		--baud 460800 write_flash 0x0 "$(MERGED_BIN)"

monitor:
	@if [ -z "$(UPLOAD_PORT)" ]; then \
		echo "Monitor port not found."; \
		echo "Connect the board, then run: make monitor UPLOAD_PORT=/dev/ttyACM0"; \
		$(PIO) device list || true; \
		exit 1; \
	fi
	$(PIO) device monitor --port "$(UPLOAD_PORT)" --baud 115200

ports:
	$(PIO) device list
	@echo "Automatically selected port: $(AUTO_UPLOAD_PORT)"

clean:
	$(PIO) run --environment $(ENV) --target clean

help:
	@echo "Available targets:"
	@echo "  make / make firmware - Build app and complete flash images"
	@echo "  make build           - Build the PlatformIO application image"
	@echo "  make merged-bin      - Build a complete image flashable at 0x0"
	@echo "  make package         - Create the F/W release module ZIP"
	@echo "  make upload          - Upload through PlatformIO"
	@echo "  make flash-merged    - Flash the complete image at address 0x0"
	@echo "  make monitor         - Open the 115200bps USB debug monitor"
	@echo "  make ports           - List serial ports"
	@echo "  make clean           - Remove PlatformIO build outputs"
