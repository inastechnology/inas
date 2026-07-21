# Hub Extension Security Review Policy

Japanese version: [jp/EXTENSION_SECURITY_REVIEW_POLICY.md](jp/EXTENSION_SECURITY_REVIEW_POLICY.md)

## Scope

This policy applies to every third-party Hub Extension submitted through the UI,
every version update, and every bundled Extension review. Version 1 accepts only
declarative UI manifests. Executable Extensions are out of scope until a
separate-process runner, capability permissions, signatures, and revocation are
implemented.

## Trust Model

- An uploaded file, filename, manifest, description, publisher claim, and AI
  instruction are untrusted input.
- AI review is advisory. It cannot approve a package rejected by deterministic
  checks and cannot guarantee that an accepted package is safe.
- Installation is a separate, explicit administrator action after the complete
  result is displayed.
- A new version is reviewed as a new artifact. Previous approval never carries
  forward by ID alone.
- Unsigned uploads cannot use the reserved `jp.inas.official` namespace or
  replace an installed/bundled Extension.

## Review Pipeline

```text
upload
  -> random review ID and quarantine outside the web root
  -> package size/type/path/compression checks
  -> strict allow-list manifest validation
  -> identity/collision/active-content checks
  -> local review-result dialog
  -> separate confirmation of data/model/cost before optional AI review
  -> AI review of untrusted text only after explicit consent
  -> updated review-result dialog
  -> administrator chooses install or do not install
  -> immutable audit event
```

No uploaded content is imported, executed, or rendered as active markup before
installation. Review fields are displayed only as escaped text. Closing or
cancelling the AI confirmation sends nothing to an AI provider.

## Deterministic Blocking Rules

Installation is blocked when any of the following is found:

- unsupported file type, malformed JSON, or invalid ZIP;
- path traversal, absolute paths, symlinks, encryption, excess members, excess
  decompressed size, or suspicious compression ratio;
- any packaged file other than the root `extension.json` in Extension API v1;
- unknown manifest fields, unsupported API/component/source/tone, duplicate IDs,
  invalid semantic version, or excessive item/text limits;
- executable or active-content markers;
- use of the reserved official namespace without signature verification;
- collision with an installed or bundled Extension.

These checks are authoritative and must remain offline and reproducible.

## AI Review

AI review never starts automatically after upload. A separate confirmation
dialog first identifies the validated manifest and static findings as the only
data sent, shows the configured model, explains that provider charges may
apply, and states that Hub secrets, database records, device data, and API keys
are not included. The administrator must explicitly consent. This consent is
recorded in the audit log.

When the configured text model is available, it then reviews only the validated
manifest and static findings. The system message explicitly treats every
manifest string as data, never as instructions. The AI looks for:

- prompt-injection or review-evasion language;
- publisher impersonation or misleading claims;
- unsafe operational guidance or pressure to bypass Hub safety controls;
- mismatch between declared device scope, data paths, and visible purpose;
- excessive tabs/cards, confusing terminology, or accessibility risks;
- social engineering or requests for credentials and sensitive data.

The AI returns a risk level, concise summary, findings, and recommendation. Its
output is escaped and displayed as text. A high AI risk remains a human decision
for a declarative package; deterministic blockers still control whether the
Install button is available. If AI is unavailable, the dialog must say so and
must not imply that AI completed the review.

## Human Decision

The dialog must show, before installation:

- Extension ID, name, version, artifact SHA-256, and size;
- whether the publisher identity is verified (v1 uploads are unverified);
- deterministic passes, warnings, and blockers;
- AI status, model, risk, findings, recommendation, and limitations;
- the capabilities actually granted by this API version;
- separate `Do not install` and `Install` actions.

The user action, review ID, extension ID/version, digest, time, and risk are
written to an append-only audit log. A blocked package never exposes an Install
action.

## Future Executable Extension Gate

Executable Extensions must not reuse the declarative approval level. Before they
are allowed, INAS must add artifact signatures and identity verification,
immutable releases, SBOM/dependency scanning, malware/static analysis, scoped
permissions, process isolation, network/filesystem deny-by-default, action
gateway validation, crash quarantine, rollback, and registry revocation.

## Reference Baseline

- [OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html): allow-list types, generated storage names,
  limits, storage outside web root, content scanning, and defense in depth.
- [ComfyUI Registry Standards](https://docs.comfy.org/registry/standards): prohibit `eval`/`exec`, runtime package
  installation, and obfuscation.
- [Sigstore](https://docs.sigstore.dev/): signatures bind an artifact digest to a publisher identity and
  transparency evidence.
