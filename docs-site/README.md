# INAS Documentation Site

Public, task-oriented documentation for INAS users and device builders. The
site is Japanese-first and is built with Astro and Starlight.

## Local Development

```bash
cd docs-site
npm install
npm run dev -- --host 0.0.0.0
```

Open `http://localhost:4321`.

Run all static checks and the production build with:

```bash
npm run check
```

## Product Screenshots

Product screenshots are generated from a deterministic, content-rich Hub demo
instead of production data or an empty freshly installed Hub:

```bash
cd docs-site
npm run capture:product-screenshots
```

The command builds the current Hub admin UI, starts
`hub/scripts/run_admin_demo_server.py` with
`HUB_DEMO_SCENARIO=documentation`, captures the documented states, and writes
WebP files to `public/images/screenshots/`. It uses fresh temporary work and
storage directories for every run and removes them afterward. The demo runner
also replaces inherited database, object storage, MQTT, AI, notification, and
other connector settings, so captures cannot read from or write to the running
environment.

Set `DOCS_SCREENSHOT_DATE=YYYY-MM-DD` only when the fixture date must move.
Otherwise the checked-in date remains fixed so work status and relative dates
do not drift between captures. While the demo server is running, `/docs-demo`
lists stable URLs for initial device setup, connection failure, field, device,
calendar, and AI proposal-review states.

Do not edit generated screenshots by hand. Change the demo fixture or capture
manifest, regenerate all images, visually review them, and run `npm run check`.

## Documentation Illustrations

`public/images/illustrations/` contains simple, text-free hardware sketches
and editorial storybook scenes generated with Krea-2 through local ComfyUI.
Hardware illustrations introduce the physical relationship between components;
they are not wiring contracts. Exact pins, voltages, ratings, and cable
requirements remain in the adjacent tables and source specifications.

Keep new illustrations on the same off-white, forest-green, sage, and pale-lime
palette used by the documentation UI. Avoid labels and generated typography.
Record the accepted prompt, seed, dimensions, steps, and CFG in
`scripts/illustration-prompts.json`, then convert the selected PNG to
WebP before publishing.

## Visual Manual Grammar

Every task-oriented guide should make the content type visible before the user
reads the paragraph:

- Put prerequisites and items to prepare in `.manual-prep-panel`. Preparation
  and the procedure itself are the strongest visual elements on the page.
- Use `ManualSteps` for user actions. Each action gets its own short title,
  instruction, and task-specific `ManualVisual`; do not use one hero image as a
  substitute for illustrating the procedure.
- Use `ManualNote` with `caution`, `trouble`, `safe`, or `info` for content that
  is not a step. OK/NG guidance should show the accepted and rejected states in
  the schematic when that comparison is the fastest way to understand it.
- Use deterministic demo screenshots when the exact Hub screen or control is
  the subject. Use code-native SVG schematics for physical relationships,
  choices, checks, and actions that must stay editable with the prose.
- Keep raster screenshots and editorial illustrations inside their linked
  `figure`. The shared lightbox opens them in place; never make readers leave
  the guide just to enlarge an image.
- Reference pages whose main job is exact lookup may remain table-first. Do not
  add decorative art to pin, setting, or compatibility tables when the table is
  clearer.

Review desktop and narrow mobile layouts together. A procedural page is not
complete until the preparation block, action sequence, callout type, figure
zoom, and horizontal overflow have all been checked.

## Code-native Diagrams

Use `ManualSteps` for actions the reader performs. Reserve the shared
`.process-map` pattern for system decision gates and state delivery, and use
`.hierarchy-map` for field ownership or nesting. These diagrams are HTML, SVG,
and CSS so wording can change with the implementation, remain searchable, and
collapse to a vertical reading order on small screens.

Keep each node short and put exact pins, payloads, commands, limits, and failure
conditions in the adjacent table or procedure. Do not add a diagram when an
existing screenshot, comparison table, or short sentence is already clearer.

## Content Ownership

- `docs-site/src/content/docs/` contains public, task-oriented guides.
- `docs-site/public/images/screenshots/` contains reproducible product
  screenshots generated only from the isolated documentation demo.
- General setup pages describe the product like an appliance: prepare a Wi-Fi
  name and password, connect the Hub and one field device, then verify them in
  the browser. Do not expose protocol names, ports, hostname resolution,
  service names, or implementation constraints in that journey.
- Put mDNS, DHCP, MQTT, ports, Cloudflare internals, service topology, firmware
  constraints, and diagnostic commands under `technical/` or another sidebar
  group explicitly labeled for technicians. Link there from a short
  "technicians only" note instead of defining the terms inline.
- `scripts/check-content.mjs` enforces this boundary for the home page and core
  general setup pages. Extend that allowlist when another page becomes part of
  the general onboarding journey.
- The self-build journey starts with technical architecture, hardware selection
  and purchase, then network design, Raspberry Pi preparation, Hub
  installation, and finally device construction. Do not place software setup
  before required purchasing decisions.
- Self-procured hardware is the current actionable route. Company-provided Hub
  and device instructions must remain clearly marked as pending until the
  product specification and shipping checklist are approved.
- `docs/`, `hub/doc/`, and `client-devices/**/docs/` remain the detailed source
  for architecture, operations, firmware contracts, and implementation notes.
- Public pages should state current behavior and link to the owning source when
  deeper implementation detail is useful.
- Never copy secrets, private hostnames, Access tokens, `.env` contents, or
  production device identifiers into public content.

When a hardware or runtime contract changes, update the owning source document,
its generated diagram where applicable, and the corresponding public guide in
the same change.

## Discord Community

Set a permanent public invite in `.env`:

```bash
PUBLIC_DISCORD_COMMUNITY_URL=https://discord.com/invite/bbEcv636eZ
```

The current permanent invite is also the component default. Set this variable
when a deployment needs to override it. Bot tokens and webhook URLs must never
use a `PUBLIC_` variable.

## Cloudflare Deployment

The checked-in `wrangler.jsonc` configures an assets-only Worker for
`docs.inas-technologies.com`. Deployment is intentionally separate from the
marketing landing page Worker.

```bash
npm run deploy
```

Run deployment only after DNS ownership, the Discord invite, and the production
build have been reviewed.
