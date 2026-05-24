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
- background run execution
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

1. Background execution is process-local.
   - FastAPI `BackgroundTasks` is fine for local MVP jobs, but it is not durable if the API process exits.

2. Running cancellation is best-effort.
   - MNE processing is not interrupted mid-call. A running job is marked `cancelling` and becomes `cancelled` at the next checkpoint.

3. Run metadata is JSON-backed.
   - JSON files are simple and inspectable, but concurrent writes and large run histories will eventually need a stronger persistence layer.

4. Output artifacts are limited to preprocessed FIF.
   - There are no diagnostic plots, filter reports, or artifact summaries yet.

5. UI coverage is build-level only.
   - TypeScript build catches regressions, but there is no browser E2E test for the full upload-to-preprocessing workflow.

## Resolution Pipeline

Recommended next hardening path:

1. Add a durable job runner.
   - Introduce a small local worker process or queue abstraction.
   - Keep the API run endpoints stable.
   - Move MNE execution out of FastAPI `BackgroundTasks`.

2. Improve cancellation.
   - Add explicit processing checkpoints around read, filter, notch, reference, resample, and save steps.
   - Store `cancel_requested_at_utc`.
   - For long-term use, run jobs in cancellable worker subprocesses.

3. Strengthen persistence.
   - Add file locking for JSON writes as a short-term fix.
   - Move run/dataset registries to SQLite when multi-run concurrency becomes common.

4. Add diagnostic outputs.
   - Store preprocessing summaries alongside `raw_preprocessed.fif`.
   - Add filter settings, before/after sampling metadata, warning summaries, and optional HTML diagnostics.

5. Add browser E2E smoke coverage.
   - Use a small fixture flow: create project, create experiment, create dataset, upload EEG/events, validate, start preprocessing, observe completed run.
   - Run it locally before release and later in CI if runtime cost is acceptable.

## Recommendation

Merge Phase 2 after CI is green and the PR is marked ready for review. The remaining risks are known hardening items rather than blockers for the Phase 2 MVP.
