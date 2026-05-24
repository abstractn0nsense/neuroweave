# Phase 3 Roadmap

Phase 3 turns completed preprocessing output into analysis-ready epochs, then adds the
first ERP artifacts and browser smoke coverage. The main design constraint is that
run state, artifact paths, and diagnostic JSON should stay stable enough for later
ERP, comparison, export, and Phase 4 statistics work.

Current Phase 3 has two active goals:

1. Build a stable analysis pipeline from completed preprocessing runs through
   epochs, ERP artifacts, and comparison-ready summaries.
2. Move the web UI away from the current soft card-heavy style toward a denser
   research-tool workbench with rectangular surfaces, dark/light theme support,
   and analysis-first controls.

These goals should be implemented together. The UI refresh should establish the
visual system before adding epoch and ERP controls, and the analysis pipeline should
stabilize run/artifact contracts before adding more worker types.

## Phase 3 Split

### Phase 3 Early: Epoching Foundation

Scope: Phase 3.0 through Phase 3.3.

Goal: freeze the epoching contract and shared stability rules before MNE execution
becomes user-facing.

Deliverables:

- run schema and artifact metadata hardening for new analysis runs.
- `EpochConfig`, `EpochRun`, and `EpochRunStatus` domain models.
- JSON persistence for epoch runs under the existing run repository boundary.
- Stable output layout under `data/epochs/{dataset_id}/{run_id}/`.
- Event-to-MNE conversion helpers with deterministic condition mapping.
- Epoch config validation that rejects invalid windows, baselines, event fields,
  rejection thresholds, and out-of-bounds event windows.
- API endpoints for creating and listing epoch runs.
- API gate that allows epoching only from completed preprocessing runs.
- first pass of UI theme tokens if frontend work starts in this phase.

Exit criteria:

- Unit tests cover domain serialization, repository persistence, event conversion,
  validation, and API failure modes.
- `POST /datasets/{id}/epoch-runs` creates a persisted `pending` run and returns
  immediately.
- No MNE epoch execution is required yet, but the run and artifact contract must be
  compatible with Phase 3.4.
- No new analysis response shape depends on temporary filesystem assumptions.

### Phase 3 Middle: Epoch Execution And Controls

Scope: Phase 3.4 through Phase 3.6.

Goal: run epoching through MNE, persist diagnostics, and expose controls inside the
research-tool UI shell.

Deliverables:

- Load `raw_preprocessed.fif` from a completed preprocessing run.
- Generate MNE events and event IDs from normalized events.
- Execute `mne.Epochs`.
- Save `epochs.fif`.
- Save `epoch_summary.json` and `condition_counts.json`.
- Persist rejection and drop-log summaries.
- Add UI controls for preprocessing-run selection, condition field selection,
  time window, baseline, rejection threshold, status polling, and condition counts.
- Convert the existing UI surface to rectangular panels, dense metadata tables,
  neutral dark/light tokens, and a persistent theme toggle.

Exit criteria:

- A valid dataset with one completed preprocessing run can produce a completed epoch
  run from the API and from the browser UI.
- Failed epoch runs remain queryable with warnings and errors.
- Existing Phase 2 preprocessing smoke still passes unchanged.
- Browser checks cover both dark and light themes at desktop and mobile widths.

### Phase 3 Late: ERP MVP, Plots, Comparison Prep, E2E

Scope: Phase 3.7 through Phase 3.10.

Goal: produce the first queryable ERP artifacts without committing to Phase 4
statistics yet.

Deliverables:

- Condition-level averaged evoked FIF files: `evoked_{condition}.fif`.
- ERP metadata JSON with channel/time summaries.
- PNG/SVG plot artifacts and UI preview.
- Plot failure isolation: ERP or epoch runs stay queryable even if plotting fails.
- Condition-pair and mean-amplitude-window configuration for later comparisons.
- Browser E2E smoke extension:
  - keep the Phase 2 upload-to-preprocessing smoke;
  - add preprocessing-complete to epoch-complete coverage;
  - keep ERP preview as a separate smoke path.

Exit criteria:

- ERP artifacts are deterministic for fixture data.
- Plot/export failure does not corrupt run status or hide completed analysis
  metadata.
- Phase 4 can add statistical tests by reading existing comparison config and
  summary JSON instead of changing epoch/ERP contracts.
- The UI presents the workflow as a research analysis console, not a landing-page
  or generic assistant-style interface.

## Phase 3 Stability Upgrade Pipeline

Purpose: strengthen the run/artifact foundation before Phase 3 adds epoch, ERP, and
comparison outputs. These upgrades should be done before or alongside Phase 3.0 so
later phases can be additive instead of corrective.

### S1 Run Schema Versioning

Implementation steps:

1. Add a lightweight schema marker for new analysis runs.
   - `run_kind`: `preprocessing`, `epoch`, `erp`, or future values.
   - `schema_version`: start new Phase 3 run records at `1`.
   - Keep existing preprocessing records readable even if they do not have these
     fields.

2. Update repository loaders defensively.
   - Missing `run_kind` on old preprocessing records should be treated as
     `preprocessing`.
   - Missing optional fields should use safe defaults.
   - Unknown future metadata keys should be preserved by not round-tripping through
     lossy shapes where possible.

3. Add tests.
   - Old preprocessing `run.json` fixtures still load.
   - New epoch run JSON includes `run_kind` and `schema_version`.
   - Unknown metadata fields do not break listing.

### S2 Artifact Metadata Contract

Implementation steps:

1. Standardize compact artifact metadata in `output_metadata`.
   - `artifact_root`
   - `primary_artifact_path`
   - `primary_artifact_size_bytes`
   - `primary_artifact_checksum_sha256`
   - `diagnostics_directory`
   - `artifact_count`

