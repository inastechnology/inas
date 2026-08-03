PIO ?= platformio
PYTHON ?= python3
PIO_ENV ?= $(ENV)
ENV := $(PIO_ENV)
PLATFORMIO_CORE_DIR ?= $(CURDIR)/.pio-core
PIO_RUN = PLATFORMIO_CORE_DIR="$(PLATFORMIO_CORE_DIR)" $(PIO)
PIO_PYTHON ?= $(shell sed -n '1s/^#!//p' "$(shell command -v $(PIO))")
ESPTOOL_PYTHON = $(if $(wildcard $(PLATFORMIO_CORE_DIR)/penv/bin/python),$(PLATFORMIO_CORE_DIR)/penv/bin/python,$(PIO_PYTHON))
ESPTOOL_SCRIPT = $(PLATFORMIO_CORE_DIR)/packages/tool-esptoolpy/esptool.py
BUILD_DIR := .pio/build/$(PIO_ENV)
REPO_ROOT ?= $(abspath ../..)
FIRMWARE_CHECKER ?= $(REPO_ROOT)/hub/scripts/check_firmware_manifest.py
FACTORY_MERGER ?= $(REPO_ROOT)/client-devices/common/tools/merge_flash_image.py
RELEASE_MODULE_TOOL ?= $(REPO_ROOT)/client-devices/common/tools/create_release_module.py
APP_BIN := $(BUILD_DIR)/firmware.bin
FACTORY_BIN := $(BUILD_DIR)/firmware.factory.bin
FILESYSTEM_BIN := $(BUILD_DIR)/littlefs.bin
PARTITIONS_CSV ?= partitions.csv
FILESYSTEM_OFFSET ?= $(shell awk -F, '$$1 ~ /^[[:space:]]*storage[[:space:]]*$$/ {gsub(/[[:space:]]/,"",$$4); print $$4}' "$(PARTITIONS_CSV)" 2>/dev/null)
FILESYSTEM_MAX_SIZE ?= $(shell awk -F, '$$1 ~ /^[[:space:]]*storage[[:space:]]*$$/ {gsub(/[[:space:]]/,"",$$5); print $$5}' "$(PARTITIONS_CSV)" 2>/dev/null)
APP_MAX_SIZE ?= $(shell awk -F, '$$1 ~ /^[[:space:]]*app0[[:space:]]*$$/ {gsub(/[[:space:]]/,"",$$5); print $$5}' "$(PARTITIONS_CSV)" 2>/dev/null)
BOOT_APP0 ?= $(PLATFORMIO_CORE_DIR)/packages/framework-arduinoespressif32/tools/partitions/boot_app0.bin
HAS_FILESYSTEM ?= 1
HAS_NATIVE_TESTS ?= 0
HAS_FIRMWARE_MANIFEST ?= 1
NATIVE_TEST_ENV ?= native
AUTO_UPLOAD_PORT := $(shell ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null | head -n 1)
UPLOAD_PORT ?= $(AUTO_UPLOAD_PORT)
MONITOR_BAUD ?= 115200
FLASH_BAUD ?= 460800
RELEASE_MODULE_TARGET ?= $(PIO_ENV)
RELEASE_MODULE_CHIP ?= $(ESP_CHIP)
RELEASE_MODULE_FLASH_SIZE ?= $(FLASH_SIZE)
RELEASE_MODULE_FILESYSTEM := $(if $(filter 1,$(HAS_FILESYSTEM)),$(FILESYSTEM_BIN),)
RELEASE_MODULE_DIAGNOSTIC_PROFILE ?= shipping/diagnostic-profile.json
RELEASE_PACKAGE ?= release/$(DEVICE_ID)-$(DEVICE_VERSION)-$(PIO_ENV).inasfw
RELEASE_MODULE_OPTIONAL_ARGS = $(if $(strip $(RELEASE_MODULE_FILESYSTEM)),--filesystem "$(RELEASE_MODULE_FILESYSTEM)") $(if $(wildcard $(RELEASE_MODULE_DIAGNOSTIC_PROFILE)),--diagnostic-profile "$(RELEASE_MODULE_DIAGNOSTIC_PROFILE)")

.DEFAULT_GOAL := all

.PHONY: all test build check check-firmware buildfs factory-bin merged-bin package upload flash flash-merged monitor ports clean help

all: check

test: $(USER_CONFIG)
ifeq ($(HAS_NATIVE_TESTS),1)
	$(PIO_RUN) test --environment $(NATIVE_TEST_ENV)
else
	@echo "No native tests configured for $(DEVICE_ID)"
endif

build: $(USER_CONFIG)
	$(PIO_RUN) run --environment $(PIO_ENV)

