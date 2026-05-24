# Warning Inventory

Captured from the local test and browser smoke runs on 2026-05-25.

Purpose: freeze the warning scope before changing artifact filenames or warning
filters. This inventory is intentionally diagnostic only; code changes should be
kept for the follow-up migration step.

## Commands

```powershell
apps\api\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .\data\cache\pytest
npm.cmd run e2e:phase2
npm.cmd run e2e:phase3:epoch
npm.cmd run e2e:phase3:erp
```

Results:

- API tests: `94 passed, 5 warnings`
- Phase 2 browser smoke: `1 passed`
- Phase 3 epoch browser smoke: `1 passed`
- Phase 3 ERP browser smoke: `1 passed`

The browser smoke output only showed expected uvicorn startup logs. No additional
runtime warning category appeared there.

## Classification Terms

- Expected invalid-file warning: emitted while intentionally exercising an invalid
  input path. The warning is useful evidence that the rejection path reached MNE.
- MNE naming warning: emitted because a FIF file does not use an MNE-recommended
  suffix. These are noisy and should be fixed by artifact naming migration, but
  they do not currently indicate corrupted data.
- Suppressed historical warning: a known warning pattern that no longer appears in
  the full pytest warning summary because it is already captured or suppressed at
  a narrow call site.
- Real-risk warning: a warning that suggests data loss, unsafe bounds, failed
  processing, or behavior that should block Phase 3 completion.

## Current Warning Inventory

| ID | Source | Warning signal | Classification | Current impact | Follow-up |
| --- | --- | --- | --- | --- | --- |
| W-001 | `tests/test_api_eeg_upload.py::test_upload_eeg_file_rejects_unreadable_eeg` via `packages/eeg-io/src/eeg_io/readers/mne_reader.py` | `not-eeg.fif` does not conform to MNE raw naming conventions | Expected invalid-file warning | Non-fatal. The test intentionally uploads an unreadable `.fif` file and expects API rejection. | Keep the test. Later, capture or filter this exact warning in the test so it does not hide new warnings. |
| W-002 | `tests/test_api_eeg_upload.py::test_upload_eeg_file_rejects_unreadable_eeg` via `packages/eeg-io/src/eeg_io/readers/mne_reader.py` | Invalid FIF tag in `not-eeg.fif` | Expected invalid-file warning | Non-fatal and expected. This is the actual invalid-file signal. | Keep as part of invalid upload coverage; use a narrow warning capture if test output needs to be clean. |
| W-003 | `tests/test_api_eeg_upload.py::test_upload_eeg_file_does_not_overwrite_existing_filename` via `packages/eeg-io/src/eeg_io/readers/mne_reader.py` | Duplicate upload path becomes `sample_resting_raw-1.fif`, which no longer ends with an MNE raw suffix | MNE naming warning | Non-fatal. Upload deconfliction preserves uniqueness but breaks the MNE suffix shape. | Change duplicate filename allocation to preserve the MNE suffix, for example `sample_resting-1_raw.fif`. |
| W-004 | `tests/test_api_epoch_execution.py::test_epoch_diagnostics_summarize_drop_reasons` | Test reads `raw_preprocessed.fif`; MNE warns that it does not end with a raw suffix | MNE naming warning | Non-fatal. It points to the current preprocessing artifact contract. | Rename the preprocessing artifact to an MNE-compliant raw name, keep legacy lookup fallback for existing runs. |
| W-005 | `tests/test_api_epoch_execution.py::test_epoch_diagnostics_summarize_drop_reasons` | Test saves `raw_preprocessed.fif`; MNE warns that it does not end with a raw suffix | MNE naming warning | Non-fatal. Same root cause as W-004. | Same migration as W-004. |
| W-006 | ERP plotting and artifact reads around `evoked_{condition}.fif` | MNE evoked naming warnings can occur because evoked files should use an evoked suffix | Suppressed historical warning | No longer appears in the current full pytest warning summary after narrow suppression around image generation. The artifact name is still not MNE-compliant. | Rename ERP evoked artifacts to `evoked_{condition}-ave.fif` or another `-ave.fif` shape; keep manifest/legacy fallback. |
| W-007 | Epoch artifact contract `epochs.fif` | MNE epoch files conventionally use `-epo.fif` | Suppressed or captured naming risk | Not present in the current pytest warning summary, but the contract is not aligned with MNE naming conventions. | Rename epoch artifacts to an `-epo.fif` shape; keep manifest/legacy fallback. |

## Real-Risk Review

No current warning in the local API or browser smoke runs indicates data corruption,
lost artifacts, failed queryability, unsafe epoch bounds, or broken ERP comparison
behavior.

The real stabilization target is warning hygiene:

1. Migrate generated and deconflicted FIF filenames to MNE-compliant suffixes.
2. Keep legacy artifact fallback so existing runs remain queryable.
3. Capture expected invalid-file warnings inside the tests that intentionally
   trigger them.
4. Keep MNE/Python warnings persisted on runs when they are produced during real
   processing.

## Recommended Next Step: Filename Migration

Acceptance criteria for the next stabilization step:

- Duplicate uploaded raw filenames preserve the MNE raw suffix.
- Preprocessing output uses an MNE-compliant raw FIF filename.
- Epoch output uses an MNE-compliant epoch FIF filename.
- ERP evoked output uses an MNE-compliant evoked FIF filename.
- Existing run metadata and artifact manifests can still resolve legacy names:
  `raw_preprocessed.fif`, `epochs.fif`, and `evoked_{condition}.fif`.
- Full API tests pass with only expected invalid-file warnings, or with those
  warnings captured by the tests that trigger them.
- Phase 2 and Phase 3 browser smoke tests still pass.

## Migration Result

Implemented in the follow-up filename migration:

- New preprocessing FIF artifacts use `raw_preprocessed_raw.fif`.
- New epoch FIF artifacts use `epochs-epo.fif`.
- New ERP evoked FIF artifacts use `evoked_{condition}-ave.fif`.
- Duplicate uploaded raw FIF names preserve the MNE suffix, for example
  `sample_resting-1_raw.fif`.
- Backend validation and worker execution retain legacy fallbacks for
  `raw_preprocessed.fif` and `epochs.fif`.
- ERP comparison generation retains a legacy fallback for `evoked_{condition}.fif`.

After the migration, the targeted backend tests report only the two expected
invalid-file warnings from `test_upload_eeg_file_rejects_unreadable_eeg`.

## Warning Capture Result

The expected invalid-file warnings are now captured inside
`test_upload_eeg_file_rejects_unreadable_eeg` and asserted explicitly:

- MNE raw naming warning for the intentionally invalid `not-eeg.fif` upload.
- Invalid FIF tag warning for the intentionally unreadable file contents.

This keeps the negative-path coverage while preventing expected invalid-input
warnings from appearing in the global pytest warning summary.