2. Add an optional `artifact_manifest.json` for completed analysis runs.
   - Store one entry per file.
   - Include logical name, path, media type or artifact type, size, checksum, and
     created timestamp.
   - Do not require older preprocessing runs to have a manifest.

3. Write metadata only for files that exist.
   - Planned paths can live in config or local variables.
   - Completed metadata should not claim checksum or size for missing files.

4. Add tests.
   - Completed runs have correct file metadata.
   - Failed runs remain queryable without fake artifact metadata.
   - Manifest paths cannot point outside the run artifact directory.

### S3 Output Root Configuration

Implementation steps:

1. Add dedicated output root environment variables.
   - `NEUROWEAVE_EPOCHS_DIR`
   - `NEUROWEAVE_ERP_DIR`

2. Keep default local paths stable.
   - epochs: `data/epochs/{dataset_id}/{run_id}/`
   - ERP: `data/erp/{dataset_id}/{run_id}/`

3. Use path helper functions in the API.
   - Avoid building output paths inline in route handlers.
   - Ensure path helpers are testable with temporary directories.

4. Add tests.
   - Env overrides are respected.
   - Default paths match the documented artifact layout.

### S4 Atomic Artifact Publishing

Implementation steps:

1. Prefer writing analysis artifacts into a temporary run directory first.
   - Example: `data/epochs/{dataset_id}/.{run_id}.tmp/`.
   - Promote to the final run directory only after primary output and diagnostics
     are complete.

2. If an MNE writer cannot atomically write the final file, clean up partial files
   on failure.

3. Persist run status after artifact publishing.
   - `completed` should mean metadata and files agree.
   - `failed` should keep warnings/errors even if partial files were removed.

4. Add tests.
   - Simulated writer failure does not leave a completed run.
   - Partial temp directories are cleaned or clearly ignored by run listing.

### S5 Shared Worker Lifecycle Helpers

Implementation steps:

1. Extract only small lifecycle helpers at first.
   - terminal status checks
   - cancellation requested checks
   - warning deduplication
   - subprocess result validation

2. Do not introduce a full workflow engine in Phase 3 unless duplication becomes
   unmanageable.

3. Keep preprocessing behavior unchanged.
   - Any helper extraction must be covered by existing preprocessing tests.
   - Epoch/ERP workers can copy the Phase 2 shape until a shared abstraction is
     clearly safer.

4. Add tests.
   - pending/running recovery works per run type.
   - terminal runs are not re-executed.
   - cancellation state is preserved.

### S6 Stability Exit Gate

Run before closing the early foundation work:

```text
python -m pytest -p no:cacheprovider --basetemp .\data\cache\pytest
npm.cmd run build
git diff --check
```

Add a browser smoke only if frontend files were changed during the stability work.

## Phase 3 Early Detailed Pipeline

### 3.0 Epoching Contract Freeze

Purpose: define durable API, storage, and artifact contracts before adding MNE
execution.

Status: implemented for domain models and JSON run persistence.

Implementation steps:

1. Add domain models in `packages/eeg-core/src/eeg_core/domain/ingestion.py`.
   - `EpochRunStatus`: `pending`, `running`, `cancelling`, `cancelled`,
     `completed`, `failed`.
   - `EpochConfig`:
     - `preprocessing_run_id: str`
     - `condition_field: str`
     - `tmin_seconds: float`
     - `tmax_seconds: float`
     - `baseline_start_seconds: float | None`
     - `baseline_end_seconds: float | None`
     - `reject_eeg_uv: float | None`
   - `EpochRun`:
     - `run_id`
     - `dataset_id`
     - `config`
     - `status`
     - `started_at_utc`
     - `finished_at_utc`
     - `cancel_requested_at_utc`
     - `output_path`
     - `output_metadata`
     - `warnings`
     - `errors`

2. Export the models from `packages/eeg-core/src/eeg_core/domain/__init__.py`.

3. Extend `JsonRunRepository` instead of creating a second persistence style.
   - Add `save_epoch_run`.
   - Add `get_epoch_run`.
   - Add `list_epoch_runs(dataset_id: str | None = None)`.
   - Keep run metadata in `data/runs/{run_id}/run.json`, matching
     preprocessing.
   - Keep binary epoch output in `data/epochs/{dataset_id}/{run_id}/`.
   - Use `run_kind` to keep preprocessing and epoch listings separate even though
     the state files share the same run root.

4. Use stable artifact names from the start.
   - `epochs.fif`
   - `epoch_summary.json`
   - `condition_counts.json`
   - Later Phase 3 middle may add `drop_log.json`, but the first three names are
     reserved now.

5. Use a distinct run ID prefix.
   - `epoch-{uuid}` for epoch runs.
   - Keep preprocessing IDs unchanged.

6. Add persistence tests.
   - Round-trip `EpochConfig` and `EpochRun`.
   - List all epoch runs.
   - List epoch runs by dataset.
   - Ensure preprocessing run persistence remains backward-compatible.

Contract notes:

- Do not store MNE-specific event arrays in `run.json`; keep them in diagnostic
  artifact JSON later.
- `EpochConfig.condition_field` should use normalized event field names, not raw CSV
  column names.
- `output_metadata` should contain compact provenance and paths, not large
  condition/drop logs.

### 3.1 Event-To-MNE Conversion

Purpose: convert normalized event logs into deterministic MNE inputs independent of
the API layer.

Status: implemented as pure event conversion helpers in `eeg_processing.epoching`.

Implementation steps:

1. Add an epoching module in `packages/eeg-processing/src/eeg_processing/epoching.py`.

2. Define a conversion helper with a small, testable return shape.
   - Input:
     - `events: list[NormalizedEvent]`
     - `condition_field: str`
     - `sampling_rate_hz: float`
   - Output:
     - MNE events array-compatible rows: sample index, previous value `0`,
       event ID.
     - `event_id: dict[str, int]`.
     - condition counts.
     - skipped-event summary.

