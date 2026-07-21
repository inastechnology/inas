# Build a demand-validation landing page for INAS App

This ExecPlan is a living document. `Progress`, `Decision Log`, `Surprises & Discoveries`, and `Outcomes & Retrospective` are updated while implementation proceeds. It follows `hub/AGENTS.md` and the established ExecPlan pattern under `hub/.agent`.

## Purpose / Big Picture

INAS App already has a brochure-style product introduction, but paid advertising needs a shorter and more decisive landing page. A visitor arriving from an advertisement should understand within a few seconds that INAS connects field observation, AI cultivation planning, work records, and irrigation; see real product screens; decide whether the product addresses their own cultivation problem; and express interest without needing to understand electronics.

The new page lives under the repository root `lp/` as a standalone static site. It can be previewed with an ordinary static HTTP server and later deployed independently of the Hub. It reuses the honest product photography, real Hub screenshots, and demo video already produced for the brochure. It does not invent prices, availability, adoption counts, testimonials, certifications, or yield improvements.

## Progress

- [x] (2026-07-20) Audited the existing brochure LP, real Hub captures, demo video, corporate website positioning, and available public destinations.
- [x] (2026-07-20) Created the standalone semantic HTML, responsive visual system, existing-photo hero, real-screen feature tour, audience tabs, FAQ, demand form, and accessible video dialog under `lp/`.
- [x] (2026-07-20) Added session-scoped UTM/ad-click attribution, PII-free conversion events, configurable lead submission, honest unconfigured fallback behavior, and deployment/measurement notes.
- [x] (2026-07-20) Added a zero-dependency local server/browser smoke script and validated desktop, 390px mobile, menu, tabs, video dialog, form validation, unconfigured form behavior, configured success submission, 48px touch targets, optimized hero delivery, and horizontal overflow.
- [x] (2026-07-20) Captured and manually inspected full and focused desktop/mobile screenshots. Increased body, FAQ, and form typography after the first review and recaptured all views.

## Decision Log

- Decision: Build a separate static site under `lp/` instead of extending the printable `/inas-app` page.
  Rationale: Paid-ad traffic needs a focused conversion path and campaign attribution, while the existing page intentionally serves both long-form product explanation and A4 printing.
  Date/Author: 2026-07-20 / Codex
- Decision: Reuse actual Hub captures and the existing 34-second demo video rather than generating mock product screens.
  Rationale: Demand validation is more credible when feature claims are supported by the current working product.
  Date/Author: 2026-07-20 / Codex
- Decision: Treat CTA clicks and lead form completion as separate conversion events, while keeping the form endpoint configurable.
  Rationale: The repository contains no verified public contact address or production form endpoint. Inventing one would lose leads or disclose unsupported contact information. A static configuration file allows the destination to be supplied at deployment without rebuilding the page.
  Date/Author: 2026-07-20 / Codex
- Decision: Use the official website, GitHub organization, and Instagram account as verified outbound destinations.
  Rationale: These links exist on the current INAS Technologies website and can be published without assumptions.
  Date/Author: 2026-07-20 / Codex

## Surprises & Discoveries

- Observation: The current corporate site has no visible contact or wait-list form, and the repository has no verified public contact email.
  Evidence: The current homepage HTML links to Philosophy, Articles, GitHub, Instagram, Medium, and Privacy only. Repository search found example addresses but no production contact address.
- Observation: The existing demo video is only about 1.6 MB for 33.9 seconds, so it is suitable for an optional, user-initiated LP video without creating an excessive initial download.
  Evidence: `ffprobe` reports 33.9 seconds and 1,595,396 bytes.

## Context and Orientation

The root `lp/` directory will be independent from Flask and React. `index.html` contains the whole public page, `styles.css` is its responsive design system, `app.js` provides progressive enhancement, and `config.js` contains deployment-specific endpoints and analytics identifiers without secrets. Assets under `lp/assets/` are copies of existing repository marketing files so the directory can be deployed by itself.

The page supports UTM parameters and an optional `audience` parameter. Attribution is kept in the page session and attached to CTA events and form submissions. When `leadEndpoint` is configured, the form sends JSON with the visitor's role, cultivation scale, principal problem, desired capability, optional message, consent, and attribution. When it is not configured, the page explains that the preview is not connected and offers verified official destinations; it must not claim that an unsubmitted lead was received.

## Plan of Work

Create an emotionally direct hero with one primary promise, a visible development/demand-survey label, two CTAs, and a real status panel. Follow it with problem recognition, the three connected outcomes, the short product video, current Hub screens, audience-specific use cases, open-source and official-hardware adoption paths, a concise FAQ, and a final interest form. Keep one primary green CTA style and give all interactive targets at least 48 CSS pixels on touch layouts.

