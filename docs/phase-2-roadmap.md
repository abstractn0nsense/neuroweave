# Phase 2 Roadmap

Phase 2 now includes the remaining app-operational work from the former Phase 1 tail plus the first preprocessing handoff.

## Phase 2.1: Click-to-Run Launcher

Goal: run NeuroWeave without typing PowerShell commands.

Implemented entrypoints:

- `Start NeuroWeave.bat`
- `scripts/start_neuroweave.ps1`
- `Stop NeuroWeave.bat`
- `scripts/stop_neuroweave.ps1`

Launcher behavior:

- create `data/logs/` when needed
- install the API virtual environment when missing
- install web dependencies when `apps/web/node_modules` is missing
- start the API server on `http://127.0.0.1:8000`
- start the web server on `http://127.0.0.1:5173`
- wait for API and web health checks
- open the browser to `http://127.0.0.1:5173`
- write logs to `data/logs/api.log` and `data/logs/web.log`
- avoid starting duplicate servers when the existing URLs already respond

## Phase 2.2: App-Like Launch Polish

Goal: make the local server and browser shape feel like a lightweight desktop app.

Implemented work:

1. `scripts/install_neuroweave_shortcut.ps1` creates Desktop and Start Menu shortcuts.
2. The shortcut uses a generated NeuroWeave `.ico` at `data/app/neuroweave.ico`.
3. Runtime API and web server windows are hidden when launched from the shortcut.
4. The browser remains the primary user-facing surface.
5. The web app has a NeuroWeave SVG favicon.
6. README and script docs include the app-like launch guide.

Electron or Tauri should wait until the web and preprocessing workflows are stable.

## Phase 2.3: Preprocessing Handoff

Goal: pass a valid dataset into actual MNE preprocessing.

Implemented core objects:

- `PreprocessingConfig`
- `PreprocessingRun`

Implemented configuration fields:

- high-pass filter
- low-pass filter
- notch filter
- resample rate
- reference

Implemented run metadata:

- run ID
- dataset ID
- status
- started and finished timestamps
- output path
- warnings and errors

Implemented API shape:

```text
POST /datasets/{id}/preprocessing-runs
GET /preprocessing-runs/{run_id}
GET /datasets/{id}/preprocessing-runs
```

Implemented storage shape:

```text
data/
  runs/
    {run_id}/
      run.json
  processed/
    {dataset_id}/
      {run_id}/
        raw_preprocessed.fif
```

Implemented UI shape:

- enable preprocessing only for valid datasets
- collect filter settings
- show run status
- show output metadata

Current scope:

- The first processing backend is MNE-based and writes FIF output.
- Runs are created as `pending`, then executed by the local preprocessing worker queue.
- The UI polls pending/running runs until they reach `completed` or `failed`.
- Failed runs are persisted with warning and error details.

## Phase 2.4: Preprocessing Config Hardening

Implemented validation:

- `high_pass_hz` must be lower than `low_pass_hz` when both are set
- filter cutoff and notch frequencies must be below the input Nyquist frequency
- `resample_hz` must not exceed the input sampling rate
- custom reference values must name existing EEG channels
- UI blocks obvious numeric and high/low ordering mistakes before sending the request
- API returns `422` with explicit validation messages for invalid preprocessing settings

## Phase 2.5: Run Provenance

Implemented provenance:

- run config is persisted as the `PreprocessingRun.config` snapshot
- input file ID, original filename, stored path, size, and checksum are stored
- input file format, channel count, sampling rate, duration, and channel names are stored
- output path, size, checksum, file format, channel count, sampling rate, and duration are stored
- MNE version is stored with the completed run metadata
- UI run summaries read the output metadata keys while remaining compatible with older run metadata

## Phase 2.6: Warning And Error Capture

Implemented capture:

- MNE/Python warnings emitted while reading, preprocessing, and saving raw data are captured
- captured warnings are persisted on completed preprocessing runs
- failed preprocessing runs persist any warnings collected before failure
- failed preprocessing runs remain queryable through dataset run listing
- UI run rows already separate warning text from error text

## Phase 2.7: Background Preprocessing Runs

Implemented execution model:

