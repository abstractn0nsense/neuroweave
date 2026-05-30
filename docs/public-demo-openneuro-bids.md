# OpenNeuro BIDS-Style Public Smoke

This smoke fixes the contract for a real OpenNeuro EEG-BIDS dataset without
checking public data into the repository.

Reference dataset:

- OpenNeuro dataset: `ds002718`
- Title: Face processing EEG dataset for EEGLAB
- DOI: `https://doi.org/10.18112/openneuro.ds002718.v1.1.0`
- Example source page: `https://openneuro.org/datasets/ds002718`
- Suggested subject/task for manual smoke: `sub-019`, `task-FaceRecognition`

The dataset is BIDS-style EEG. The smoke is intended to exercise adjacent
sidecar discovery for:

- `*_eeg.json`
- `*_channels.tsv`
- `*_events.tsv`

## Storage Policy

Download or sync public data only under the ignored `data/` directory:

```text
data/raw/public-samples/openneuro/ds002718/
```

Do not commit copied OpenNeuro files. Commit only docs, tests, small synthetic
fixtures, and expected warning snapshots.

## Prepare Files

Use an OpenNeuro download method outside git, for example the OpenNeuro CLI or a
browser download. Keep the BIDS directory structure intact under:

```text
data/raw/public-samples/openneuro/ds002718/
```

For a single-recording smoke, choose one EEG recording and its adjacent sidecars.
The expected local shape is:

```text
data/raw/public-samples/openneuro/ds002718/sub-019/eeg/
  sub-019_task-FaceRecognition_eeg.set
  sub-019_task-FaceRecognition_eeg.json
  sub-019_task-FaceRecognition_channels.tsv
  sub-019_task-FaceRecognition_events.tsv
```

If the selected dataset version uses `.edf`, `.bdf`, `.vhdr`, or another
supported EEG extension instead of `.set`, keep the same BIDS basename.

## Upload In NeuroWeave

1. Start NeuroWeave.
2. In `Setup`, create a project, experiment, and dataset.
3. Click `Continue Analysis`.
4. Upload the selected `*_eeg.*` file as `EEG Recording`.
5. Confirm sidecar discovery reports the adjacent `_eeg.json`, `_channels.tsv`,
   and `_events.tsv` candidates when those files are present.
6. Upload the matching `*_events.tsv` as `Event Log`.
7. In `Event Mapping`, use preset `BIDS Events` or map manually:
   - `onset_seconds` -> `onset`
   - `duration_seconds` -> `duration`
   - `trial_type` -> `trial_type`
   - `stimulus` -> `stimulus` or `stim_file` if available
8. If the condition label should come from a different source column, set the
   configured condition column in the API mapping request. Common candidates are
   `trial_type`, `value`, and `stim_file`.
9. Click `Validate Dataset`.
10. Run preprocessing.
11. Create epochs using the selected condition field.
12. Generate ERP preview from the completed epoch run.
13. Create a comparison summary between two observed conditions. Keep the
    comparison descriptive; statistical testing remains out of scope.

## Expected Warnings

Snapshot fixture:

```text
tests/fixtures/public_smoke/openneuro_bids_style_expected_warnings.json
```

Expected warnings are empty for a clean, complete BIDS sidecar set. Missing
optional sidecars and local MNE/preprocessing warnings are allowed only when
they are structured diagnostics using the D4 taxonomy:

- `source=bids` for sidecar discovery issues
- `source=event_mapping` for event normalization issues
- `source=validation` for validation warnings
- `source=worker` for MNE/preprocessing/epoching/ERP warnings
- `source=artifact` for manifest, QC, or analysis report artifact issues
- `source=export_bundle` for export ZIP omissions
- `source=batch` for batch-level warnings

Invalid sidecars should produce diagnostics and must not corrupt the dataset
record or block the core upload unless the primary EEG/event file cannot be read.

## Test Policy

The committed test suite does not download OpenNeuro data. It validates the
expected warning snapshot and public-data storage policy. The manual smoke is
opt-in because OpenNeuro datasets can be large and must remain in ignored
`data/` paths.
