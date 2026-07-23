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

## Content Ownership

- `docs-site/src/content/docs/` contains public, task-oriented guides.
- The public setup journey starts with system overview, hardware selection and
  purchase, then network design, Raspberry Pi preparation, Hub installation,
  and finally device construction. Do not place software setup before required
  purchasing decisions.
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
