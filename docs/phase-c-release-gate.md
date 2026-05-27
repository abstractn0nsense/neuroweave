# Phase C Release Gate

Recorded on 2026-05-28 before starting Phase C template and batch work.

Baseline:

- Branch checked: `main`
- Baseline commit: `556fd56`
- Working tree: clean before C0 documentation
- Purpose: freeze the pre-Phase-C smoke result, confirm the Phase B artifact
  contract, and list migration/compatibility constraints before adding workflow
  templates and batch execution.

## Gate Commands

Run from the repository root unless the command changes directory.

```powershell
git status --short --branch
```

Expected:

```text
## main...origin/main
```

Python test gate:

```powershell
.\apps\api\.venv\Scripts\python.exe -m pytest --basetemp=data\cache\pytest
```

Expected result:

```text
203 passed
```

Operational note: plain `pytest` can fail on this Windows machine when pytest
tries to create temporary directories under the default user temp location.
Use the repository-local `--basetemp=data\cache\pytest` path for Phase C gates.

Web build gate:

```powershell
cd apps\web
npm.cmd run build
```

Expected result:

```text
tsc --noEmit && vite build
```

The build must complete successfully. Use `npm.cmd` from PowerShell because
`npm.ps1` may be blocked by the local execution policy.

Browser smoke gate:

```powershell
cd apps\web
npm.cmd run e2e:all
```

Expected result:

```text
Phase 2 preprocessing smoke: 1 passed
Phase 3 epoch smoke: 1 passed
Phase 3 ERP smoke: 1 passed
```

## C0 Result Snapshot

The Phase C gate passed on 2026-05-28 with these local results:

| Area | Result | Notes |
| --- | --- | --- |
| Git state | Pass | `main...origin/main`, clean before C0 documentation. |
| Python tests | Pass | `203 passed` with `--basetemp=data\cache\pytest`. |
| Web build | Pass | TypeScript check and Vite production build completed. |
| Browser smoke | Pass | Phase 2 preprocessing, Phase 3 epoch, and Phase 3 ERP smokes passed sequentially. |

## Phase B Artifact Contract

Phase C can assume completed preprocessing runs expose the Phase B diagnostics
through both QC summary and artifact manifest paths.

Required preprocessing diagnostic artifacts:

- `bad_channel_report.json`
- `artifact_rejection_report.json`
- `ica_report.json`
- `before_after_qc.json`
- `artifact_summary.json`
- `filter_report.json`
- `preprocessing_summary.json`
- `artifact_manifest.json`

Required manifest logical names for Phase B diagnostics:

- `bad_channel_report`
- `artifact_rejection_report`
- `ica_report`
- `before_after_qc`

Gate coverage:

- `apps/web/e2e/phase2-smoke.spec.ts` asserts `phase_b_artifacts` in the QC
  summary response.
- `apps/web/e2e/phase2-smoke.spec.ts` asserts the artifact-integrity endpoint
  includes the Phase B logical names.
- `apps/web/e2e/phase2-smoke.spec.ts` verifies the completed preprocessing run
  can be exported as a ZIP.
- `tests/test_api_preprocessing.py` covers standalone diagnostic artifact writes,
  manifest registration, artifact integrity, export bundle inclusion, and
  analysis-report QC summary integration.

Phase C must preserve this contract when templates create or apply preprocessing
configs and when batch runs execute preprocessing for multiple datasets.

## Existing Run Schema Touchpoints

Phase C template and batch work will touch these persisted run shapes.

### Run Envelope

Persisted under `data/runs/{run_id}/run.json` through
`JsonRunRepository`.

Common fields:

- `run_id`
- `dataset_id`
- `run_kind`
- `schema_version`
- `status`
- `started_at_utc`
- `finished_at_utc`
- `cancel_requested_at_utc`
- `output_path`
- `output_metadata`
- `warnings`
- `errors`
- `diagnostics`
- `config`

Compatibility constraints:

- Keep existing `schema_version: 1` run records readable.
- Add new fields as optional and additive unless a migration is explicitly
  documented.
- Do not mutate completed run records when creating templates or batch snapshots.
- Batch state should be persisted as a separate model or an additive run kind only
  after repository compatibility tests exist.

### Preprocessing Config

Current fields:

- `artifact_schema_version`
- `high_pass_hz`
- `low_pass_hz`
- `notch_hz`
- `resample_hz`
- `reference`
- `manual_bad_channels`
- `bad_channel_detection`
- `bad_channel_interpolation`
- `ica`
- `artifact_handling`
- `qc`

Template policy:

- Include stable workflow parameters such as filters, resampling, reference,
  automatic bad-channel detection settings, interpolation settings, artifact
  handling flags, QC settings, and ICA method/threshold settings.
- Treat `manual_bad_channels` as subject-specific and exclude it by default.
- Treat `ica.exclude_components` as subject-specific review state and exclude it
  by default.
- Treat explicit `ica.eog_channels`, `ica.ecg_channels`,
  `artifact_handling.eog_channels`, and `artifact_handling.ecg_channels` as
  channel-layout-specific. Templates may store them only with validation against
  the target dataset channel list.
- Applying a template must reuse existing preprocessing validation so unknown
  channels, invalid frequency ordering, Nyquist violations, and unsupported
  references are rejected before queueing a run.

### Epoch Config

Current fields:

- `preprocessing_run_id`
- `condition_field`
- `tmin_seconds`
- `tmax_seconds`
- `baseline_start_seconds`
- `baseline_end_seconds`
- `reject_eeg_uv`

Template policy:

- Include condition field, epoch window, baseline, and rejection threshold.
- Do not persist a source `preprocessing_run_id` in a reusable template. Template
  application must bind to the target dataset's selected or newly-created
  preprocessing run.
- Revalidate event mapping and epoch bounds for each target dataset before
  queueing epoch work.

### ERP Config

Current fields:

- `epoch_run_id`
- `conditions`
- `picks`
- `method`
- `plot_mode`
- `plot_channel`

Template policy:

- Include ERP method, desired conditions, picks, plot mode, and plot channel only
  as reusable preferences.
- Do not persist a source `epoch_run_id` in a reusable template. Template
  application must bind to the target dataset's selected or newly-created epoch
  run.
- Revalidate requested conditions, picks, and plot channel for each target epoch
  output.

## Artifact Manifest Touchpoints

Templates and batches must not weaken existing artifact-manifest guarantees.

Current expectations:

- Completed preprocessing, epoch, and ERP runs write `artifact_manifest.json`.
- The artifact integrity endpoint validates artifact paths under the run artifact
  root.
- Export bundle creation reads the source artifact manifest and records missing
  manifest entries as structured warnings.
- Analysis report generation uses config snapshots, provenance, QC summary, and
  artifact-manifest content.

Phase C constraints:

- A template snapshot should record the config used to create a batch, but it
  must not replace the per-run config snapshot stored on each run.
- Batch summary artifacts should link to per-subject run manifests instead of
  copying or rewriting them.
- A failed item retry must create a new run id and preserve lineage to the failed
  item and error cause.
- A batch should allow `partial` completion when some subject runs fail and others
  complete with valid manifests.

## Legacy Fallback Inventory

Phase C must keep these compatibility paths intact:

- Preprocessing output:
  - New file: `raw_preprocessed_raw.fif`
  - Legacy fallback: `raw_preprocessed.fif`
- Epoch output:
  - New file: `epochs-epo.fif`
  - Legacy fallback: `epochs.fif`
- ERP evoked output:
  - New file shape: `evoked_{condition}-ave.fif`
  - Legacy fallback: `evoked_{condition}.fif`
- Duplicate uploaded raw FIF names preserve the MNE raw suffix, for example
  `sample_resting-1_raw.fif`.

Template and batch code must resolve completed-run inputs through the same
backend helpers that already know these fallbacks. Do not hard-code only the new
filenames in Phase C batch planning or retry logic.

## Migration And Compatibility Checklist

Before merging each Phase C slice:

- Run the C0 gate commands listed above.
- Confirm legacy preprocessing, epoch, and ERP run JSON can still be loaded.
- Confirm missing Phase B preprocessing config fields still default safely.
- Confirm template persistence tolerates unknown future keys as additive metadata.
- Confirm applying a template validates against the target dataset, not only the
  source run that created the template.
- Confirm subject-specific fields are excluded by default:
  - `manual_bad_channels`
  - `ica.exclude_components`
  - source `preprocessing_run_id`
  - source `epoch_run_id`
- Confirm ICA exclusions are either omitted or marked `requires_review` before
  use.
- Confirm batch snapshots are immutable after batch creation.
- Confirm per-subject failures do not alter successful item manifests.
- Confirm retry creates a new run id and preserves the previous failure reason.
- Confirm cancellation state is persisted and queryable.
- Confirm export/report/QC paths still work for individual runs after batch
  integration.

## Phase C Entry Decision

Phase C is cleared to start after C0 because:

- The current mainline smoke and regression gates pass.
- Phase B diagnostic artifacts are exposed through QC summary, integrity, and
  export paths.
- Run schema and artifact compatibility constraints are explicit before template
  and batch persistence changes begin.