check-firmware: build
ifeq ($(HAS_FIRMWARE_MANIFEST),1)
	$(PYTHON) "$(FIRMWARE_CHECKER)" "$(APP_BIN)"
else
	@echo "No firmware manifest configured for $(DEVICE_ID)"
endif

check: test check-firmware

buildfs: $(USER_CONFIG)
ifeq ($(HAS_FILESYSTEM),1)
	$(PIO_RUN) run --environment $(PIO_ENV) --target buildfs
else
	@echo "No filesystem configured for $(DEVICE_ID)"
endif

factory-bin: build $(if $(filter 1,$(HAS_FILESYSTEM)),buildfs)
	@test -f "$(BOOT_APP0)" || { echo "Missing $(BOOT_APP0)"; exit 1; }
	$(PYTHON) "$(FACTORY_MERGER)" --output "$(FACTORY_BIN)" --size "$(FLASH_SIZE)" \
		--region 0x0="$(BUILD_DIR)/bootloader.bin" \
		--region 0x8000="$(BUILD_DIR)/partitions.bin" \
		--region 0xe000="$(BOOT_APP0)" \
		--region 0x10000="$(APP_BIN)" \
		$(if $(filter 1,$(HAS_FILESYSTEM)),--region $(FILESYSTEM_OFFSET)="$(FILESYSTEM_BIN)")

merged-bin: factory-bin
	@echo "Compatibility alias: factory image is $(FACTORY_BIN)"

package: $(if $(filter 1,$(HAS_FIRMWARE_MANIFEST)),check-firmware,build) $(if $(filter 1,$(HAS_FILESYSTEM)),buildfs)
	$(PYTHON) "$(RELEASE_MODULE_TOOL)" \
		--build-dir "$(BUILD_DIR)" --boot-app0 "$(BOOT_APP0)" \
		--output "$(RELEASE_PACKAGE)" --module-id "$(DEVICE_ID)" \
		--device-kind "$(DEVICE_KIND)" --display-name "$(DEVICE_NAME)" \
		--firmware-version "$(DEVICE_VERSION)" --target "$(PIO_ENV)" \
		--chip "$(ESP_CHIP)" --flash-size "$(FLASH_SIZE)" \
		--app-max-size "$(APP_MAX_SIZE)" \
		$(if $(filter 1,$(HAS_FILESYSTEM)),--filesystem-offset "$(FILESYSTEM_OFFSET)" --filesystem-max-size "$(FILESYSTEM_MAX_SIZE)") \
		$(RELEASE_MODULE_OPTIONAL_ARGS)

upload: $(USER_CONFIG)
	@test -n "$(UPLOAD_PORT)" || { echo "Upload port not found. Set UPLOAD_PORT."; exit 1; }
	$(PIO_RUN) run --environment $(PIO_ENV) --target upload --upload-port "$(UPLOAD_PORT)"

flash: factory-bin
	@test -n "$(UPLOAD_PORT)" || { echo "Upload port not found. Set UPLOAD_PORT."; exit 1; }
	@test -f "$(ESPTOOL_SCRIPT)" || { echo "Missing $(ESPTOOL_SCRIPT)"; exit 1; }
	"$(ESPTOOL_PYTHON)" "$(ESPTOOL_SCRIPT)" --chip $(ESP_CHIP) \
		--port "$(UPLOAD_PORT)" --baud $(FLASH_BAUD) write_flash 0x0 "$(FACTORY_BIN)"

flash-merged: flash

monitor:
	@test -n "$(UPLOAD_PORT)" || { echo "Monitor port not found. Set UPLOAD_PORT."; exit 1; }
	$(PIO_RUN) device monitor --port "$(UPLOAD_PORT)" --baud $(MONITOR_BAUD)

ports:
	$(PIO_RUN) device list

clean:
	$(PIO_RUN) run --environment $(PIO_ENV) --target clean

help:
	@echo "Unified firmware targets for $(DEVICE_ID):"
	@echo "  test         Run native tests when configured"
	@echo "  build        Build firmware.bin"
	@echo "  check        Run tests, build, and verify the firmware manifest"
	@echo "  buildfs      Build littlefs.bin when configured"
	@echo "  factory-bin  Build firmware.factory.bin for address 0x0"
	@echo "  package      Build the shipping .inasfw package"
	@echo "  upload       Upload the application through PlatformIO"
	@echo "  flash        Flash firmware.factory.bin at address 0x0"
	@echo "  monitor      Open the USB serial monitor"
	@echo "  ports        List serial ports"
	@echo "  clean        Remove PlatformIO build outputs"
	@echo "  merged-bin and flash-merged remain compatibility aliases"
