# Documentation Guide

Japanese version: [jp/DOCUMENTATION_GUIDE.md](jp/DOCUMENTATION_GUIDE.md)

This guide defines how documentation is written, translated, linked, and
maintained in this repository.

## Language Policy

- English is the default language for documentation.
- Japanese documentation is stored under a `jp/` directory inside the relevant
  documentation tree, such as `docs/`, `doc/`, or `<device>/docs/`.
- Keep the same file name in Japanese directories whenever practical.
- If a detailed document exists only in Japanese, keep it under the relevant
  documentation tree's `jp/` directory and add an English summary or index
  document at the default path.

Examples:

```text
docs/SYSTEM_SPECIFICATION.md
docs/jp/SYSTEM_SPECIFICATION.md

hub/README.md
hub/doc/jp/README.md

hub/doc/OPERATIONS.md
hub/doc/jp/OPERATIONS.md

client-devices/README.md
client-devices/docs/jp/README.md

client-devices/docs/pin_assignments.md
client-devices/docs/jp/pin_assignments.md
```

## Directory Rules

Each documentation hierarchy owns its own Japanese directory. Entry documents
without a dedicated `doc` or `docs` directory are localized into the nearest
documentation tree.

| Default location | Japanese location | Scope |
|---|---|---|
| `README.md` | `docs/jp/README.md` | Repository entry documentation |
| `docs/` | `docs/jp/` | Cross-project specifications and system diagrams |
| `hub/README.md` | `hub/doc/jp/README.md` | Hub entry documentation |
| `hub/doc/` | `hub/doc/jp/` | Hub operations, Cloudflare, UX, and design notes |
| `hub/doc/spec/` | `hub/doc/spec/jp/` | Hub implementation specifications |
| `client-devices/README.md` | `client-devices/docs/jp/README.md` | Client device entry documentation |
| `client-devices/docs/` | `client-devices/docs/jp/` | Shared device specifications and diagrams |
| `client-devices/<device>/docs/` | `client-devices/<device>/docs/jp/` | Device-specific manuals and specifications |

Do not move Japanese documents to a single global directory when the document
belongs to a lower-level component. Also do not create top-level `jp/`
directories directly under the repository root, `hub/`, or `client-devices/`;
place Japanese Markdown under their `doc` or `docs` tree.

## Link Rules

- Use relative Markdown links.
- English documents should link to the Japanese counterpart when one exists.
- Japanese documents should link to Japanese counterparts where possible.
- When a Japanese counterpart does not exist, linking to the English document is
  acceptable.
- After moving a document into `jp/`, re-check relative links because `../`
  paths often need one extra level.

## Asset Rules

- Language-specific diagrams or screenshots follow the same `jp/` rule.
- Language-neutral assets may be shared from the default asset directory.
- Generated SVG files should be regenerated from their source script instead of
  edited manually.
- Keep draw.io sources near their rendered SVG/PNG outputs.

Current generators:

```sh
python3 docs/assets/generate_system_diagrams.py
python3 client-devices/docs/generate_xiao_pin_assignment_diagrams.py
```

## Writing Style

- Prefer concise, implementation-oriented prose.
- State current behavior separately from planned or future behavior.
- Keep command examples copy-pasteable.
- Use stable names for device kinds, such as `WTR`, `WRS`, `SOI`, and `ENV`.
- Use exact environment variable names, topic names, file paths, and API paths
  in monospace.
- For farmer-facing descriptions, explain the operational meaning before the
  raw variable or payload field.
- Avoid mixing implementation details into overview documents. Link to the
  detailed specification instead.

## Document Shape

Recommended structure for specifications:

1. Purpose
2. Scope
3. Current behavior
4. Data model or topic/API contract
5. Operational rules
6. Failure handling
7. Related documents

Recommended structure for implementation plans:

1. Goal
2. Non-goals
3. Constraints
4. Proposed design
5. Migration steps
6. Tests
7. Open questions

## Versioning And Dates

- Use ISO dates such as `2026-07-12` when a date is needed.
- Avoid relative dates such as "today" or "next month" in long-lived documents.
- Prefer describing compatibility by firmware version, device kind, schema
  version, or migration state.

## Generated Or External Content

- Do not treat files under `node_modules`, `.pio`, or other dependency
  directories as repository documentation.
- Do not edit vendored README files for repository-level documentation changes.
- When adding generated files, also document the generator command.

## Maintenance Checklist

Before finishing a documentation change:

```sh
rg -n "\p{Hiragana}|\p{Katakana}|\p{Han}" --glob '*.md' --glob '*.svg' --glob '!**/jp/**' README.md docs client-devices hub
python3 docs/assets/generate_system_diagrams.py
python3 client-devices/docs/generate_xiao_pin_assignment_diagrams.py
```

Run a Markdown link check for repository-owned documents and exclude dependency
directories such as `node_modules` and `.pio`.
