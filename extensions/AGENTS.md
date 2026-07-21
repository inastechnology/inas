# Hub Extension Rules For AI Developers

These instructions apply to every file under `extensions/`. They are normative
for AI-authored Extension changes.

## Read Before Editing

Read these files completely:

- `../docs/EXTENSION_SPECIFICATION.md`
- `../docs/EXTENSION_SECURITY_REVIEW_POLICY.md`
- `../docs/ARCHITECTURE_LAYERING_POLICY.md`
- `README.md`

Inspect at least one existing Extension and
`../hub/scripts/build_extension_registry.py` before creating a new manifest. Do
not infer an unsupported schema from UI code or invent manifest fields.

## Ownership And Boundaries

- One Extension owns one directory: `extensions/<kebab-case-name>/`.
- Put its manifest, assets, fixtures, and Extension-specific tests in that
  directory when the supported schema allows them.
- Keep Extension-specific names, copy, process steps, and applicability out of
  Hub core.
- A Hub core change is allowed only when adding a reusable Extension API
  capability that benefits more than one Extension.
- Device firmware behavior belongs to `client-devices/<device>/`, not an
  Extension.
- Firmware capability metadata belongs to a Device Definition. Do not duplicate
  sensor slots, output terminals, masks, or Runtime Config send keys in an
  Extension.
- Never access the Hub database, MQTT client, GPIO, secrets, or `.env` from a
  declarative Extension.

## Manifest Rules

- Use a stable reverse-domain `id`, for example
  `jp.inas.community.example-weather`.
- Never change a released Extension ID. A display name may change; identity may
  not.
- Increment `version` when behavior or visible content changes.
- Declare the exact supported `compatibility.hub_extension_api`.
- Use only component types, value sources, tones, and fields accepted by the
  registry builder.
- Do not add HTML, JavaScript, event attributes, remote embeds, Python imports,
  shell commands, or package installation instructions to a declarative
  manifest.
- Do not edit
  `hub/src/ina_device_hub/extensions/generated/registry.json` manually. Regenerate
  it with the build script.

## Choosing A UI Extension Point

Use the smallest surface that matches the user task:

1. Use `overview_cards` for short information needed during routine checks.
   Cards are not settings forms and must remain understandable without opening
   another screen.
2. Use `tabs` when an Extension has one cohesive task, workflow, or explanation
   that needs several blocks. Prefer one well-structured tab over several small
   tabs.
3. Do not create a tab only to show one sentence or one metric; use an overview
   card instead.
4. Do not place rarely used diagnostics before daily operational information.
5. A future settings contribution must use Hub-owned form components and save
   through Hub validation. Until that API exists, do not imitate settings with
   static UI blocks.
6. A future standalone page is appropriate for large searchable collections,
   long histories, or complex editors. It must still be linked from a named Hub
   slot rather than patched into global navigation.

Version 1 supports only:

- `callout`
- `metric_grid`
- `process_flow`

If the requested UI cannot be represented safely, stop and propose a reusable
Extension API addition. Do not work around the schema with raw markup.

## UX And Accessibility

- Write farmer-facing language. Do not expose circuit, bus, mask, pin, transport,
  or internal-ID terminology in ordinary UI.
- Put the user action or current state first; implementation details come later.
- Keep labels short and explanations concrete.
- Preserve a logical heading order and ordered process flow.
- Do not rely on color alone. Text must explain states and warnings.
- Use Hub tones semantically and maintain sufficient contrast.
- Verify keyboard tab selection and arrow-key navigation.
- Verify at desktop width and at 390px mobile width with no horizontal page
  overflow.
- When visible UI changes, capture both desktop and mobile screenshots and inspect
  them before declaring completion.

## Data And Compatibility

- `metric_grid` may read only the allow-listed `device`, `status`, and `config`
  sources.
- Use stable existing paths. A missing value must remain visible as `未設定`; do
  not silently replace it with zero.
- Do not migrate, delete, or rename existing database configuration merely to
  display an Extension.
- Extension removal must not damage stored device configuration.
- Do not send new Runtime Config keys to firmware through an Extension. Update
  the relevant Device Definition and firmware project when the firmware contract
  truly changes.

## Required Workflow

After editing an Extension manifest:

```bash
cd hub
UV_CACHE_DIR=.uv-cache uv run python scripts/build_extension_registry.py
UV_CACHE_DIR=.uv-cache uv run python scripts/build_extension_registry.py --check
UV_CACHE_DIR=.uv-cache uv run python -m unittest tests.test_extension_registry
```

If Hub rendering changes, also run:

```bash
PYTHON_DOTENV_DISABLED=1 UV_CACHE_DIR=.uv-cache uv run python -m unittest discover -s tests
UV_CACHE_DIR=.uv-cache uv run ruff check .
UV_CACHE_DIR=.uv-cache uv run ruff format --check .
```

Start the isolated demo and run the device-detail browser test:

```bash
cd hub
UV_CACHE_DIR=.uv-cache uv run python scripts/run_admin_demo_server.py

cd admin-ui
HUB_URL=http://127.0.0.1:39251 npm run smoke:device-detail
```

Inspect the generated screenshots, not only the assertions.

## Extension API Changes

When adding a reusable Extension API feature, update all of the following in the
same change:

- English and Japanese Extension specifications
- Registry builder validation
- Runtime registry loader/resolver
- Safe Hub renderer
- Positive and rejection tests
- At least one real sample Extension
- Desktop and mobile browser assertions and screenshots
- CI path filters and stale-registry checks when relevant

Do not mark the work complete if the generated registry is stale, the full tests
fail because of the change, or the screenshots have not been inspected.

## Security Review

- Treat every third-party package and every manifest string as hostile input.
- Deterministic validation is authoritative; AI review is advisory and cannot
  override a blocker.
- Never render or execute uploaded content before explicit installation.
- Every version and digest must be reviewed independently.
- Keep uploaded content outside the web root and use server-generated review IDs.
- Reject traversal, symlinks, encryption, ZIP bombs, unknown fields, active
  content, official-ID impersonation, and ID collisions.
- Display static checks, AI status and limitations, artifact identity, and granted
  capabilities before asking the administrator to install.
- Never start AI review on upload. Show a separate preflight confirmation with
  the exact data classes sent, configured model, external-transfer notice, and
  possible provider cost. A cancel action must send nothing.
- Record review and install decisions in the audit log.