- `POST /datasets/{id}/preprocessing-runs` validates the dataset and config, saves a `pending` run, and returns immediately
- background execution updates the run to `running`, then `completed` or `failed`
- successful runs persist output metadata, provenance, and captured warnings
- failed runs persist errors, captured warnings, and input provenance
- the web UI polls preprocessing runs while any selected-dataset run is `pending` or `running`

## Phase 2.8: Cancel Preprocessing Runs

Implemented cancellation:

- `POST /preprocessing-runs/{run_id}/cancel`
- pending runs are marked `cancelled` immediately
- running runs are marked `cancelling` as a best-effort cancellation request
- background execution skips runs already marked `cancelled`
- background execution converts `cancelling` runs to `cancelled` at the next completion checkpoint
- cancellation warnings are persisted on the run
- the web UI shows Cancel buttons for `pending` and `running` runs

## Phase 2.9: Merge Readiness And Final Review

Implemented readiness work:

- local Python test suite passes
- local web build passes
- GitHub CI passes on the Phase 2 PR branch
- the Phase 2 PR is mergeable against `main`
- final review notes are recorded in `docs/phase-2-final-review.md`
- the PR is ready to move out of draft once the final review commit is uploaded

## Phase 2.0 Hardening Track

The remaining Phase 2 hardening items are tracked as `Phase 2.0.n` work. These items improve reliability without changing the core Phase 2 preprocessing API shape.

### Phase 2.0.1: Durable Local Worker Queue

Implemented worker queue:

- FastAPI `BackgroundTasks` is no longer used for preprocessing execution
- `LocalPreprocessingWorker` owns a local run queue and daemon worker thread
- `POST /datasets/{id}/preprocessing-runs` saves a `pending` run and enqueues only the run ID
- the worker loads run metadata from `JsonRunRepository` before execution
- API startup starts the worker and recovers `pending` or stale `running` runs from `data/runs`
- recovered runs keep the same run ID, config snapshot, provenance, and output path

### Phase 2.0.2: Cancellation Checkpoints

Implemented cancellation hardening:

- `PreprocessingRun.cancel_requested_at_utc` records when cancellation was requested
- cancellation timestamps persist through JSON run storage and API responses
- preprocessing checks for cancellation before and after read, filter, notch, reference, resample, and save stages
- cancellation observed at a checkpoint persists a warning on the run
- running runs that observe cancellation finish as `cancelled` instead of `failed`

### Phase 2.0.3: Cancellable Subprocess Execution

Implemented subprocess execution:

- each preprocessing run executes MNE work in a spawned child process
- the local worker thread monitors the child process while polling run cancellation state
- `cancelling` or `cancelled` status terminates the child process
- if the child process does not exit promptly, it is killed
- subprocess results are returned through a process queue and persisted by the API worker
- failed subprocesses persist warnings and errors on the run
- JSON writes use atomic temp-file replacement so status polling cannot read a partially written run file

### Phase 2.0.4: JSON Persistence Locking

Implemented JSON persistence hardening:

- JSON registry files use per-file lock files during reads and writes
- read-modify-write saves for project, experiment, participant, and uploaded-file registries run inside one lock
- lock acquisition uses a process-local reentrant lock plus an OS file lock for cross-thread and cross-process safety
- JSON writes still use atomic temp-file replacement after the lock is acquired
- concurrent project registry writes are covered by regression tests
- the existing repository boundary remains the migration point for a future SQLite backend

### Phase 2.0.5: Preprocessing Diagnostics

Implemented diagnostic outputs:

- completed runs write `preprocessing_summary.json` beside `raw_preprocessed.fif`
- completed runs write `filter_report.json` with applied, skipped, and not-requested operation statuses
- completed runs write `artifact_summary.json` with bad-channel and annotation counts
- `output_metadata` records diagnostic file paths and key artifact counts
- diagnostic JSON includes before/after sampling metadata, config snapshots, and captured warnings
- artifact rejection is explicitly reported as disabled until a later analysis phase implements it

Remaining `Phase 2.0.n` items:

- `Phase 2.0.6`: browser E2E smoke test for upload, validation, preprocessing, and completed-run display
