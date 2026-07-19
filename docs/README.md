# INAS Documentation

This directory contains cross-project documentation for the hub, client
firmware, Cloudflare hosted options, field data, OTA, and operational model.

- [SYSTEM_SPECIFICATION.md](SYSTEM_SPECIFICATION.md): start here for the INAS
  system-level specification.
- [ARCHITECTURE_LAYERING_POLICY.md](ARCHITECTURE_LAYERING_POLICY.md): system-wide
  layer boundaries for hub, firmware, contracts, storage, UI, and adapters.
- [DEVICE_DEFINITION_SPECIFICATION.md](DEVICE_DEFINITION_SPECIFICATION.md):
  firmware-owned Hub metadata, definition-driven device UI, Runtime Config
  projection, and database compatibility.
- [DOCUMENTATION_GUIDE.md](DOCUMENTATION_GUIDE.md): documentation writing,
  localization, linking, and asset rules.
- [CULTIVATION_SYSTEM_ORCHESTRATION.md](CULTIVATION_SYSTEM_ORCHESTRATION.md):
  design policy for composing crop-specific systems such as strawberry drip
  cultivation from multiple devices orchestrated by the hub.
- [AGENTIC_AGRICULTURE_VISION.md](AGENTIC_AGRICULTURE_VISION.md): product
  philosophy for evidence-backed, bounded, rail-independent cooperation between
  growers, fixed equipment, services, and future robots.
- [jp/](jp/): Japanese versions of the same level of documentation.
- [assets/inas_system_diagrams.drawio](assets/inas_system_diagrams.drawio):
  draw.io source for the system architecture, data/control flow, field placement
  model, and OTA flow diagrams.

Regenerate the default English diagrams with:

```sh
python3 docs/assets/generate_system_diagrams.py
```

Documentation convention:

- Default documents in each directory are written in English.
- Japanese documents are stored under `jp/` inside the relevant documentation
  tree.
- Keep paths stable where possible, and link from English docs to Japanese docs
  when both are available.
