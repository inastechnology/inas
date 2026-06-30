# Repository Guidelines

## Project Structure & Module Organization

This is a Python IoT hub using a `src` layout. Application modules live in `src/ina_device_hub/`, including MQTT handling, storage, repositories, scheduling, Flask web serving, and settings. HTML templates are in `src/ina_device_hub/templates/`. Operational scripts live in `scripts/`, systemd units in `systemd/`, and design/operations documentation in `doc/` and `doc/spec/`. Root files such as `pyproject.toml`, `README.md`, `serve.sh`, and environment templates define local setup and entry points.

## Build, Test, and Development Commands

- `rye sync`: install and sync project dependencies into the managed environment.
- `cp .default.env .env`: create local configuration, then edit secrets and endpoints for the target environment.
- `rye run serve`: run the local hub service; the README notes the default web endpoint as `http://localhost:5151`.
- `rye run format`: apply Ruff formatting and autofixable lint changes.
- `rye run lint`: run Ruff checks, Ruff format verification, and mypy with explicit package bases.
- `sudo ./scripts/install_service.sh`: install and enable the systemd template services for deployment targets.

## Coding Style & Naming Conventions

Use Python 3.11-compatible style. Ruff is the formatter and linter; line length is configured as 160, double quotes are preferred, and import ordering is handled by Ruff/isort rules. Keep modules and files in `snake_case`, classes in `PascalCase`, functions and variables in `snake_case`, and constants in `UPPER_SNAKE_CASE`. Follow the existing repository pattern: connectors, repositories, and task modules are separated by responsibility under `src/ina_device_hub/`.

## Testing Guidelines

No dedicated test suite is currently present in the repository. For now, run `rye run lint` before submitting changes. When adding tests, place them under a top-level `tests/` directory, name files `test_<module>.py`, and prefer focused tests for repositories, settings parsing, MQTT payload handling, and Flask route behavior. Add any new test runner dependency and command to `pyproject.toml` when introducing the suite.

## Commit & Pull Request Guidelines

Recent history uses Conventional Commit-style prefixes such as `feat:`, `fix:`, `refactor:`, and `chore:`, with occasional documentation-only commits. Prefer short imperative subjects, for example `fix: handle null telemetry values`. Pull requests should describe the behavior change, list verification commands run, link related issues, and include screenshots or logs when changing web output, MQTT topics, systemd behavior, or deployment scripts.

## Security & Configuration Tips

Do not commit real `.env` files, Turso tokens, S3 credentials, MQTT passwords, or device-specific secrets. Keep environment examples generic and update `src/ina_device_hub/setting.py` plus `README.md` when adding or renaming required configuration values.


# ExecPlans
 
When writing complex features or significant refactors, use an ExecPlan (as described in .agent/PLANS.md) from design to implementation.
