# Phase D Entry Plan

Recorded on 2026-05-30 after the Phase C exit gate and current-regression
check.

## Entry Decision

Phase D is cleared to start.

Current gate results:

- `git status --short --branch`: `## main...origin/main`
- `.\apps\api\.venv\Scripts\python.exe -m pytest --basetemp=data\cache\pytest`:
  250 passed, with one pytest cache permission warning under `.pytest_cache`.
- `npm.cmd run build` in `apps/web`: passed.
- `npm.cmd run e2e:all` in `apps/web`: passed, including Phase 2
  preprocessing, Phase C batch retry, Phase 3 epoch, and Phase 3 ERP smoke
  tests.

Phase C can be treated as closed because workflow templates, batch planning,
batch worker execution, retry, cancellation, batch summary artifacts, and the
individual-run QC/report/export contracts are covered by tests and browser
smoke.

## Current Baseline For Phase D

The older research-tool roadmap still lists several items as missing, but the
current code already has first-pass implementations for some of them:

- BIDS sidecar parsing exists in `packages/eeg-io/src/eeg_io/bids_sidecars.py`.
- Event mapping already supports presets and row filters through the API and UI.
- Run diagnostics already include structured warning objects alongside legacy
  string warnings.
- QC summary and QC dashboard paths exist for preprocessing, epoch, and ERP
  artifacts.
- Export bundle generation exists and includes analysis report, manifest,
  diagnostics, figures, provenance, artifacts, and batch context.

Phase D should therefore focus on closing the gaps between these MVP pieces and
repeatable public EEG dataset use, not on rebuilding them from scratch.

## Scope Additions For Phase D

Add these items to the Phase D scope before implementation:

- Update stale roadmap status so Phase D starts from the actual current code
  baseline.
- Add a formal public-dataset validation matrix covering at least PhysioNet
  EEGMMI and one OpenNeuro/BIDS-style sample.
- Integrate BIDS sidecar discovery into dataset upload or dataset registration,
  not only standalone parsers.
- Preserve source/provenance manifest details for EEG files, event files, and
  discovered sidecars, including checksums where practical.
- Harden event normalization for BIDS `events.tsv`, including null handling,
  filtered rows, source row preservation, and condition derivation.
- Define a stable diagnostic warning taxonomy for BIDS, event mapping,
  validation, worker, artifact, export, and batch warnings.
- Add docs/user-guide updates for BIDS sidecars, event presets, diagnostics, QC,
  and export expectations.
- Keep all additions backward-compatible with existing run JSON, template
  snapshots, batch snapshots, artifact manifests, and export bundles.

Out of scope for Phase D:

- Full statistical testing.
- Permutation tests and multiple-comparison correction.
- Full reproducibility graph and one-click rerun.
- Collaboration/share snapshots.
- Large visual regression suite.
- Complete multi-subject batch UI beyond the Phase C foundation.

## One-Prompt Work Slices

Each item below is sized so it can be given to Codex as one implementation
request.

### D0. Baseline And Roadmap Sync

- Update `docs/research-tool-completion-roadmap.md` to reflect the Phase C exit
  state and current MVP implementations.
- Link this Phase D entry plan from the roadmap or release checklist.
- Do not change runtime code.

Acceptance:

- Documentation no longer says BIDS sidecar parsing, event presets, structured
  warnings, QC summary, or export bundle are entirely missing.
- Phase D scope and exclusions are explicit.

### D1. BIDS Sidecar Discovery Contract

- Add a small discovery layer for BIDS sidecars near uploaded EEG/event files.
- Return a structured sidecar set for `_eeg.json`, `_channels.tsv`,
  `_events.tsv`, and optional future sidecars.
- Keep missing sidecars non-fatal.
- Add unit tests with deterministic fixture files.

Acceptance:

- Existing uploads without sidecars behave exactly as before.
- Known sidecars are detected and parsed into optional metadata structures.
- Invalid sidecars produce structured diagnostics without corrupting the
  dataset record.

### D2. Dataset Metadata And Provenance Attachment

- Attach discovered sidecar metadata to dataset/recording metadata through
  optional fields.
- Record source file paths, original filenames, roles, sizes, and checksums
  where practical.
- Keep legacy JSON registry records readable.

Acceptance:

- Dataset API responses expose sidecar/provenance metadata additively.
- Existing registry tests still pass.
- New tests cover old records with missing Phase D fields.

### D3. BIDS Events Normalization Hardening

- Extend BIDS `events.tsv` normalization beyond the current row-filter MVP.
- Normalize null values consistently.
- Preserve source row and selected source columns.
- Support condition derivation from `trial_type`, `value`, or a configured
  source column.

Acceptance:

- BIDS event fixtures map into the existing EventLog model.
- API and UI previews agree on filtered row counts and event outputs.
- Existing PsychoPy and custom mapping behavior stays compatible.

### D4. Diagnostic Warning Taxonomy

- Define shared warning codes and severities for BIDS, event mapping,
  validation, workers, artifacts, export, and batch.
- Convert the most important new Phase D warning paths to structured
  diagnostics.
- Keep legacy `warnings: list[str]` for compatibility.

Acceptance:

- New diagnostics have `code`, `severity`, `source`, `impact`, and
  `suggested_action`.
- UI warning rendering continues to prefer structured diagnostics.
- Existing warning tests still pass.

### D5. Public Dataset Smoke Fixtures

- Add or document two opt-in public dataset smoke workflows:
  PhysioNet EEGMMI and one BIDS/OpenNeuro-style sample.
- Keep downloaded data under ignored `data/` paths.
- Add snapshot expectations for warnings and metadata where feasible.

Acceptance:

- Smoke docs/scripts do not require committing public EEG data.
- A maintainer can reproduce ingest -> preprocessing -> epoch -> ERP ->
  comparison for both samples.
- Expected warnings are documented instead of treated as unexplained noise.

Status: complete. See `docs/public-data-smoke-fixtures.md`,
`docs/public-demo-physionet-eegmmi.md`, and
`docs/public-demo-openneuro-bids.md`.

### D6. QC And Export Review Polish

- Make the QC dashboard and export flow surface Phase D provenance, sidecar,
  and structured diagnostic details.
- Ensure export bundles include the new provenance/sidecar metadata when present.
- Preserve existing bundle structure.

Acceptance:

- Completed ERP runs export a ZIP with analysis report, manifest, diagnostics,
  provenance, figures, and artifacts.
- Batch-created runs retain batch context in QC/report/export.
- Missing optional metadata creates warnings, not hard failures.

Status: complete. QC summaries now expose Phase D context, and export bundles
include `diagnostics/phase_d_metadata.json` alongside structured optional
metadata warnings.

### D7. Phase D Exit Gate

- Run the full Python test gate, web build, and `npm.cmd run e2e:all`.
- Run or document the two public dataset smoke workflows.
- Update user guides and the local release checklist.

Acceptance:

- Regression gate passes.
- Public data smoke result is recorded with exact command/date.
- Remaining work is explicitly moved to Phase E or later.

Status: complete. See `docs/phase-d-exit-report.md`.

Recorded D7 results:

- `.\apps\api\.venv\Scripts\python.exe -m pytest --basetemp=data\cache\pytest-full-d7-final`:
  271 passed.
- `npm.cmd run build` in `apps/web`: passed.
- `npm.cmd run e2e:all` in `apps/web`: passed.
- PhysioNet EEGMMI S001R03 prepare smoke recorded with 30 manifest events.
- OpenNeuro/BIDS-style opt-in smoke contract and expected warning snapshot
  recorded.
- Phase E-or-later carryover is listed in the exit report.