3. Supported condition fields for Phase 3 early:
   - `trial_type`
   - `stimulus`
   - `response`
   - `correct`

4. Normalize labels deterministically.
   - Convert values to strings.
   - Trim whitespace.
   - Treat empty strings and `None` as invalid.
   - For booleans, use lowercase labels: `true`, `false`.
   - Assign integer IDs from sorted unique labels, starting at `1`.

5. Convert onset seconds to sample indices.
   - `sample = round(onset_seconds * sampling_rate_hz)`.
   - Reject negative onset values.
   - Keep duplicate sample indices valid unless MNE execution later rejects them;
     record counts, not artificial deduplication.

6. Add event conversion tests.
   - Happy path with two conditions.
   - Empty/missing condition labels are skipped.
   - Unknown condition field fails before worker execution.
   - Boolean condition values map deterministically.
   - No valid events returns an explicit validation/conversion error.

Contract notes:

- The helper should not read files or know about datasets.
- The helper should not import FastAPI.
- MNE imports can be avoided here by returning plain Python data and letting Phase
  3.4 convert to a NumPy array at execution time.

### 3.2 Epoch Config Validation

Purpose: reject bad epoch requests before a worker run is queued.

Implementation steps:

1. Add API-level validation helper near the preprocessing validation helper first.
   It can move into a domain validation module later if it grows.

2. Validate the selected dataset and input preprocessing run.
   - Dataset must exist.
   - Dataset should still be `valid`.
   - Event log must exist and contain normalized events.
   - Referenced preprocessing run must exist.
   - Referenced preprocessing run must belong to the same dataset.
   - Referenced preprocessing run must be `completed`.
   - Referenced preprocessing run must have an existing output file path.

3. Validate time-window fields.
   - `tmin_seconds < tmax_seconds`.
   - `tmin_seconds` can be negative.
   - `tmax_seconds` should be positive.
   - Epoch duration should be greater than zero.

4. Validate baseline.
   - Both baseline bounds may be `None` for no baseline.
   - If one baseline bound is set, both should be set.
   - `baseline_start_seconds <= baseline_end_seconds`.
   - Baseline range must be inside `[tmin_seconds, tmax_seconds]`.

5. Validate condition field.
   - Must be one of the supported normalized event fields.
   - At least one event must have a non-empty value for the selected field.

6. Validate rejection threshold.
   - `reject_eeg_uv` may be `None`.
   - If set, it must be greater than `0`.
   - Store the API value in microvolts for usability.
   - Convert to volts only inside MNE execution in Phase 3.4.

7. Validate sampling and recording bounds.
   - Use preprocessing output metadata sampling rate and duration when present.
   - Fall back to recording metadata only if output metadata is missing.
   - For each valid condition event, require:
     - `onset_seconds + tmin_seconds >= 0`
     - `onset_seconds + tmax_seconds <= output_duration_seconds`
   - If some events are out of bounds, allow the request only if at least one event
     remains valid, and persist a warning on the pending run.
   - If all candidate events are out of bounds, reject the request.

8. Add validation tests.
   - Reject missing preprocessing run.
   - Reject preprocessing run from another dataset.
   - Reject non-completed preprocessing run.
   - Reject invalid time window and invalid baseline.
   - Reject unknown condition field.
   - Reject no usable conditions.
   - Reject all events out of bounds.
   - Warn, but allow, partially out-of-bounds events.

Contract notes:

- Use `422` for invalid config/request semantics.
- Use `404` only for missing dataset or missing referenced run.
- Keep validation messages explicit and stable enough for UI display.

### 3.3 Epoch Run API And Queue Contract

Purpose: expose epoching as a first-class run type while reusing the Phase 2 worker
shape.

Implementation steps:

1. Add Pydantic models in `apps/api/main.py`.
   - `EpochConfigPayload`
   - `EpochRunResponse`
   - `EpochRunsResponse`

2. Add endpoints.
   - `POST /datasets/{dataset_id}/epoch-runs`
   - `GET /epoch-runs/{run_id}`
   - `GET /datasets/{dataset_id}/epoch-runs`

3. Create epoch output directory on request creation.
   - `data/epochs/{dataset_id}/{run_id}/`
   - `output_path` should be `.../epochs.fif`.
   - Store `epoch_summary_path` and `condition_counts_path` in
     `output_metadata` as planned paths only after Phase 3.4 writes them, or omit
     them until completed. Avoid claiming files exist before they do.

4. Persist pending runs before enqueueing.
   - Match preprocessing behavior: API writes `pending`, then queues only the run
     ID.
   - For Phase 3 early, the worker may be a placeholder that marks unsupported
     execution as failed only if called. Prefer not to enqueue until Phase 3.4 if
     execution is not implemented.

5. Decide worker introduction timing.
   - Phase 3.3 should include a `LocalEpochWorker` class skeleton only if Phase
     3.4 is implemented immediately after.
   - If Phase 3.3 lands alone, keep runs queryable as `pending` and document that
     execution begins in Phase 3.4.
   - Do not share one queue implementation by stringly-typed run kind yet unless
     duplication becomes painful; preserving preprocessing stability matters more.

6. Add API tests.
   - Create epoch run from completed preprocessing run.
   - Get epoch run by ID.
   - List epoch runs by dataset.
   - Reject epoch run when preprocessing has not completed.
   - Reject epoch run for invalid condition config.
   - Ensure failed validation does not write a run.

7. Update docs and README only with stable user-facing API shape.
   - Do not document unimplemented UI controls yet.

Exit gate for Phase 3 early:

