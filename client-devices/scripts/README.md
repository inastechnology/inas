# Client Device Scripts

## Create A Device Project

Use `create_device_project.py` to scaffold a new PlatformIO firmware project
that uses the shared INAS client library.

```bash
python3 client-devices/scripts/create_device_project.py soil-device SOI \
  --display-name "INA Soil Sensor"
```

The script creates `client-devices/<project>/`, links
`lib/ina-client-common`, sets a fixed three-letter `APP_DEVICE_KIND`, and
generates the standard `Makefile`, OTA partition table, and firmware manifest
build flags.

Build from the generated project directory:

```bash
cd client-devices/soil-device
make build
make check-firmware
```

The script refuses to overwrite an existing project. Treat each `device_kind`
as a fixed hardware contract: if pin assignment, connected sensors, actuator
role, or payload schema materially changes, create another project and assign a
new three-letter device kind.
