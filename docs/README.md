# INAS Documentation

This directory contains cross-project documentation for the hub, client
firmware, Cloudflare hosted options, field data, OTA, and operational model.

- [SYSTEM_SPECIFICATION.md](SYSTEM_SPECIFICATION.md): start here for the INAS
  system-level specification.
- [DOCUMENTATION_GUIDE.md](DOCUMENTATION_GUIDE.md): documentation writing,
  localization, linking, and asset rules.
- [CULTIVATION_SYSTEM_ORCHESTRATION.md](CULTIVATION_SYSTEM_ORCHESTRATION.md):
  design policy for composing crop-specific systems such as strawberry drip
  cultivation from multiple devices orchestrated by the hub.
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
- Japanese documents are stored under a sibling `jp/` directory at the same
  hierarchy level.
- Keep paths stable where possible, and link from English docs to Japanese docs
  when both are available.