```text
python -m pytest -p no:cacheprovider --basetemp .\data\cache\pytest
npm.cmd run build
git diff --check
```

Browser E2E is not required for Phase 3 early unless API changes accidentally break
the existing Phase 2 UI path. If frontend code is touched, run the Phase 2 smoke
before closing the early phase.

## Phase 3 Middle Detailed Pipeline

### 3.4 MNE Epoch Execution

Purpose: turn a validated epoch run into an actual `epochs.fif` artifact while
preserving the same durable worker behavior as preprocessing.

Implementation steps:

1. Add epoch execution code to `packages/eeg-processing/src/eeg_processing/epoching.py`.
   - Keep pure event conversion helpers from Phase 3.1 in the same module or a
     small sibling module.
   - Add `epoch_preprocessed_eeg(input_path, output_path, event_log, config)`.
   - Return compact metadata and diagnostics payloads; do not write API run state
     from inside the processing package.

2. Read the preprocessed FIF.
   - Use `mne.io.read_raw_fif(..., preload=True, verbose=False)`.
   - Treat missing or unreadable input as an epoching failure, not as a missing
     dataset failure, because the run already exists.
   - Record `input_preprocessing_run_id`, input path, sampling rate, channel count,
     duration, and MNE version in returned metadata.

3. Build events and event IDs.
   - Convert normalized events using the Phase 3.1 helper.
   - Convert plain rows to a NumPy integer array inside the MNE execution function.
   - Preserve `event_id` as JSON metadata and diagnostic output.
   - Skip invalid labels and out-of-window events with warnings when at least one
     event remains usable.

4. Build `mne.Epochs` arguments from `EpochConfig`.
   - `tmin=config.tmin_seconds`.
   - `tmax=config.tmax_seconds`.
   - `baseline=None` when both baseline bounds are `None`.
   - Otherwise `baseline=(baseline_start_seconds, baseline_end_seconds)`.
   - Convert `reject_eeg_uv` to volts as `{"eeg": reject_eeg_uv * 1e-6}`.
   - Use `preload=True`.
   - Use `event_repeated="merge"` only if duplicate event samples become a fixture
     problem; default should stay conservative until needed.

5. Save artifacts.
   - Save epochs to `data/epochs/{dataset_id}/{run_id}/epochs.fif`.
   - Write `epoch_summary.json`.
   - Write `condition_counts.json`.
   - Add `drop_log.json` in this phase if drop reasons are not too large for the
     fixture data; otherwise summarize drop reasons in `epoch_summary.json` and
     defer full logs.

6. Return execution metadata.
   - `output_path`
   - `output_size_bytes`
   - `output_checksum_sha256`
   - `output_file_format`
   - `mne_version`
   - `input_preprocessing_run_id`
   - `condition_count`
   - `event_count_total`
   - `event_count_used`
   - `event_count_skipped`
   - `epoch_count`
   - `dropped_epoch_count`
   - `epoch_summary_path`
   - `condition_counts_path`
   - `drop_log_path` when written

7. Add subprocess execution.
   - Add `run_epoching_job` beside `run_preprocessing_job` or in a new worker
     module.
   - Use the same spawn-process and result-queue pattern as preprocessing.
   - Return `{"status": "completed", "metadata": ...}` or
     `{"status": "failed", "error": ..., "warnings": ...}`.

8. Add `LocalEpochWorker` in `apps/api/main.py`.
   - Own a separate queue and queued-run-id set.
   - Start during FastAPI lifespan.
   - Recover `pending` and stale `running` epoch runs.
   - Mark `running`, then `completed`, `failed`, or `cancelled`.
   - Check cancellation while monitoring the subprocess, matching preprocessing.

9. Add cancellation endpoint only if UI needs it in Phase 3.6.
   - Preferred endpoint: `POST /epoch-runs/{run_id}/cancel`.
   - Pending runs become `cancelled`.
   - Running runs become `cancelling` and the worker terminates the subprocess.
   - If not implemented in 3.4, explicitly defer cancellation to 3.6 and do not
     expose inactive buttons.

10. Add tests.
    - Completed epoch run writes `epochs.fif` and diagnostic JSON.
    - Failed MNE execution persists warnings and errors.
    - Worker recovers pending epoch runs.
    - Cancellation terminates a running subprocess if cancellation is included.
    - Existing preprocessing worker tests still pass.

Artifact contract for `epoch_summary.json`:

```json
{
  "run_id": "epoch-...",
  "dataset_id": "dataset-...",
  "input": {
    "preprocessing_run_id": "preprocess-...",
    "path": "data/processed/.../raw_preprocessed.fif",
    "sampling_rate_hz": 250.0,
    "duration_seconds": 120.0,
    "channel_count": 32
  },
  "config": {
    "condition_field": "trial_type",
    "tmin_seconds": -0.2,
    "tmax_seconds": 0.8,
    "baseline_start_seconds": -0.2,
    "baseline_end_seconds": 0.0,
    "reject_eeg_uv": 150.0
  },
  "events": {
    "total": 120,
    "used": 116,
    "skipped": 4,
    "event_id": {
      "target": 1,
      "standard": 2
    }
  },
  "epochs": {
    "created": 116,
    "retained": 112,
    "dropped": 4
  },
  "warnings": []
}
```

Contract notes:

- `epochs.fif` is the computational artifact. JSON files are summaries and should
  remain small enough to render quickly in the API/UI.
- Epoch execution should not mutate preprocessing runs.
- A failed epoch run should keep `output_path` as the intended `epochs.fif` path
  but should not claim checksum or file-size metadata unless the file exists.

### 3.5 Epoch Diagnostics

Purpose: make epoch results understandable and queryable without forcing the UI to
open FIF files.

Implementation steps:

