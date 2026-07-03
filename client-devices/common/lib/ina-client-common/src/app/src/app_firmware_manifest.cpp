#include "app_def.h"

extern "C" __attribute__((used, aligned(16), section(".rodata.inas_firmware_manifest")))
const char INAS_FIRMWARE_MANIFEST[] =
    "INAS_FW_MANIFEST_V1_BEGIN\n"
    "schema=1\n"
    "project=" APP_FIRMWARE_PROJECT "\n"
    "device_kind=" APP_DEVICE_KIND "\n"
    "version=" APP_FIRMWARE_VERSION "\n"
    "build_id=" APP_FIRMWARE_BUILD_ID "\n"
    "target=" APP_FIRMWARE_TARGET "\n"
    "framework=" APP_FIRMWARE_FRAMEWORK "\n"
    "INAS_FW_MANIFEST_V1_END\n";
