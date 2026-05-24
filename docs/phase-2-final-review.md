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
   - JSON files are simple and inspectable, and writes now use atomic temp-file replacement to avoid partial reads.
   - Concurrent read/write sequences and large run histories will eventually need file locks or a stronger persistence layer.

4. Output artifacts are limited to preprocessed FIF.
   - There are no diagnostic plots, filter reports, or artifact summaries yet.

5. UI coverage is build-level only.
   - TypeScript build catches regressions, but there is no browser E2E test for the full upload-to-preprocessing workflow.

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
   - Add file locking for JSON read/write sequences as a short-term fix.
   - Move run/dataset registries to SQLite when multi-run concurrency becomes common.

5. Phase 2.0.5: Add diagnostic outputs.
   - Store preprocessing summaries alongside `raw_preprocessed.fif`.
   - Add filter settings, before/after sampling metadata, warning summaries, and optional HTML diagnostics.

6. Phase 2.0.6: Add browser E2E smoke coverage.
   - Use a small fixture flow: create project, create experiment, create dataset, upload EEG/events, validate, start preprocessing, observe completed run.
   - Run it locally before release and later in CI if runtime cost is acceptable.

## Recommendation

Merge Phase 2 after CI is green and the PR is marked ready for review. The remaining risks are known hardening items rather than blockers for the Phase 2 MVP.