1. Define a stable diagnostic JSON shape.
   - Keep `epoch_summary.json` as the single high-level summary.
   - Keep `condition_counts.json` as the direct source for UI count display.
   - Add `drop_log.json` only if needed for detailed debugging.

2. Include condition counts before and after rejection.
   - `candidate_event_count` by condition.
   - `retained_epoch_count` by condition.
   - `dropped_epoch_count` by condition when available.

3. Include drop reasons.
   - Count MNE drop-log reasons.
   - Group empty reason tuples as retained epochs.
   - Avoid storing per-epoch verbose logs in `output_metadata`.

4. Include baseline and timing summaries.
   - `tmin_seconds`
   - `tmax_seconds`
   - `epoch_duration_seconds`
   - `baseline`
   - `sampling_rate_hz`
   - `samples_per_epoch`

5. Include warnings and non-fatal skips.
   - invalid condition labels
   - out-of-bounds epoch windows
   - dropped epochs
   - baseline warnings from MNE

6. API response strategy.
   - Keep `EpochRunResponse.output_metadata` compact.
   - Add a diagnostics endpoint only if the UI needs full diagnostic JSON:
     `GET /epoch-runs/{run_id}/diagnostics`.
   - For 3.5, prefer reading count/path metadata from the run response first to
     avoid adding endpoints prematurely.

7. Add tests.
   - Condition counts JSON matches fixture event labels.
   - Drop reason summary is deterministic.
   - Diagnostics paths exist only on completed runs.
   - Failed runs remain listable and include errors.

Contract notes:

- `condition_counts.json` should be designed for UI display, not for statistics.
- Later Phase 4 statistics should read `epochs.fif` plus config/provenance, not
  infer scientific values from UI summaries.

### 3.6 UI Epoch Controls

Purpose: let the user create and monitor epoch runs without coupling the UI to
temporary backend details.

Implementation steps:

1. Extend frontend types.
   - `EpochConfig`
   - `EpochRun`
   - `EpochRunsResponse`
   - optional `EpochDiagnostics` only if a diagnostics endpoint exists.

2. Fetch completed preprocessing runs for the active dataset.
   - Reuse the existing preprocessing run list response.
   - Filter client-side to `status === "completed"`.
   - Prefer the newest completed run as default if no run is selected.

3. Add epoch form state.
   - `preprocessing_run_id`
   - `condition_field`, default `trial_type`
   - `tmin_seconds`, default `-0.2`
   - `tmax_seconds`, default `0.8`
   - `baseline_start_seconds`, default `-0.2`
   - `baseline_end_seconds`, default `0`
   - no-baseline toggle that sends both baseline values as `null`
   - `reject_eeg_uv`, default empty/null

4. Add client-side validation for obvious mistakes.
   - require completed preprocessing run
   - `tmin < tmax`
   - baseline either fully disabled or inside epoch window
   - rejection threshold greater than zero when set
   - condition field selected

5. Add controls in the dataset workflow panel.
   - Keep preprocessing controls intact.
   - Place epoch controls after preprocessing runs.
   - Do not hide preprocessing history when epoch controls appear.
   - Show disabled state with concise text when no completed preprocessing run
     exists.

6. Add run creation and polling.
   - `POST /datasets/{dataset_id}/epoch-runs`.
   - `GET /datasets/{dataset_id}/epoch-runs`.
   - Poll while any epoch run is `pending`, `running`, or `cancelling`.
   - Stop polling when all runs are terminal.

7. Display results.
   - run ID
   - status
   - selected preprocessing run
   - epoch count
   - dropped count
   - condition counts
   - warnings and errors
   - output path

8. Add cancellation UI only if backend cancellation exists.
   - Button should appear for `pending` and `running`.
   - Do not show a cancel button for epoch runs unless the endpoint exists.

9. Add frontend tests/build checks.
   - TypeScript build.
   - Existing Phase 2 smoke.
   - A manual browser check for epoch controls if E2E is deferred to 3.10.

UI contract notes:

- UI should read compact values from `output_metadata`; it should not parse FIF.
- Keep condition field options aligned with backend-supported normalized fields.
- Avoid making ERP controls visible until at least one completed epoch run exists.

Exit gate for Phase 3 middle:

```text
python -m pytest -p no:cacheprovider --basetemp .\data\cache\pytest
npm.cmd run build
git diff --check
```

If frontend controls are added, also run the browser smoke locally or document why
it was skipped.

## Phase 3 Research UI Refresh Pipeline

Purpose: redesign the web app into a focused research analysis tool before adding
more controls. The target is a dense, rectangular, dark-capable workbench where
datasets, runs, diagnostics, and plots are easy to scan.

This is a UI system change, not a marketing redesign. It should not introduce a
landing page, oversized hero area, decorative gradients, or assistant-style prompt
chrome.

### UI.1 Visual Direction

Design goals:

- Dark-first research-console feel with a complete light theme.
- Rectangular panels and controls.
- Small radius: `0px` to `4px` for core controls, maximum `6px` only where needed.
- Dense but readable spacing.
- Table-like run histories and metadata where scanning matters.
- Muted neutral palette with one restrained accent color for primary actions and
  active selections.
- Clear status colors for valid, warning, error, running, and completed states.
- No gradient or blob backgrounds.
- No pill-shaped badges unless the element is genuinely a compact tag; prefer
  square status cells or small rectangular labels.

Initial palette direction:

- Dark theme:
  - app background: near-black neutral, not saturated navy
  - panels: dark gray surfaces with visible borders
  - text: high-contrast off-white
  - muted text: cool gray
  - accent: restrained cyan/teal or blue, used sparingly
- Light theme:
  - app background: cool gray
  - panels: white or very light gray
  - text: near-black
  - borders: medium-light gray
  - accent: same hue family as dark theme

### UI.2 Theme Architecture

