# Re-record the current Hub product tour with bilingual narration

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` are updated while implementation proceeds.

## Purpose / Big Picture

The LP product tour currently contains a silent Japanese-only capture from an older Hub workflow. After this change, the tour will show the current field dashboard, four-state work board, authenticated submission and manager review, member completion visibility, crop plan, and wake-scheduled irrigation. The same scene plan will produce Japanese and English editions with localized on-screen telops, narration, accessible caption files, and one instrumental background track generated locally through ComfyUI.

The LP will let viewers select Japanese or English before playback. The English edition must show a real, selectable English Hub UI on every product surface included in the tour, in addition to English telops, narration, and captions. Japanese remains the default UI.

## Progress

- [x] (2026-07-22) Audited the current 33.9-second silent MP4 and stale capture script.
- [x] (2026-07-22) Confirmed local Japanese and English TTS voices and ComfyUI ACE-Step 1.5 support.
- [x] (2026-07-23) Defined one 55-second, 11-scene bilingual tour and narration plan.
- [x] (2026-07-23) Updated the capture pipeline and recorded clean Japanese and English visual masters from a fresh demo fixture.
- [x] (2026-07-23) Generated an original 62-second instrumental BGM track in ComfyUI and retained its prompt/seed metadata.
- [x] (2026-07-23) Rendered Japanese and English TTS, ducked the BGM under speech, and exported MP4/VTT/poster assets.
- [x] (2026-07-23) Added the language selector and accessible captions to the LP.
- [x] (2026-07-23) Validated media streams, duration, caption timing, LP behavior, and responsive playback.
- [x] (2026-07-23) Added a real Japanese/English selector and English rendering for the field, work-board, review, member-summary, Gantt, and watering-device tour surfaces.
- [x] (2026-07-23) Re-recorded the English visual master with the English Hub UI and replaced the English MP4/poster.
- [x] (2026-07-23) Revalidated English-screen coverage, media streams, captions, and LP switching.
- [x] (2026-07-23) Audited the LP at ten widths from 320px to 1440px and reviewed all eleven Japanese and English video scenes at full resolution.
- [x] (2026-07-23) Removed the mobile fixed CTA overlap, corrected field-task tag wrapping, kanban header controls, member completion badges, and the work-date filter layout.
- [x] (2026-07-23) Added automated card-boundary, control-overlap, clipped-label, English-placeholder, and fixed-overlay regression checks.
- [x] (2026-07-23) Re-captured and re-rendered both 55-second editions, then deployed the updated LP and media to Cloudflare.

## Surprises & Discoveries

- Observation: the published LP video has H.264 video only and no audio stream.
  Evidence: `ffprobe lp/assets/demo.mp4` reports one 1920x1080 video stream and a 33.9-second duration.

- Observation: the old script describes three work states and predates assignment, review, and member completion visibility.
  Evidence: its scene copy says `未完了・作業中・完了` and never opens the review flow.

- Observation: ComfyUI contains the ACE-Step 1.5 workflow but its four model files are not installed.
  Evidence: the bundled blueprint references the model files while the corresponding model directories contain none of them.

- Observation: an ACE-Step 1.5 all-in-one checkpoint was already installed and could replace the four split files.
  Evidence: `models/checkpoints/ace_step_1.5_turbo_aio.safetensors` loaded successfully through ComfyUI's current checkpoint workflow and generated the 62-second stereo FLAC bed.

- Observation: the current 12-month Gantt belongs to the field work workspace, while the crop workspace now contains crop-specific care, fertilizer, and AI regeneration tools.
  Evidence: `PlantCalendarDrawer.tsx` mounts `AnnualCalendarGantt` only when `workspace === "work"`; the capture now records it without switching to the crop tab.

- Observation: mixing all voice inputs, side-chain compression, and MP4 muxing in a single ffmpeg process caused the audio endpoint to be misdetected.
  Evidence: the first mux produced only 0.305 seconds of AAC and truncated video to 44.9 seconds. Rendering the voice bus, final mix, and MP4 as separate deterministic stages produces exactly 55 seconds at 48 kHz.

- Observation: the Hub stores a legacy `locale` column in user preferences, but current preference normalization forces Japanese and the UI intentionally exposes no language control.
  Evidence: `user_preference_repository.py` normalizes locale to `ja`, while the templates and React calendar contain Japanese literals and the UI tests assert that no locale selector is present.

- Observation: the original seeded watering status did not include `next_sleep_sec`, so the low-power scene displayed an unknown next wake even though the narration discussed wake-based delivery.
  Evidence: the first English recapture showed `Next wake / Not received`; the deterministic demo fixture now supplies a two-hour sleep interval and the final scene shows the computed next wake timestamp.

- Observation: page-level horizontal-overflow checks did not detect the mobile conversion bar covering cards and form fields because the fixed element remained inside the viewport.
  Evidence: 320px card captures showed the fixed bar over the open-source cards and interest form while `scrollWidth` still matched `clientWidth`.

- Observation: element-boundary checks alone did not detect the two member count badges painting over one another inside the same card.
  Evidence: the first high-resolution English member scene clipped `completed`; a dedicated sibling-overlap and label-clipping check now covers this case.

- Observation: the kanban date input has a global 48px touch target, so placing it in a 36px grid row caused it to overlap its caption despite a two-row layout.
  Evidence: computed geometry reported a three-pixel intersection until the second grid row was sized to 48px.

## Decision Log

- Decision: publish separate Japanese and English MP4s from one deterministic scene plan.
  Rationale: narration, telop density, and speech timing differ by language; separate editions avoid overlapping bilingual text and let each version remain readable.
  Date/Author: 2026-07-22 / Codex

- Decision: supersede the earlier Japanese-screen English edition. The English edition will use a real `lang=en` Hub mode and an on-screen Japanese/English selector for the tour surfaces.
  Rationale: English narration over a Japanese product screen is not an English product demo and does not accurately represent the experience being promoted.
  Date/Author: 2026-07-23 / Codex

- Decision: select the tour locale with the `lang=en` query parameter instead of reactivating the legacy saved preference column.
  Rationale: this keeps Japanese as the established default, preserves existing preference behavior, makes shared demo URLs deterministic, and lets links carry the selected locale without changing an account-wide setting.
  Date/Author: 2026-07-23 / Codex

- Decision: generate one wordless, restrained instrumental bed with ACE-Step and reuse it in both editions.
  Rationale: the BGM should reinforce brand consistency without competing with narration or creating different emotional claims by language.
  Date/Author: 2026-07-22 / Codex

- Decision: include sidecar VTT captions even though the explanatory telops are burned into the picture.
  Rationale: VTT supports accessibility, indexing, and future players that can hide or restyle captions.
  Date/Author: 2026-07-22 / Codex

- Decision: use the installed local Windows SAPI voices, Haruka for Japanese and Zira for English.
  Rationale: both required languages are available offline, deterministic, and require no external speech service or credential.
  Date/Author: 2026-07-23 / Codex

- Decision: render the voice bus, ducked music mix, and final MP4 in separate stages.
  Rationale: fixed-duration intermediate WAV files make missing narration, sample rate, and truncation directly testable before publication.
  Date/Author: 2026-07-23 / Codex

- Decision: remove the persistent mobile conversion bar and retain the existing in-flow hero, menu, and interest-form calls to action.
  Rationale: the fixed bar repeatedly covered real content on small screens, while the page already offers equivalent conversion paths without obscuring reading or input.
  Date/Author: 2026-07-23 / Codex

- Decision: preserve the 48px help touch targets and give kanban headings a two-row layout instead of shrinking the controls.
  Rationale: the overlap was a layout-capacity problem; retaining accessible targets avoids trading readability for a smaller hit area.
  Date/Author: 2026-07-23 / Codex

## Plan of Work

Refactor the browser capture into a locale-driven deterministic tour. Use a fresh demo directory so the pending and approved work records are guaranteed. Replace stale scenes with the field status, four-state task board, manager review, member task visibility, crop plan, and scheduled irrigation configuration. Keep scene lengths aligned to concise narration lines.

Add a Japanese-default, query-selectable locale to the Hub pages used by the tour. Provide a visible selector that preserves the current route and query state. Localize server-rendered field/device surfaces and the React work-board surface, including dynamic demo labels and accessibility text visible in the recording. Capture English URLs with `lang=en`; do not perform capture-only DOM substitution.

Download only the four models declared by the bundled ACE-Step 1.5 blueprint into the local ComfyUI model directories. Start a temporary ComfyUI server, submit a fixed prompt and seed for an instrumental organic-technology bed, validate the generated audio, and stop the server.

Synthesize narration with the installed Japanese and English system voices. Normalize every line, place it at the scene start, apply side-chain ducking to the BGM, and export AAC audio with H.264 video. Produce VTT captions and language-specific posters. Update the LP video dialog with explicit Japanese and English controls and test source switching without losing dialog focus or analytics.

## Validation and Acceptance

The final Japanese and English MP4s must each contain one 1920x1080 H.264 video stream and one AAC stereo audio stream, use the current Hub demo, and play without browser console errors. Every Hub label visible in the English edition must be English; the UI locale selector must show English as active. The voice must remain intelligible over the BGM, telops must fit within the safe area, and VTT timings must cover every narration line.

Run:

    ffprobe -v error -show_streams -show_format lp/assets/demo-ja.mp4
    ffprobe -v error -show_streams -show_format lp/assets/demo-en.mp4
    HUB_URL=http://127.0.0.1:39251 npm --prefix hub/admin-ui run smoke:demo-english-ui
    npm --prefix lp run check

The LP smoke must switch sources in both directions, expose Japanese and English caption tracks, and retain responsive playback at desktop and mobile widths.

## Idempotence and Recovery

The capture uses a fresh temporary Hub work directory and does not touch production state. Model downloads are local ComfyUI dependencies and are not committed. Fixed scene data, music prompt, and seeds make the render reproducible. Existing `demo.mp4` remains a compatibility copy of the Japanese edition until all references migrate.

## Outcomes & Retrospective

The LP now serves Japanese and English 55-second editions of the current Hub tour. The English visual master uses the real `?lang=en` Hub mode across the field dashboard, four-state work board, member completion summary, manager review dialog, 12-month outlook, device overview, and irrigation schedule. The visible `JA / EN` selector reports English as active, while the no-query experience remains Japanese.

The English UI smoke opens all four product pages plus the review dialog, verifies zero visible Japanese strings and zero browser errors, checks the Japanese default, and confirms locale-preserving links. The final low-power scene shows a concrete next wake timestamp from the deterministic demo fixture. `lp/assets/demo-en.mp4` is 55 seconds of 1920×1080 H.264 with English-tagged AAC stereo at 48 kHz; the LP build, Worker test, desktop/mobile browser smoke, three focused Hub tests, media probe, and `git diff --check` all pass.

The music bed was generated locally in ComfyUI with ACE-Step 1.5 using the fixed prompt and seed in `tour.json`. The final files are 1920×1080 H.264 at 30 fps with AAC stereo at 48 kHz. Both are exactly 55 seconds; Japanese integrated loudness measures -16.40 LUFS and English -16.68 LUFS, with true peaks below -1 dBFS. The Japanese and English decoded audio hashes differ, confirming that each localized voice bus is present.

`npm --prefix lp run check` passes, including source switching, both caption tracks, Worker tests, desktop and mobile browser smoke, and responsive screenshots. Desktop and 390px mobile visual inspection confirms that the language controls, English title, video controls, and descriptive copy fit without clipping.

The overflow follow-up now tests twenty LP states across 320, 360, 375, 390, 430, 768, 820, 1024, 1280, and 1440 pixels, and ten Hub scene pages covering sixty cards in Japanese and English. Both report zero boundary escapes, fixed overlays, clipped count labels, and overlapping controls. Full-resolution scene review confirms that task tags wrap within their card, kanban help buttons no longer collide with headings, member counts remain distinct, the date field is readable, and the manager note placeholder is English.

The updated LP, Japanese video, and English video are live at `https://inas-technologies.com/app/` in Cloudflare Worker version `f25b90c8-21b4-43e1-aa3f-6ae80f0d646d`. The public CSS hash matches the local build and the same ten-width responsive audit passes against the production URL. The repository-owned Hub deployment completed all 405 tests after switching temporary files to Linux `/tmp`, but the service installation could not proceed because this environment requires interactive sudo authentication and has no non-interactive askpass path; no production Hub unit was modified.
