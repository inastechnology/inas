# Register and manage network cameras from the Hub UI

This ExecPlan is a living document. It follows the ExecPlan requirement in `hub/AGENTS.md`; `.agent/PLANS.md` is not present in this checkout.

## Purpose / Big Picture

Network cameras are already used for RTSP preview, timelapse capture, field imagery, and Instagram posting, but operators can only register them by editing `.camera_device_list.json`. The device-maintenance UI should expose an administrator-only manual registration flow with a bounded server-side connection test, show registered cameras alongside MQTT equipment, and support safe editing and deletion without exposing credentials or breaking field and Instagram references.

## Progress

- [x] (2026-07-18) Audited camera persistence, RTSP connector behavior, device-list rendering, authentication, field references, and Instagram camera selection.
- [x] (2026-07-18) Added atomic camera metadata and credential repositories with legacy-record compatibility.
- [x] (2026-07-18) Added validation, connection testing, CRUD orchestration, and reference-aware deletion.
- [x] (2026-07-18) Added camera API routes, registration/edit UI, and camera cards to device maintenance.
- [x] (2026-07-18) Added repository, service, API, and UI regressions; deployed and verified the production Hub.

## Surprises & Discoveries

- `CameraDeviceRepository.add()` is not called by any Hub route or service. The current Reolink record was therefore created outside the UI.
- Camera credentials are currently stored in the same JSON object as display metadata. New writes must separate credentials while the connector continues to read legacy records.
- The existing device-maintenance catalog is backed only by MQTT device configuration records, so a camera can be healthy and selected by Instagram while remaining invisible in the device list.

## Decision Log

- Decision: Keep IP cameras outside the MQTT device configuration repository and aggregate them only at the presentation layer.
  Rationale: Reolink and Tapo RTSP cameras do not participate in the Hub MQTT lifecycle, config distribution, firmware, or device-state transitions.
- Decision: Make registration manual and place the primary entry point on the device-maintenance page, with contextual links from settings when no camera is available.
  Rationale: Manual host and credential entry is predictable across segmented networks; discovery can be added later without changing the data model.
- Decision: Store camera metadata and credentials separately, never return passwords from APIs, and keep legacy combined records readable until they are edited.
  Rationale: Existing installations remain compatible while new and updated records no longer expose passwords in the general camera inventory.
- Decision: Run an administrator-only, bounded one-frame RTSP probe and reject public, loopback, link-local, multicast, and unspecified destinations.
  Rationale: Connection feedback is necessary for setup, while unrestricted server-side URL probing would create an SSRF boundary.
- Decision: Block deletion while a camera is referenced by a field, layout placement, or Instagram settings; retain captured media.
  Rationale: Removing only the registration must not silently break active workflows or destroy historical imagery.

## Plan of Work

Extend camera persistence with atomic upsert/delete operations and a mode-0600 credential repository. Add a camera management service that validates operator input, merges legacy credentials internally, redacts public records, tests RTSP connectivity through the connector, and reports reference conflicts before deletion.

Expose JSON CRUD and connection-test routes under `/local/api/cameras`. Add `/cameras/new` and `/cameras/<id>/edit` forms, render registered cameras on `/mqtt-devices`, and link the empty Instagram camera state to registration. Preserve the existing preview and image routes.

## Validation and Acceptance

Focused tests must prove metadata validation, secret separation, legacy credential compatibility, password redaction, connection-test error mapping, administrator API behavior, edit-with-blank-password retention, reference-aware deletion, camera rendering in the device list, and registration links in both device maintenance and settings. The complete Python unittest suite plus Ruff lint and formatting checks must pass.

Validation completed on 2026-07-18:

- `PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m unittest discover -s tests`: 296 tests passed.
- Ruff lint and format checks passed for all seven Python files changed by this work.
- The repository-wide Ruff run still reports pre-existing import ordering in `scripts/build_device_definition_registry.py`, `device_config_service.py`, and `device_definition_registry.py`, plus pre-existing formatting in `test_mqtt_device_config_service.py`; these unrelated files were not changed.
- The connection-test service fetched one frame from the existing Reolink camera without printing credentials.
- Production `/mqtt-devices` renders the existing `garden` camera and the registration action; `/cameras/new` renders the manual setup and connection-test controls.
- Production systemd state is active/running, `/healthz` is `ok`, and `/readyz` reports MQTT and Web ready.

## Idempotence and Recovery

Repository writes are atomic and serialized. A failed metadata write may leave an unreferenced credential entry but must never expose or delete an existing secret. Existing `.camera_device_list.json` records remain readable, and no automatic destructive migration runs at startup. Updating a legacy record writes its credentials to the protected store and removes secret fields from the metadata record. Deletion leaves timelapse media untouched.

## Outcomes & Retrospective

Camera setup is now an operator workflow instead of a JSON-editing task. The device-maintenance page shows MQTT equipment and cameras together, existing legacy registrations remain immediately visible, and administrators can register or edit Reolink, Tapo, and custom RTSP cameras with a bounded one-frame test. Passwords are absent from public records and new metadata writes, referenced cameras cannot be deleted, and captured images remain independent of registration lifecycle.