Implementation steps:

1. Add CSS custom properties in `apps/web/src/styles.css`.
   - semantic tokens:
     - `--color-bg`
     - `--color-surface`
     - `--color-surface-raised`
     - `--color-border`
     - `--color-text`
     - `--color-muted`
     - `--color-accent`
     - `--color-accent-strong`
     - `--color-danger`
     - `--color-warning`
     - `--color-success`
   - sizing tokens:
     - `--radius-control`
     - `--radius-panel`
     - `--space-1` through `--space-6`

2. Add theme selectors.
   - `:root[data-theme="dark"]`
   - `:root[data-theme="light"]`
   - Default to `prefers-color-scheme` only when the user has not chosen a theme.

3. Persist user choice.
   - Store `neuroweave-theme` in `localStorage`.
   - Apply the selected theme before the first full render if practical.
   - Add a header theme toggle with clear labels: `Dark` and `Light`.

4. Replace hard-coded colors incrementally.
   - First convert global surfaces, text, borders, buttons, inputs.
   - Then convert workflow-specific panels and run rows.
   - Keep behavior unchanged during the token migration.

5. Add checks.
   - `npm.cmd run build`
   - manual browser check in dark and light mode
   - verify text contrast and disabled states

### UI.3 Layout Direction

Implementation steps:

1. Keep the first screen as the usable app, not a landing page.

2. Change the shell into a research workbench.
   - Top bar:
     - product name
     - active project/dataset context
     - API health
     - theme toggle
   - Left column:
     - project, experiment, dataset selection and creation
     - compact dataset status list
   - Main workspace:
     - upload/mapping/validation
     - preprocessing
     - epoching
     - ERP and comparison when available
   - Right or lower inspector area only if needed:
     - selected run details
     - warnings/errors
     - artifact paths

3. Reduce nested card feel.
   - Use full-width work sections inside the main workspace.
   - Use bordered rectangular panels for tools.
   - Avoid card inside card styling.
   - Prefer tables/grids for repeated records.

4. Establish stable dimensions.
   - Fixed-height status strip cells.
   - Stable form grid columns.
   - Run rows should not jump when status changes.
   - Plot preview areas should have explicit aspect ratios.

5. Add responsive behavior.
   - Desktop: left navigation plus main workbench.
   - Tablet/mobile: stacked sections, no horizontal overflow.
   - Theme toggle and active dataset context stay visible.

### UI.4 Component Restyle

Implementation steps:

1. Buttons.
   - Rectangular, `2px` to `4px` radius.
   - Primary action filled with accent.
   - Secondary action transparent or surface-colored with border.
   - Destructive/cancel actions use danger border/text unless actively destructive.

2. Inputs and selects.
   - Dark-compatible surfaces.
   - Strong focus ring.
   - Consistent height.
   - Avoid rounded pill styling.

3. Status tiles and badges.
   - Replace rounded status pills with rectangular status cells.
   - Use compact uppercase status text only where useful for scanning.
   - Keep warning/error text readable in both themes.

4. Run histories.
   - Move toward table-like rows:
     - run ID
     - type
     - status
     - source run
     - key metrics
     - started/finished
     - actions
   - Keep warnings/errors expandable or visually separated.

5. Data previews.
   - CSV preview should look like a data grid.
   - Metadata should use definition grids or tables.
   - Channel lists can remain compact tags, but with rectangular tag style.

6. Analysis controls.
   - Preprocessing, epoching, and ERP controls should share a consistent form
     pattern.
   - Numeric fields should show units in labels.
   - Binary options should use toggles or checkboxes.
   - Condition and channel selections should use selects until the lists become too
     long.

### UI.5 Workflow UX For Phase 3

Implementation steps:

1. Keep ingestion and preprocessing visible as the foundation.
   - Do not bury preprocessing history when epoch controls are added.
   - Completed preprocessing runs are the selectable source for epoching.

2. Add a clear analysis progression.
   - Dataset validation
   - Preprocessing
   - Epoching
   - ERP
   - Comparison prep

3. Each analysis section should have the same shape.
   - source selector
   - config controls
   - start action
   - run table
   - warnings/errors
   - artifact summary

4. Keep unavailable steps disabled, not hidden.
   - Epoching disabled until a completed preprocessing run exists.
   - ERP disabled until a completed epoch run exists.
   - Comparison disabled until an ERP run has at least two conditions.

5. Avoid explanatory in-app text overload.
   - Use concise labels and status messages.
   - Put detailed docs in markdown, not inside the UI.

### UI.6 Implementation Order

Recommended order:

1. Theme token migration.
   - Add dark/light variables.
   - Add theme state and toggle.
   - Convert global colors and controls.
   - No workflow behavior changes.

2. Research workbench layout.
   - Convert the app shell and major panels.
   - Reduce card-heavy nesting.
   - Convert repeated data to table/grid style where practical.

3. Existing workflow restyle.
   - Upload, event mapping, validation, preprocessing.
   - Preserve existing test IDs so Phase 2 E2E stays stable.

4. Add epoch controls using the new component style.
   - Do this after the visual system is stable.
   - Avoid building epoch UI in the old style and restyling it immediately after.

5. Add ERP preview and comparison controls using the same section pattern.

6. Browser verification.
   - Desktop dark.
   - Desktop light.
   - Mobile dark.
   - Mobile light.
   - Check no text overlap, no blank plot areas, and no unreadable disabled states.

### UI.7 Acceptance Criteria

Before calling the UI refresh complete:

- The app has a visible dark/light theme toggle.
- Theme choice persists across reloads.
- Existing Phase 2 workflow remains usable.
- Existing Playwright selectors still work unless intentionally updated with tests.
- UI uses rectangular panels and controls consistently.
- No page section reads as a marketing card stack.
- Run histories are denser and easier to scan than the current card rows.
- Text fits in controls and metadata cells at desktop and mobile widths.
- Dark mode and light mode both pass manual browser inspection.

