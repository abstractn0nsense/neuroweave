# Phase 2 Final Review

## Status

Phase 2 is complete for the local-app and preprocessing MVP.

Implemented:

- click-to-run Windows launcher
- app-like shortcut and icon setup
- valid dataset to MNE preprocessing handoff
- preprocessing config validation
- run provenance
- warning and error capture
- local worker queue execution
- best-effort run cancellation
- UI controls for preprocessing configuration, run status, polling, and cancellation

## Verification

Local verification:

```text
python -m pytest -p no:cacheprovider --basetemp .\data\cache\pytest
npm.cmd run build
git diff --check
```

GitHub verification:

- PR branch: `codex/phase-2-launcher-polish`
- Base branch: `main`
- GitHub CI workflow: `CI / test`
- Latest observed status: passing
- PR mergeability: mergeable

## Remaining Risks

Phase 2 is suitable to merge as an MVP, but these limitations should be handled before treating NeuroWeave as a robust long-running research production tool.

1. Worker execution is still process-local.
   - Phase 2.0.1 removed FastAPI `BackgroundTasks` and recovers pending/stale running runs on API startup, but the worker still runs inside the API process.

2. Running cancellation is best-effort.
   - MNE processing is not interrupted mid-call. A running job is marked `cancelling` and becomes `cancelled` at the next checkpoint.

3. Run metadata is JSON-backed.
   - JSON files are simple and inspectable.
   - Writes use atomic temp-file replacement, and registry reads/writes now use per-file OS locks.
   - Large run histories will eventually need a stronger persistence layer.

4. Output diagnostics are JSON-only.
   - Completed runs now write preprocessing summaries, filter reports, and artifact summaries.
   - Diagnostic plots and richer artifact detection remain future analysis work.

5. UI coverage is smoke-level only.
   - TypeScript build and a browser E2E smoke cover the main upload-to-preprocessing workflow.
   - Broader browser coverage for edge cases should be added as workflows expand.

## Phase 2.0.n Resolution Pipeline

Recommended next hardening path:

1. Phase 2.0.1: Durable local worker queue.
   - Status: implemented.
   - FastAPI `BackgroundTasks` was replaced with a local queue and worker thread.
   - API startup recovers `pending` and stale `running` runs from JSON run metadata.

2. Phase 2.0.2: Improve cancellation.
   - Status: implemented for cooperative checkpoints.
   - Explicit checkpoints now run around read, filter, notch, reference, resample, and save steps.
   - `cancel_requested_at_utc` is persisted with run metadata.
   - For hard mid-MNE interruption, Phase 2.0.3 adds cancellable subprocess execution.

3. Phase 2.0.3: Add cancellable subprocess execution.
   - Status: implemented.
   - Each preprocessing run executes MNE work in a spawned child process.
   - The local worker terminates or kills the child process when cancellation is requested.

4. Phase 2.0.4: Strengthen persistence.
   - Status: implemented for JSON locking.
   - JSON registry reads/writes are protected by per-file locks.
   - List-style read-modify-write updates are serialized to avoid lost updates.
   - Move run/dataset registries to SQLite later if multi-run concurrency becomes common.

5. Phase 2.0.5: Add diagnostic outputs.
   - Status: implemented for JSON diagnostics.
   - Store preprocessing summaries alongside `raw_preprocessed.fif`.
   - Add filter settings, before/after sampling metadata, warning summaries, and artifact summaries.
   - Optional HTML diagnostics remain future polish.

6. Phase 2.0.6: Add browser E2E smoke coverage.
   - Status: implemented.
   - The smoke creates project, experiment, and dataset records through the web UI.
   - It uploads fixture EEG/events, saves event mapping, validates, starts preprocessing, and observes a completed run.
   - CI installs Chromium and runs the smoke with isolated E2E data directories.

## Recommendation

Merge Phase 2 after CI is green and the PR is marked ready for review. The remaining risks are known hardening items rather than blockers for the Phase 2 MVP.