Add `config.js` with empty `leadEndpoint`, `analyticsMeasurementId`, and `metaPixelId` values plus verified URLs. `app.js` will preserve UTM attribution, dispatch a documented `inas:conversion` browser event, push to `dataLayer` if present, send Meta events only when a configured pixel exists, manage the mobile menu and video dialog, and submit the lead form only to a configured endpoint. It will avoid cookies and third-party scripts by default.

Add a zero-dependency Node smoke script using the existing `puppeteer-core` installation from `hub/admin-ui`. The script will serve `lp/` locally, verify headings and CTA semantics, check campaign propagation, exercise the audience selector, video dialog, menu, and form fallback, assert no horizontal overflow at desktop and 390px mobile widths, and write reusable screenshots into `lp/artifacts/`.

## Validation and Acceptance

- The first viewport identifies the product, its concrete value, its development/demand-survey status, and a primary action without scrolling.
- All product claims are illustrated with an existing real Hub screen or clearly described as a goal/current development direction.
- Desktop and 390px mobile views have no horizontal overflow, clipped text, overlapping sticky elements, or undersized primary controls.
- Keyboard focus is visible, the video opens in an accessible dialog, Escape closes it, and reduced-motion users do not receive unnecessary animation.
- UTM values and the selected audience appear in conversion payloads without including unrelated browser or device fingerprint data.
- An unconfigured form never displays a false success message; a configured endpoint path can be exercised by the smoke test with an intercepted response.
- Screenshots are opened and manually inspected before work is considered complete.

## Idempotence and Recovery

The implementation is additive. Re-running the capture script replaces only named files under `lp/artifacts/`. Asset copies use existing source files and may be refreshed without modifying the source marketing assets. No database, Hub setting, or production endpoint is changed. No secret belongs in `config.js` because every file in a static site is public.

## Outcomes & Retrospective

The repository now contains a standalone demand-validation site under `lp/`. The first viewport states “畑に行く前に、今日やることがわかる。”, labels the product as under development, shows an actual cultivation scene and field-status card, and presents one primary early-interest action plus a short product demo. The rest of the page connects four common problems to three outcomes, a 34-second real Hub recording, three current Hub screens, audience-specific starting points, open-source and planned official-hardware paths, FAQ answers, and a structured one-minute interest form.

Campaign attribution retains UTM values, `gclid`, and `fbclid` only for the session and includes them in PII-free conversion events and configured lead submissions. An unconfigured deployment does not send or retain entered personal information and explicitly tells the operator to configure `leadEndpoint`. The smoke test also substitutes a local endpoint and verifies a successful lead payload, including campaign attribution.

`npm run smoke` completed successfully. It verified no browser console errors or horizontal overflow at 1440px and 390px, a 48px minimum for primary mobile controls, real image loading, WebP hero selection, mobile navigation, keyboard-addressable audience tabs, native video dialog behavior, missing-endpoint honesty, and successful configured submission. `node --check lp/app.js`, `node --check lp/scripts/smoke.mjs`, and `git diff --check` passed. The hero displayed by browsers is about 181KB instead of the 2.3MB PNG fallback, and the social preview image is about 192KB.

Manual inspection accepted the visual hierarchy and cropping in:

- `lp/artifacts/inas-demand-lp-desktop-hero.png`
- `lp/artifacts/inas-demand-lp-desktop.png`
- `lp/artifacts/inas-demand-lp-mobile-hero.png`
- `lp/artifacts/inas-demand-lp-mobile.png`
- `lp/artifacts/inas-demand-lp-mobile-form.png`

After a user review on 2026-07-21, secondary gray copy was found too faint for older readers. `--ink-soft` and individual helper, dark-background, status-card, footer, and dialog colors were darkened or raised in opacity; several small labels were also enlarged. The browser smoke and all focused screenshots were regenerated and inspected again with no overflow or layout regression.

The only intentional pre-publication item is the actual lead receiver. `lp/config.js` leaves `leadEndpoint` blank because no verified production form endpoint or public contact email exists. `lp/README.md` documents the exact JSON contract, endpoint safety requirements, campaign parameters, events, and recommended funnel metrics.

Revision note (2026-07-20): Initial plan created after auditing the existing brochure, product captures, demo video, and verified public destinations.

Revision note (2026-07-20): Marked implementation and visual validation complete after responsive browser smoke, optimized assets, lead-flow verification, and manual screenshot review.

Revision note (2026-07-21): Increased secondary-text contrast and small-label sizes after user feedback, then reran browser and visual validation.
