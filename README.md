# INAS

This repository contains the INAS hub services and client device firmware.

## Documentation

Start with [INAS System Specification](docs/SYSTEM_SPECIFICATION.md) for the cross-project
architecture, device roles, field data model, OTA flow, and Cloudflare hosted
options. The draw.io source for the system diagrams is
[docs/assets/inas_system_diagrams.drawio](docs/assets/inas_system_diagrams.drawio).
Documentation writing and localization rules are defined in
[docs/DOCUMENTATION_GUIDE.md](docs/DOCUMENTATION_GUIDE.md).
Japanese documentation is stored under `jp/` directories, such as
[docs/jp/SYSTEM_SPECIFICATION.md](docs/jp/SYSTEM_SPECIFICATION.md).

## Client Device Layout

Client firmware projects live under `client-devices/`.

```text
client-devices/
  common/
    lib/
      ina-client-common/      # Shared PlatformIO library
  watering-device/            # Watering device firmware, device kind: WTR
```

Each device project owns its device-specific App layer, such as sensors,
actuators, pins, schedules, and the top-level application flow. Shared client
firmware code is kept in `client-devices/common/lib` and is mounted into each
device project through a symbolic link under the device project's `lib/`
directory.

The watering device currently uses:

```text
client-devices/watering-device/lib/ina-client-common
  -> ../../common/lib/ina-client-common
```

When adding another device, create a new directory under `client-devices/`, add
its concrete `AppDevice` implementation there, and link the shared library from
`client-devices/common/lib`.

## Linux / WSL2 Requirement

Client device firmware uses symbolic links for local PlatformIO libraries.
Build the firmware on Linux.

Windows users should use WSL2. Native Windows builds from PowerShell or Command
Prompt are not supported for client firmware because Git and PlatformIO may
handle symbolic links differently depending on Windows settings.

Recommended WSL2 setup:

```bash
wsl --install -d Ubuntu
```

Then, inside Ubuntu on WSL2:

```bash
sudo apt update
sudo apt install -y git make python3 python3-pip python3-venv
python3 -m pip install --user platformio
```

Clone this repository inside the WSL2 Linux filesystem, such as under `~/work`.
Avoid building from `/mnt/c/...`; it is slower and more likely to expose Windows
filesystem behavior around symbolic links.

For the watering device:

```bash
cd client-devices/watering-device
cp default.env.user.ini .env.user.ini
make build
```

Use `make upload` or `make merged-bin` from the same directory when needed.
