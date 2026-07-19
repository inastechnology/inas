# Build the INAS App marketing landing page and printable brochure

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds. This plan follows `hub/AGENTS.md` and the ExecPlan format documented by the adjacent INA repository's `.agent/PLANS.md`.

## Purpose / Big Picture

INAS App needs a public-facing explanation that a first-time grower can understand without knowing electronics or system administration. After this change, opening `/inas-app` on the Hub demo server will show a polished Japanese landing page that explains the value of observing a field, planning work with AI, and controlling irrigation. The same page will include real Hub screenshots, explain that the software and hardware designs are open source, and offer two honest adoption paths: build the hardware oneself or buy an official preconfigured Raspberry Pi Hub and supported devices. Printing the page will produce a compact A4 brochure rather than a long web page.

## Progress

- [x] (2026-07-19 10:20Z) Reviewed the current INAS Technologies website, its public-interest/open-source message, and its cyan-to-lavender brand accents.
- [x] (2026-07-19 10:25Z) Audited the Hub template, static asset, demo server, browser smoke, and route structure.
- [x] (2026-07-19 10:30Z) Generated a text-free, photorealistic Japanese smart-farming hero image with the built-in image generation workflow.
- [x] (2026-07-19 10:33Z) Added the standalone `/inas-app` page, responsive styling, accessible interactions, and print layout.
- [x] (2026-07-19 10:35Z) Seeded an isolated demo with three placed assets, an active crop, target-range sensor values, planned/in-progress/completed work, and a bound irrigation device; captured three current Hub screens into durable marketing assets.
- [x] (2026-07-19 10:38Z) Added browser and Python route tests, built the UI, and passed all 316 Python regression tests.
- [x] (2026-07-19 10:39Z) Captured and inspected desktop, mobile, and print screenshots; corrected lazy screenshot loading, print emoji fallback, and a fourth PDF page before accepting the final three-page brochure.

## Surprises & Discoveries

- Observation: The corporate website currently leads with “公益に資するスマート栽培基盤を、オープンソースで。” and uses a more abstract technology aesthetic than the Hub's green field UI.
  Evidence: The live homepage title and hero copy were fetched from `https://inas-technologies.com/` on 2026-07-19.
- Observation: The Hub already has browser smoke infrastructure based on `puppeteer-core`, so real application views can be reproduced rather than mocked in a design tool.
  Evidence: `hub/admin-ui/scripts/field-detail-smoke.mjs` captures the field and calendar screens, and `device-detail-smoke.mjs` captures device screens.
- Observation: The working tree contains unrelated, uncommitted calendar work. The marketing implementation must be additive and must not reset or rewrite those edits.
  Evidence: `git status --short` listed modified calendar, repository, and generated bundle files before this plan began.
- Observation: Full-page Puppeteer screenshots do not scroll through the page before capture, so product images marked `loading="lazy"` remained blank even though the page layout was correct.
  Evidence: The first desktop and mobile LP captures showed empty browser frames; removing lazy loading made all three real Hub screens appear in the next capture.
- Observation: Setting each print sheet's minimum height to the A4 content area does not guarantee a three-page PDF if one sheet's content grows beyond that height.
  Evidence: The first PDF contained four `/Type /Page` objects. The print smoke measured the start sheet at 1286px versus the 1055px content limit. Placing the open-source introduction and both adoption paths on one three-column row reduced every sheet to 1054px and the PDF to three pages.

## Decision Log

- Decision: Serve the page from the Hub at `/inas-app`, while keeping its template and assets isolated under `templates/inas_app.html` and `static/inas-app/`.
  Rationale: This gives an immediately testable URL and a self-contained package that can later be moved into the corporate website without depending on the operational Hub UI bundle.
  Date/Author: 2026-07-19 / Codex
- Decision: Use the live corporate site's public-interest and open-source positioning, but give INAS App a warmer editorial farming style with the Hub's green operational color as the primary accent.
  Rationale: The product page should feel related to INAS Technologies while communicating soil, crops, water, and daily usefulness instead of abstract technology alone.
  Date/Author: 2026-07-19 / Codex
