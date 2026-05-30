# Phase D Exit Report

Recorded on 2026-05-30 for branch `codex/phase-d-roadmap-sync` and draft PR
https://github.com/abstractn0nsense/neuroweave/pull/11.

## Exit Decision

Phase D is complete. The Phase D scope moved the existing BIDS, event mapping,
diagnostic, QC, export, and batch MVPs into a harder public-data-ready contract
without breaking the existing local upload and analysis flow.

## Regression Gate

Run from the repository root unless noted.

| Area | Command | Result |
| --- | --- | --- |
| Git status | `git status --short --branch` | `## codex/phase-d-roadmap-sync...origin/codex/phase-d-roadmap-sync` before D7 documentation edits |
| Python full test | `.\apps\api\.venv\Scripts\python.exe -m pytest --basetemp=data\cache\pytest-full-d7-final` | 271 passed |
| Web build | `npm.cmd run build` in `apps/web` | passed |
| Browser smoke | `npm.cmd run e2e:all` in `apps/web` | passed |

The Python gate emitted one non-fatal pytest cache permission warning under
`.pytest_cache` on Windows. The run used `--basetemp` under `data/cache` to keep
test temporary output inside an ignored workspace path.

Browser smoke coverage:

- Phase 2 preprocessing smoke: passed.
- Phase C batch retry smoke: passed.
- Phase 3 epoch smoke: passed.
- Phase 3 ERP smoke: passed.

## Public Dataset Smoke Results

### PhysioNet EEGMMI S001R03

Command:

```powershell
.\apps\api\.venv\Scripts\python.exe .\scripts\prepare_physionet_eegmmi_demo.py
```

Result:

- EEG recording prepared at `data/raw/public-samples/S001R03.edf`.
- Event log prepared at `data/raw/public-samples/S001R03_events.csv`.
- Smoke manifest prepared at
  `data/raw/public-samples/S001R03_neuroweave_smoke.json`.
- Manifest event count: 30.
- Expected conditions: `rest`, `left_fist`, `right_fist`.
- Comparison contract: `left_fist` versus `right_fist`, GFP target,
  `mean_amplitude_uv`, no inferential statistics.
- Expected warning snapshot:
  `tests/fixtures/public_smoke/physionet_eegmmi_s001r03_expected_warnings.json`.

The public EDF and generated local smoke manifest remain under ignored `data/`
paths and are not committed.

### OpenNeuro/BIDS-Style Sample

Result:

- Workflow is documented in `docs/public-demo-openneuro-bids.md`.
- Shared public smoke policy is documented in
  `docs/public-data-smoke-fixtures.md`.
- Expected warning snapshot:
  `tests/fixtures/public_smoke/openneuro_bids_style_expected_warnings.json`.
- The D7 Python full test includes the public smoke contract tests that verify
  both expected warning snapshots and public smoke documentation links.

The OpenNeuro/BIDS-style run is intentionally documented as an opt-in local
workflow because public dataset downloads vary by dataset size and network
availability. Real public EEG files must stay under ignored `data/` paths.

## Phase D Completion Summary

- D0 aligned the roadmap with the actual Phase C exit baseline.
- D1 promoted BIDS sidecar handling from file parsing to adjacent dataset
  discovery.
- D2 attached additive source file, sidecar, and checksum provenance metadata.
- D3 hardened BIDS event normalization, null handling, source row preservation,
  and condition derivation.
- D4 stabilized structured diagnostic warning taxonomy while preserving legacy
  `warnings: list[str]`.
- D5 documented reproducible public dataset smoke fixtures and expected warning
  snapshots.
- D6 surfaced Phase D metadata in QC summaries, the web QC dashboard, analysis
  reports, and export bundles.
- D7 recorded the exit regression gate, public smoke results, user guide updates,
  and release checklist updates.

## Moved To Phase E Or Later

- Inferential statistics, including paired/unpaired tests, permutation tests,
  effect sizes, confidence intervals, and multiple-comparison correction.
- Full reproducibility graph with one-click rerun.
- Broader public dataset CI that downloads and runs multiple large EEG datasets.
- Collaboration, project archive sharing, and immutable shareable snapshots.
- Large visual regression suite for ERP and QC views.
- Complete multi-subject batch UI beyond the Phase C foundation.
- Advanced artifact workflows such as ICA, bad-channel interpolation, and manual
  artifact review.
- Data governance polish such as explicit local data deletion and migration
  tooling between preview versions.
