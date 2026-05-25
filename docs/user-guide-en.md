# NeuroWeave User Guide

This guide explains how to use the current local NeuroWeave app to create an EEG
dataset, upload files, validate events, run preprocessing, create epochs, generate
ERP previews, and prepare a descriptive condition comparison.

## 1. Launch The App

On Windows, run `Start NeuroWeave.bat` from the repository root.

App URL:

```text
http://127.0.0.1:5173
```

API URL:

```text
http://127.0.0.1:8000
```

To stop the local servers, run `Stop NeuroWeave.bat`.

## 2. UI Layout

The UI is split into two workspace modes.

### Setup

Use Setup to define the study context and choose the active dataset.

- `Study Setup`: create or select a project and experiment.
- `Dataset Queue`: create or select participant/session datasets.
- `Active Dataset`: review the selected dataset readiness state.
- `Sample Metadata`: inspect local sample EEG metadata.

Selecting a dataset in Dataset Queue does not automatically move to analysis.
Use `Continue Analysis` when you are ready to run ingestion and analysis steps.

### Analysis

Use Analysis for file intake and processing.

- `Active Dataset`: shows the current dataset and readiness state.
- `Ingestion And Preprocessing`: EEG upload, event upload, event mapping, validation, and preprocessing.
- `Epoch Controls`: create epochs from completed preprocessing output.
- `ERP Preview`: generate evoked artifacts and preview plots from completed epochs.
- `QC Dashboard`: inspect manifest-backed artifact and warning summaries.

## 3. Quick Test Files

You can test the workflow with local files that are already available.

Public PhysioNet example:

```text
EEG Recording:
C:\neuroweave\data\raw\public-samples\S001R03.edf

Event Log:
C:\neuroweave\data\raw\public-samples\S001R03_events.csv
```

Small fixture example:

```text
EEG Recording:
C:\neuroweave\tests\fixtures\eeg\sample_resting_raw.fif

Event Log:
C:\neuroweave\tests\fixtures\events\psychopy_minimal.csv
```

The PhysioNet file is a real public EDF recording. The fixture files are smaller
and useful for quick smoke tests.

## 4. Create A Dataset

1. Open the `Setup` tab.
2. In `Study Setup`, enter a project name and click `Create Project`.
3. Enter an experiment name and click `Create Experiment`.
4. In `Dataset Queue`, enter participant and session labels and click `Create Dataset`.
5. Confirm that `Active Dataset` shows the selected dataset state.
6. Click `Continue Analysis`.

A dataset usually represents one participant/session recording.

## 5. Upload The EEG Recording

In `Ingestion And Preprocessing`, use `EEG Recording` to upload the raw EEG file.

Currently supported formats:

- FIF
- EDF
- BDF
- BrainVision VHDR
- EEGLAB SET

After selecting the file, click `Upload EEG`. The backend reads sampling rate,
duration, channel count, and channel names.

## 6. Upload The Event Log

Use `Event Log` to upload a CSV or TSV file containing experiment events.

The event log tells NeuroWeave when stimuli or trials occurred. An onset column is
required.

Example:

```csv
onset,duration,trial_type,stimulus
4.200000,4.100000,T2,right_fist
12.500000,4.100000,T1,left_fist
```

After upload, use `Event Mapping` to assign raw columns to normalized event fields.

Important fields:

- `onset_seconds`: event onset time. Required.
- `duration_seconds`: event duration.
- `trial_type`: commonly used as the condition label.
- `stimulus`: stimulus name.
- `response`, `correct`, `reaction_time_seconds`: optional behavioral fields.

Review the mapping and click `Save Mapping`.

## 7. Validate The Dataset

Click `Validate Dataset`. NeuroWeave checks:

- whether an EEG recording exists;
- whether an event log has been mapped;
- whether event onsets fall inside the recording duration;
- whether required metadata is available.

When validation succeeds, the UI shows `Dataset is valid.` and preprocessing becomes
available.

## 8. Run Preprocessing

Default settings:

- high-pass: `1`
- low-pass: `40`
- reference: `average`

Optional settings:

- notch filter
- resample rate
- custom reference

Click `Start Preprocessing`. The run is queued and then executed by the local worker.
When complete, the run row changes to `completed` and NeuroWeave writes processed FIF
and diagnostic artifacts.

Validation rules:

- filter frequencies must be lower than Nyquist;
- resample rate cannot exceed the input sampling rate;
- custom reference channels must exist in the uploaded recording.

## 9. Create Epochs

In `Epoch Controls`, select a completed preprocessing run.

Main settings:

- `condition_field`: event field used as condition labels, usually `trial_type`.
- `tmin_seconds`: epoch start relative to event onset.
- `tmax_seconds`: epoch end relative to event onset.
- baseline: optional baseline correction window.
- reject EEG: optional threshold-based epoch rejection.

Click `Start Epoch`. Completed runs show condition count, epoch count, and dropped
epoch count.

## 10. Generate ERP Preview

In `ERP Preview`, select a completed epoch run.

The default plot mode is GFP. To inspect a specific channel, choose channel plot mode
and enter the channel name.

Click `Generate ERP`. NeuroWeave writes condition-level evoked FIF files, PNG/SVG
plots, and ERP metadata. A preview plot is shown when plot generation succeeds.

## 11. Prepare A Comparison

When a completed ERP run has at least two conditions, you can create a descriptive
comparison summary.

Settings:

- condition A
- condition B
- GFP or channel target
- mean-amplitude time window

This is currently descriptive only. Statistical testing is planned for a later phase.

## 12. Export And Reproducibility

Completed runs preserve:

- input file checksums and metadata;
- immutable config snapshots;
- output artifact paths;
- diagnostic JSON;
- artifact manifests;
- warnings and errors;
- MNE/Python version information.

These records are the basis for reproducing an analysis or explaining why two runs
differ.

## 13. Troubleshooting

If an upload button is disabled:

- make sure a file is selected;
- make sure an active dataset is selected.

If preprocessing is disabled:

- upload both EEG and event files;
- save event mapping;
- run validation successfully.

If epoch or ERP controls are disabled:

- confirm there is a completed preprocessing run;
- confirm there is a completed epoch run.

If the UI state looks wrong:

- click `Refresh`;
- reselect the active dataset from `Setup`;
- restart with `Stop NeuroWeave.bat` and `Start NeuroWeave.bat` if needed.

## 14. Current Limits

- Statistical testing is not implemented yet.
- ICA and advanced artifact correction are planned future work.
- Collaboration, accounts, and cloud storage are not part of the current local prototype.
- The current priority is reproducible local workflow execution and artifact generation.
