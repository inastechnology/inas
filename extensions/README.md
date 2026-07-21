# INAS Hub Extensions

Hub Extensions are isolated, declarative contributions assembled into the Hub at
build time. Version 1 can add device-detail overview cards and supplementary tabs
without executing Extension-owned code.

For the complete schema and security model, read
[`../docs/EXTENSION_SPECIFICATION.md`](../docs/EXTENSION_SPECIFICATION.md). AI
development rules are in [`AGENTS.md`](AGENTS.md).

## Add An Extension

1. Copy `_template/extension.example.json` to
   `<your-extension>/extension.json`.
2. Choose a stable reverse-domain ID and list the applicable device kinds.
3. Use only supported declarative blocks.
4. Regenerate and test the registry from `hub/`.

```bash
UV_CACHE_DIR=.uv-cache uv run python scripts/build_extension_registry.py
UV_CACHE_DIR=.uv-cache uv run python scripts/build_extension_registry.py --check
UV_CACHE_DIR=.uv-cache uv run python -m unittest tests.test_extension_registry
```

The generated registry is packaged with the Hub. Production does not scan or
execute these source directories at runtime.