- Decision: Avoid invented prices, customer counts, performance percentages, certifications, testimonials, and a live purchase button.
  Rationale: None of those facts were supplied. The page should be credible and ready for future commerce without publishing unsupported claims.
  Date/Author: 2026-07-19 / Codex
- Decision: Reuse one semantic HTML document for web and print, with print-only reordering and page breaks in CSS.
  Rationale: One source prevents the brochure and landing page copy from diverging. Web sections can be spacious and interactive, while `@media print` can compress them into deliberate A4 pages.
  Date/Author: 2026-07-19 / Codex
- Decision: Use generated imagery only for the hero and use actual Hub captures for product explanations.
  Rationale: The hero needs emotional context, while feature claims are most trustworthy when illustrated by the real application.
  Date/Author: 2026-07-19 / Codex

## Outcomes & Retrospective

The Hub now serves a complete Japanese INAS App product page at `/inas-app`. It combines an original human-centered farming hero, a beginner-readable three-step explanation, three genuine Hub screenshots populated with coherent marketing demo data, open-source and future official-hardware adoption paths, audience examples, and a restrained call to action. The same semantic page produces a deliberate three-page A4 PDF.

Validation completed on 2026-07-19. `npm run build` passed, `npm run capture:marketing` passed, `npm run smoke:marketing` passed at 1440px desktop, 390px mobile, and print media, and `python -m unittest discover -s tests` passed all 316 tests. `git diff --check` reported no errors. Manual inspection confirmed readable hierarchy, real product images, no horizontal overflow, and correct three-page brochure composition. The running isolated demo is available at `http://127.0.0.1:39306/inas-app`.

The page is intentionally isolated from the operational Hub bundle so its template and assets can later be moved to `inas-technologies.com`. Publishing there, adding real product prices/availability, and replacing the current “提供準備中” state remain future business decisions rather than incomplete implementation.

## Context and Orientation

The Hub is a Python Flask application under `hub/src/ina_device_hub`. Flask maps URLs to response functions in `web_server.py`, renders HTML from `templates`, and serves files under `static`. The newer field layout and calendar interface is built in `hub/admin-ui`, compiled into static files, and embedded into the field templates. A “landing page” is a public product explanation optimized for a reader who arrives without prior context. A “print stylesheet” is CSS inside `@media print` that changes the same HTML when a browser prints or exports it as PDF.

The new template will not depend on a logged-in user, field database, device state, or external JavaScript. It will use semantic headings, ordinary links, accessible labels, and small progressive enhancements. Marketing screenshots will be generated by a deterministic Puppeteer script under `hub/admin-ui/scripts` against the existing demo server. The script will write only to `hub/src/ina_device_hub/static/inas-app/hub-*.webp` or PNG files and may be rerun whenever the UI changes.

## Plan of Work

First, add the generated hero image and current Hub screenshots under `hub/src/ina_device_hub/static/inas-app`. Create `hub/src/ina_device_hub/templates/inas_app.html` with a compact navigation bar, a human-centered hero, a three-step value explanation, real-product feature sections, an open-source ownership section, two adoption paths, audience examples, and a restrained call to action. Copy must explicitly state that people may source components and build devices from published designs, while official preconfigured hardware will be offered for people who prefer support. It must describe affordability as a design goal, not make an unsupported price claim.

Create `hub/src/ina_device_hub/static/inas-app/inas-app.css` for responsive layout and `inas-app.js` only if a minimal mobile menu or screenshot tab control materially improves comprehension. The page should remain fully readable without JavaScript. Add `@media print` rules for A4 portrait output, hide web navigation and buttons that have no print meaning, keep QR/contact placeholders out until real destinations are supplied, and use explicit page breaks so the hero/value proposition, feature tour, and adoption/open-source content form coherent brochure pages.

Add a thin Flask route in `web_server.py` returning the new template. Add focused route assertions in `hub/tests/test_web_server_basic_ui.py` for HTTP 200, core copy, stylesheet, real screenshot references, open-source/build and official-hardware paths, and print semantics. Add the browser capture script and package command, plus an LP smoke script that checks desktop width, mobile width, important landmarks, absence of horizontal overflow, and print media rendering.

