# PhysioNet EEGMMI Public Demo

This demo lets a user try NeuroWeave with one real public EEG recording without
committing local data to git.

Source dataset:

- PhysioNet EEG Motor Movement/Imagery Dataset v1.0.0
- Record: `S001R03`
- EDF download URL:
  `https://physionet.org/files/eegmmidb/1.0.0/S001/S001R03.edf`
- Dataset DOI: `https://doi.org/10.13026/C28G6P`
- File license: Open Data Commons Attribution License v1.0

PhysioNet describes EEGMMI as 64-channel EEG recorded at 160 Hz in EDF+ format
with annotation channels. The event labels are `T0` for rest, `T1` and `T2` for
task onsets. In run `R03`, `T1` maps to `left_fist` and `T2` maps to
`right_fist`.

## Prepare Files

Run from the repository root:

```powershell
.\apps\api\.venv\Scripts\python.exe .\scripts\prepare_physionet_eegmmi_demo.py
```

The script writes local files under the ignored `data/` directory:

```text
data/raw/public-samples/S001R03.edf
data/raw/public-samples/S001R03_events.csv
data/raw/public-samples/S001R03_neuroweave_smoke.json
```

Use `--events-only` if the EDF already exists and only the event CSV should be
regenerated:

```powershell
.\apps\api\.venv\Scripts\python.exe .\scripts\prepare_physionet_eegmmi_demo.py --events-only
```

## Upload In NeuroWeave

1. Start NeuroWeave.
2. In `Setup`, create a project, experiment, and dataset.
3. Click `Continue Analysis`.
4. Upload `data/raw/public-samples/S001R03.edf` as `EEG Recording`.
5. Upload `data/raw/public-samples/S001R03_events.csv` as `Event Log`.
6. In `Event Mapping`, map:
   - `onset_seconds` -> `onset`
   - `duration_seconds` -> `duration`
   - `trial_type` -> `trial_type`
   - `stimulus` -> `stimulus`
7. Click `Save Mapping`.
8. Click `Validate Dataset`.
9. Run preprocessing. Keep `resample_hz` empty or set it to a value at or below
   `160`.
10. Create epochs using `trial_type` as the condition field.
11. Generate ERP preview from the completed epoch run.
12. Create a comparison summary:
   - `condition_a` -> `left_fist`
   - `condition_b` -> `right_fist`
   - target -> GFP
   - metric -> mean amplitude

The generated smoke manifest records the same mapping, epoching, and comparison
contract so a local run can be checked without committing the downloaded EDF.

## Expected Warnings

Snapshot fixture:

```text
tests/fixtures/public_smoke/physionet_eegmmi_s001r03_expected_warnings.json
```

Expected warnings are empty for ingest, event mapping, and validation. Worker
warnings can vary by MNE version and preprocessing settings, but any such warning
must be preserved as structured diagnostics with `source=worker` while the legacy
`warnings: list[str]` remains available.

If a warning appears during the smoke, record whether it changes the analysis
plan before treating the ERP comparison as interpretable.

## Test Policy

The committed smoke test is offline. It validates the event CSV generation
logic, generated smoke manifest, expected warning snapshot, and expected
PhysioNet URL without downloading public data.

The actual public EDF download is opt-in because it depends on network access
and writes local data under `data/`, which is intentionally git-ignored.
