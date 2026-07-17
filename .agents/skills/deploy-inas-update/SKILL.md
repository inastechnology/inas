---
name: deploy-inas-update
description: Safely fetch, test, and deploy the latest origin/main implementation of the INA monorepo Hub while preserving existing tracked edits, runtime files, .env, MQTT, HTTP, and Cloudflare settings. Use when the user asks to pull new INA commits, apply a new implementation, update the running INA Hub, deploy the latest main branch, or perform the server's normal pull-and-deploy workflow.
---

# Deploy INA Update

Run the repository-owned deployment script as the single source of truth:

```bash
bash .agents/skills/deploy-inas-update/scripts/deploy.sh
```

Run it from anywhere inside the INA repository. Request one escalated execution approval for the complete command because it fetches Git commits, synchronizes dependencies, creates a state backup, updates systemd units, restarts the production Hub, and checks localhost health endpoints.

The script must:

1. Lock concurrent deployments and verify the repository, branch, remote, Hub layout, installer, and `uv` installation.
2. Fetch `origin/main` and reject divergent or unpublished local commits.
3. Preserve tracked staged and unstaged edits with a tracked-only stash. Leave untracked runtime files untouched. Restore the tracked edits before testing and deployment.
4. Fast-forward to the fetched remote revision without rebasing or force-updating.
5. Synchronize the locked environment and run the full Hub unittest suite.
6. Invoke `hub/scripts/install_service.sh` in normal upgrade mode without `--production`, preserving `.env` and existing external-service settings.
7. If the installer reaches its 30-second readiness timeout, continue a bounded readiness check because production startup can take longer after schema or task changes.
8. Verify systemd state plus `/healthz` and `/readyz`, then report the previous and deployed revisions.

Never print, source, copy, stage, or commit `.env`, runtime JSON, tokens, passwords, private endpoints, state backups, or command output containing their values. The deployment script may read only `HUB_HTTP_PORT` from `.env` to select the local health endpoint.

Use `--preflight` to validate command discovery and repository assumptions without fetching, modifying Git state, testing, or deploying:

```bash
bash .agents/skills/deploy-inas-update/scripts/deploy.sh --preflight
```

Use `--force` only when the current revision must be redeployed even though `origin/main` has no new commit.

If any stage fails, stop. Preserve the user's edits and any remaining stash, report the failing stage and service state, and diagnose before rerunning. Never discard changes, force-push, reset the repository, or automatically roll back code.

On success, report the deployed commit, test count/result, backup result emitted by the installer, service status, and health/readiness result. Mention preserved pre-existing workspace changes without presenting them as part of the deployed commit.
