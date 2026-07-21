# Hub Extension Specification

Japanese version: [jp/EXTENSION_SPECIFICATION.md](jp/EXTENSION_SPECIFICATION.md)

## Purpose

Hub Extensions let device metadata, agricultural knowledge, integrations, and
small UI contributions evolve in isolated folders. The Hub owns stable extension
points and safety rules; an Extension owns its manifest, assets, tests, and
contributions.

The initial Extension API is intentionally declarative. It does not import
arbitrary Python, JavaScript, or HTML into the Hub process.

## Repository Layout

```text
extensions/<extension-name>/
  extension.json
  assets/                 # optional
  tests/                  # optional
```

`hub/scripts/build_extension_registry.py` validates every manifest and produces
the packaged registry read by the running Hub:

```text
hub/src/ina_device_hub/extensions/generated/registry.json
```

The source folders may later move to independent repositories without changing
the manifest format. Development copies can be placed under `extensions/`, while
production releases can be pinned and assembled before deployment.

## UI Extension Points

Version 1 provides two device-detail extension points:

- `overview_cards`: short, glanceable information shown on the existing
  overview. This must not become a second settings screen.
- `tabs`: a cohesive supplementary workspace. A tab is appropriate when its
  content has its own task or mental model.

Settings fields and large standalone pages are reserved extension points for a
later version. A contribution must use Hub-rendered components so responsive
layout, keyboard navigation, text sizing, contrast, and escaping remain owned by
the Hub.

Supported version 1 blocks are:

- `callout`: a title and concise explanation.
- `metric_grid`: values resolved from allow-listed `device`, `status`, or
  `config` paths on the server.
- `process_flow`: ordered steps with titles and descriptions.

## Safety And Compatibility

- Extension and contribution IDs are validated and globally stable.
- A manifest declares `compatibility.hub_extension_api`.
- Unknown component types and data sources fail the registry build.
- Values are resolved by the Hub and escaped by the template renderer.
- Extension UI cannot add executable HTML, scripts, event handlers, or remote
  assets.
- Core operations, MQTT commands, credentials, and database access are not
  exposed by the UI registry.

Executable Extensions will require a separate runner and a permissioned Host API.
They must not be implemented as automatic imports from the Extension directory.

## Build And Test

```bash
cd hub
uv run python scripts/build_extension_registry.py
uv run python scripts/build_extension_registry.py --check
uv run python -m unittest tests.test_extension_registry
```

The generated registry is committed so packaged and installed Hub builds do not
need the repository source tree at runtime.

## Administrator Installation

Administrators can open **App settings → Extensions** and upload a single
`extension.json` or `.inas-extension` package. Upload performs deterministic
local checks only. It does not install the Extension or contact an AI provider.
If the package passes, the administrator may open a separate AI preflight
dialog. That dialog shows the exact data classes sent, configured model,
destination, and possible provider cost; AI review begins only after explicit
consent. Installation remains a separate final decision.

Installed manifests are stored under the Hub work directory and merged with the
bundled registry. They remain declarative and receive exactly the same schema
validation and Hub-owned rendering as bundled contributions. See the
[Extension security review policy](EXTENSION_SECURITY_REVIEW_POLICY.md).

AI developers must also follow
[`../extensions/AGENTS.md`](../extensions/AGENTS.md). A copyable manifest is
available at
[`../extensions/_template/extension.example.json`](../extensions/_template/extension.example.json).