Run the full Python suite and the admin UI build. Start the demo server on an unused local port, capture real Hub screenshots, then capture the LP at desktop and mobile widths and as print/PDF or print-emulated screenshots. Inspect every image. If text, focus, cropping, contrast, or page breaks are weak, update the page and repeat the screenshots before marking this plan complete.

## Concrete Steps

All commands start from `/home/polonity/workspace/ina-technologies/inas` unless another directory is named.

Copy the generated hero image into the product asset directory, create the template and CSS through `apply_patch`, and register the route. Build the existing React UI before capturing Hub screens:

    cd hub/admin-ui
    npm run build

Start the demo server with an isolated writable database:

    cd hub
    HUB_DEMO_PORT=39306 HUB_DEMO_WORK_DIR=/tmp/ina-device-hub-marketing PYTHON_DOTENV_DISABLED=1 UV_CACHE_DIR=.uv-cache uv run python scripts/run_admin_demo_server.py

In another shell, generate Hub captures and validate the LP:

    cd hub/admin-ui
    HUB_URL=http://127.0.0.1:39306 npm run capture:marketing
    HUB_URL=http://127.0.0.1:39306 npm run smoke:marketing

Run backend regression tests:

    cd hub
    PYTHON_DOTENV_DISABLED=1 UV_CACHE_DIR=.uv-cache uv run python -m unittest discover -s tests

The expected final unittest transcript ends with `OK`. The browser scripts should exit with code zero and report the screenshot paths they produced.

## Validation and Acceptance

Opening `http://127.0.0.1:39306/inas-app` at 1440px wide must show a complete page with a clear product name, the statement “育てる判断を、もっとやさしく。” or equivalent, an immediate summary of what the app does, and a visible route to explore features. A reader must understand within the first two sections that INAS App connects field observation, AI cultivation planning, records, and controllable devices.

The feature tour must use screenshots captured from the real demo Hub and must explain each screen in plain Japanese. The open-source section must clearly distinguish “自分でつくる” from “公式ハードウェアから始める,” without implying that official products are already in stock. The mobile viewport must have no horizontal overflow and no clipped controls. Print emulation must produce intentional A4 pages with no navigation chrome, no split feature card headings, no dark ink-heavy full-page background, and readable URLs or contact destinations.

The route test, complete Python suite, TypeScript/Vite build, marketing screenshot capture, and browser smoke must all pass. Desktop, mobile, and print screenshots must be manually inspected and their paths recorded in `Outcomes & Retrospective`.

## Idempotence and Recovery

The implementation is additive. Re-running the screenshot script replaces only named marketing screenshots. The demo work directory is under `/tmp`, does not inherit production Turso settings, and can be abandoned safely. No production database migration is required. If image generation or browser capture fails, the page remains functional; retry the failed asset step without resetting the working tree. Do not use `git reset`, `git checkout`, or removal commands against unrelated user changes.

## Artifacts and Notes

The generated hero source is stored by the built-in image tool at:

    /home/polonity/.codex/generated_images/019f6ea8-6d8b-7603-ad84-78a1760f70e0/exec-b390014d-3157-4f83-bdbe-218f805e127a.png

Its prompt specifies a Japanese strawberry grower, a modest greenhouse and field, realistic sensors and irrigation, left-side headline space, warm morning light, and no text, logos, science-fiction effects, or unsafe exposed electronics. The selected output is 1672 by 941 pixels and will be copied into the repository before use.

## Interfaces and Dependencies

`hub/src/ina_device_hub/web_server.py` will expose a GET-only `inas_app_landing_page()` route at `/inas-app` that returns `render_template("inas_app.html")`. No repository or service dependency is needed.

`hub/admin-ui/scripts/marketing-capture.mjs` will use the already installed `puppeteer-core` dependency and `HUB_URL`. It will capture real field, calendar, and device views into the marketing static directory. `marketing-smoke.mjs` will use the same dependency and verify the public page at desktop, mobile, and print media settings. No new npm or Python dependency is required.

Revision note (2026-07-19): Initial plan created after reviewing the corporate website, repository route structure, current dirty working tree, and generated hero asset.

Revision note (2026-07-19): Marked implementation complete after building the LP, seeding and capturing visually coherent real Hub data, generating and inspecting the three-page brochure, and passing browser/build/backend validation.
