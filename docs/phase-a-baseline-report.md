# Phase A Baseline Report

Date: 2026-05-26

Branch: `codex/fix-run-warnings-growth-pipeline`

Purpose: fix the current stability baseline before starting Phase A follow-up work.
This report records the state of the current local research MVP without applying
code fixes.

## Summary

The current NeuroWeave baseline is green for the local API/package test suite,
web production build, and Phase 2/3 browser workflow smokes.

Validated capabilities:

- web app builds successfully with TypeScript and Vite
- browser workflow can create a project, experiment, and dataset
- browser workflow can upload EEG and event files
- event mapping, dataset validation, and preprocessing complete
- epoch generation from a completed preprocessing run completes
- ERP preview and comparison summary complete
- Python API/package tests pass across ingestion, preprocessing, epoching, ERP,
  export, QC, provenance, registry, and worker CLI modules

## Commands Run

```powershell
npm.cmd run build
```

Result:

```text
passed
```

```powershell
npm.cmd run e2e:all
```

Result:

```text
passed
phase2-smoke: 1 passed
phase3-epoch-smoke: 1 passed
phase3-erp-smoke: 1 passed
```

```powershell
apps\api\.venv\Scripts\python.exe -m pytest tests -o cache_dir=data/cache/pytest-cache --basetemp data/cache/pytest-tmp
```

Result:

```text
183 passed
```

The explicit `--basetemp data/cache/pytest-tmp` argument is required on this
Windows environment because the default user temp pytest directory can be
permission-restricted.

## Baseline Status

| Area | Status | Notes |
| --- | --- | --- |
| Web build | Pass | `tsc --noEmit` and Vite production build complete. |
| Phase 2 browser workflow | Pass | Upload, mapping, validation, and preprocessing complete. |
| Phase 3 epoch workflow | Pass | Completed preprocessing output can produce completed epochs. |
| Phase 3 ERP workflow | Pass | ERP preview and comparison prep complete. |
| API/package tests | Pass | 183 tests pass with repo-local pytest temp/cache paths. |

## Known Constraints

- This baseline validates the local web/API workflow, not a packaged desktop app.
- E2E tests use local fixture EEG/event files, not a live network download.
- The public PhysioNet workflow has been manually exercised previously, but it is
  not yet part of the automated baseline.
- Statistical testing remains out of scope; current comparison prep is descriptive.
- Advanced preprocessing such as ICA, bad-channel interpolation, and visual artifact
  review is not part of this baseline.

## Recommended Next Step

Proceed to A2, upload UX improvement:

```text
Improve the Ingestion And Preprocessing upload UI for EEG Recording and Event Log.
Show supported file formats, example file paths, before/after upload state, and
clear next-step guidance. Keep the existing API shape and update E2E as needed.
```
