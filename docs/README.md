# INAS Documentation

This directory contains cross-project documentation for the hub, client
firmware, Cloudflare hosted options, field data, OTA, and operational model.

Public, task-oriented setup and operation documentation is maintained in
[`../docs-site/`](../docs-site/README.md). This directory remains the source for
cross-project specifications and architecture policy.

- [SYSTEM_SPECIFICATION.md](SYSTEM_SPECIFICATION.md): start here for the INAS
  system-level specification.
- [ARCHITECTURE_LAYERING_POLICY.md](ARCHITECTURE_LAYERING_POLICY.md): system-wide
  layer boundaries for hub, firmware, contracts, storage, UI, and adapters.
- [DEVICE_DEFINITION_SPECIFICATION.md](DEVICE_DEFINITION_SPECIFICATION.md):
  firmware-owned Hub metadata, definition-driven device UI, Runtime Config
  projection, and database compatibility.
- [EXTENSION_SPECIFICATION.md](EXTENSION_SPECIFICATION.md): declarative,
  folder-owned Hub extensions and safe UI contribution points.
- [EXTENSION_SECURITY_REVIEW_POLICY.md](EXTENSION_SECURITY_REVIEW_POLICY.md):
  quarantine, deterministic checks, AI-assisted review, and human approval.
- [DISCORD_NOTIFICATION_DESIGN.md](DISCORD_NOTIFICATION_DESIGN.md): low-noise
  actionable cards, Cloudflare-only deep links, and administrator controls.
- [DOCUMENTATION_GUIDE.md](DOCUMENTATION_GUIDE.md): documentation writing,
  localization, linking, and asset rules.
- [CULTIVATION_SYSTEM_ORCHESTRATION.md](CULTIVATION_SYSTEM_ORCHESTRATION.md):
  design policy for composing crop-specific systems such as strawberry drip
  cultivation from multiple devices orchestrated by the hub.
- [AGENTIC_AGRICULTURE_VISION.md](AGENTIC_AGRICULTURE_VISION.md): product
  philosophy for receiving the world's call, returning people to the field,
  and using evidence-backed, bounded cooperation between growers and machines.
- [EDGE_GATEWAY_HARDWARE_AND_IDENTITY.md](EDGE_GATEWAY_HARDWARE_AND_IDENTITY.md):
  identity namespace, secure enrollment boundary, and Raspberry Pi/Compute
  Module appliance profiles for Edge Gateway and Local Hub nodes.
- [../hub-cloud/README.md](../hub-cloud/README.md): shared Cloud Hub frontend,
  authenticated tenant routing, one dedicated Turso DB per customer, and
  factory provisioning.
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