Verification:

```text
npm.cmd run build
npm.cmd run e2e:phase2
git diff --check
```

After epoch/ERP UI is added, include the Phase 3 E2E checks from 3.10.

## Phase 3 Late Detailed Pipeline

### 3.7 ERP MVP

Purpose: produce deterministic condition-level evoked artifacts from completed epoch
runs while keeping ERP as a separate analysis layer.

Implementation steps:

1. Add ERP domain models only if ERP needs independent run state.
   - Preferred for MVP: create ERP artifacts from a completed epoch run and store
     paths on the epoch run only if ERP generation is synchronous and tightly
     coupled.
   - More stable option: add `ErpConfig`, `ErpRun`, and `ErpRunStatus` with a
     separate `erp-{uuid}` run ID.
   - Choose the separate run model if plotting/export or future re-generation will
     be user-triggered independently.

2. Recommended run contract.
   - `ErpConfig`:
     - `epoch_run_id: str`
     - `conditions: list[str] | None`
     - `picks: list[str] | None`
     - `method: "mean"`
   - `ErpRun` mirrors `EpochRun` fields.
   - Store run state in `data/runs/{run_id}/run.json`.
   - Store artifacts in `data/erp/{dataset_id}/{run_id}/`.

3. Add API endpoints if using a separate run.
   - `POST /datasets/{dataset_id}/erp-runs`
   - `GET /erp-runs/{run_id}`
   - `GET /datasets/{dataset_id}/erp-runs`
   - Optional: `POST /erp-runs/{run_id}/cancel` only if execution can run long.

4. Generate evoked artifacts.
   - Load `epochs.fif` from a completed epoch run.
   - Use the epoch run's `event_id` or `condition_counts.json` to determine
     available conditions.
   - For each selected condition, run `epochs[condition].average()`.
   - Save `evoked_{safe_condition}.fif`.
   - Use a deterministic safe filename transform and store the original condition
     label in metadata.

5. Write ERP metadata JSON.
   - `erp_metadata.json`
   - `condition`
   - `evoked_path`
   - `nave`
   - `channel_count`
   - `time_min_seconds`
   - `time_max_seconds`
   - `sampling_rate_hz`
   - `peak_amplitude_by_channel_uv` or a compact channel/time summary
   - `warnings`

6. Add channel/time summaries.
   - For each condition, include:
     - peak positive channel/time/amplitude
     - peak negative channel/time/amplitude
     - global field power peak time and value
   - Use microvolts in JSON summaries for readability.
   - Keep full waveform data in FIF, not JSON.

7. Add worker execution if ERP is a run type.
   - Match epoch worker pattern.
   - Recover pending/stale running ERP runs on startup.
   - Keep failures queryable.

8. Add tests.
   - Completed ERP generation writes one evoked FIF per condition.
   - Metadata contains expected condition labels and `nave`.
   - Empty condition selection defaults to all available conditions.
   - Missing or failed epoch run is rejected.
   - Failed ERP execution persists a failed run.

Contract notes:

- Do not make ERP generation part of epoch completion unless the user experience
  explicitly needs automatic ERP artifacts.
- ERP artifacts should depend on a completed epoch run, not directly on a
  preprocessing run.
- If separate ERP runs are introduced, Phase 4 should build on ERP/epoch run IDs
  instead of dataset-global latest artifacts.

### 3.8 ERP Plot And Export

Purpose: create previewable ERP plots while isolating plotting failures from
successful computational artifacts.

Implementation steps:

1. Add plot generation in the ERP processing module.
   - Input: evoked FIF path or in-memory evoked object.
   - Output:
     - `erp_{safe_condition}.png`
     - optional `erp_{safe_condition}.svg`
   - Use a non-interactive Matplotlib backend.
   - Close figures after saving.

2. Choose MVP plot mode.
   - Primary: selected channel if provided.
   - Fallback: global field power.
   - Store selected mode in `erp_metadata.json`.
   - Do not block ERP FIF creation if plot generation fails.

3. Add plot metadata.
   - `plot_png_path`
   - `plot_svg_path`
   - `plot_mode`
   - `plot_channel`
   - `plot_status`
   - `plot_warnings`

4. Add API serving strategy.
   - Prefer static artifact download endpoints over exposing raw filesystem paths
     if browser preview needs direct image loading.
   - Candidate endpoint:
     `GET /artifacts/{run_id}/{filename}` with run ownership/path validation.
   - If direct paths are used temporarily, keep them local-only and document that
     this is not the final serving model.

5. Add UI preview.
   - Show ERP run list after completed epoch runs.
   - Show condition selector when multiple plots exist.
   - Render PNG preview.
   - Show path/status metadata when preview is unavailable.

6. Add export affordance only for existing files.
   - Download/view PNG.
   - Download/view SVG if generated.
   - Do not create ZIP export in Phase 3 unless it is trivial and covered by tests.

7. Add tests.
   - Plot generation writes PNG for fixture evoked data.
   - Simulated plotting failure leaves ERP run completed with plot warning if FIF
     generation succeeded.
   - Artifact endpoint refuses path traversal if implemented.
   - UI build passes with preview types.

Contract notes:

- Computational success and visualization success are separate. A run with valid
  evoked FIF files should not become `failed` only because a PNG could not be
  created.
- Store plot warnings in metadata and run warnings, but keep errors reserved for
  failed computational artifacts.

### 3.9 Condition Comparison Prep

Purpose: prepare stable configuration and summary artifacts for Phase 4 statistics
without implementing statistical tests yet.

Implementation steps:

1. Decide whether comparison prep is tied to ERP or has its own run.
   - For MVP, add comparison config to an ERP run only if it is generated together
     with ERP artifacts.
   - Use a separate `ComparisonConfig`/`ComparisonRun` if users can trigger many
     pair/window comparisons from the same ERP output.
   - Preferred stability path: separate `comparison-{uuid}` run only when actual
     Phase 4 tests begin. In Phase 3.9, write prep JSON under the ERP run artifact
     directory.

2. Define config shape.
   - `erp_run_id`
   - `condition_a`
   - `condition_b`
   - `channel: str | None`
   - `use_gfp: bool`
   - `window_start_seconds`
   - `window_end_seconds`
   - `metric: "mean_amplitude_uv"`

3. Validate config.
   - Conditions must exist in ERP metadata.
   - Window must overlap ERP time range.
   - `window_start_seconds < window_end_seconds`.
   - Channel must exist unless `use_gfp` is true.
   - Do not allow both a channel and GFP as active metric targets.

4. Generate comparison summary JSON.
   - `comparison_summary.json`
   - condition labels
   - selected channel or GFP
   - time window
   - mean amplitude for condition A
   - mean amplitude for condition B
   - difference `A - B`
   - source ERP run ID
   - source evoked paths
   - explicit note: statistical testing is not implemented in Phase 3.

5. Add API surface.
   - Minimal option:
     `POST /erp-runs/{run_id}/comparison-summary`.
   - If separate run is used:
     `POST /datasets/{dataset_id}/comparison-runs`,
     `GET /comparison-runs/{run_id}`,
     `GET /datasets/{dataset_id}/comparison-runs`.

6. Add UI controls.
   - Show only after completed ERP run with at least two conditions.
   - Condition A selector.
   - Condition B selector.
   - Channel selector or GFP toggle.
   - Start/end window numeric inputs.
   - Display mean amplitudes and difference.
   - Display "statistics deferred" as metadata/status, not as a blocking error.

7. Add tests.
   - Valid pair/window writes summary JSON.
   - Unknown condition is rejected.
   - Invalid window is rejected.
   - Channel/GFP validation is enforced.
   - Summary values are deterministic for fixture evoked data.

Contract notes:

- Do not introduce p-values, confidence intervals, or statistical labels in Phase
  3.9.
- The Phase 3.9 summary is descriptive. Phase 4 owns inference.
- Keep metric names explicit so Phase 4 can add alternatives without renaming
  existing fields.

### 3.10 Browser E2E Expansion

Purpose: protect the complete user workflow without making one large smoke test
fragile.

Implementation steps:

1. Keep the existing Phase 2 smoke path intact.
   - Upload EEG/events.
   - Save event mapping.
   - Validate dataset.
   - Complete preprocessing.
   - Do not add ERP expectations to this smoke.

2. Add an epoch smoke.
   - Reuse fixture upload and preprocessing flow.
   - Wait for a completed preprocessing run.
   - Select that preprocessing run for epoching.
   - Use default epoch config.
   - Wait for completed epoch run.
   - Assert visible condition counts and output path.

3. Add a separate ERP smoke.
   - Start from a completed epoch run when possible.
   - Generate ERP artifacts.
   - Assert ERP metadata appears.
   - Assert preview status appears.
   - Only assert image rendering if the artifact-serving endpoint is stable.

4. Isolate E2E data.
   - Use `data/cache/phase3-e2e` or separate subdirectories:
     - `phase3-epoch-e2e`
     - `phase3-erp-e2e`
   - Set `NEUROWEAVE_UPLOADS_DIR`, `NEUROWEAVE_RUNS_DIR`,
     `NEUROWEAVE_PROCESSED_DIR`, `NEUROWEAVE_EPOCHS_DIR`, and
     `NEUROWEAVE_ERP_DIR` for tests if those env vars exist.

5. Add package scripts.
   - `npm run e2e:phase3:epoch`
   - `npm run e2e:phase3:erp`
   - Keep `npm run e2e:phase2` as-is.

6. Add CI cautiously.
   - First add epoch smoke to CI once stable locally.
   - Add ERP smoke after plot/artifact serving is not flaky.
   - Keep timeouts explicit because MNE work can be slower on CI.

7. Add E2E assertions that check behavior, not implementation details.
   - User-visible completed status.
   - Condition counts visible.
   - ERP condition summary visible.
   - Plot preview visible or plot warning visible.
   - Avoid asserting exact run IDs.

Exit gate for Phase 3 late:

```text
python -m pytest -p no:cacheprovider --basetemp .\data\cache\pytest
npm.cmd run build
npm.cmd run e2e:phase2
npm.cmd run e2e:phase3:epoch
npm.cmd run e2e:phase3:erp
git diff --check
```

If ERP plot serving remains intentionally local-only, the ERP smoke may assert
metadata and plot status instead of pixel rendering.

## Stability Rules For Later Updates

- Add new run types through repository methods, not by exposing storage paths in
  route handlers.
- Keep `data/runs/{run_id}/run.json` as the queryable state source.
- Keep analysis artifacts under type-specific roots:
  - preprocessing: `data/processed/{dataset_id}/{run_id}/`
  - epochs: `data/epochs/{dataset_id}/{run_id}/`
  - ERP: `data/erp/{dataset_id}/{run_id}/` unless Phase 3 late intentionally
    chooses a different root.
- Treat config snapshots as immutable after run creation.
- Never rewrite completed run configs during later phases; add metadata keys or new
  artifact files instead.
- Use explicit `*_path` metadata keys only for files that exist.
- Keep failure states queryable with warnings and errors.
- Keep plotting/export failures separate from successful computational artifacts.
- Prefer additive API response fields over renaming existing fields.
- Defer SQLite or a generalized workflow engine until JSON run history becomes a
  real bottleneck.
