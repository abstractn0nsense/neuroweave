# Phase 1 Ingestion Plan

Phase 1 should treat uploaded data as an experiment session, not as a loose EEG file.

## Goal

A user can upload external experiment data and get a validated dataset ready for preprocessing and analysis.

```text
create dataset
  -> upload EEG recording
  -> upload event or behavior log
  -> validate timing and metadata
  -> preview channels and events
  -> mark dataset ready for preprocessing
```

## Core Objects

- `Dataset`: one analysis-ready unit.
- `Participant`: participant identifier and optional group metadata.
- `Session`: one experiment visit or recording session.
- `Recording`: EEG signal file and extracted metadata.
- `EventLog`: event, stimulus, response, accuracy, and reaction-time rows.
- `UploadedFile`: original uploaded file plus normalized storage metadata.
- `ValidationReport`: warnings and blocking errors before preprocessing.

## Upload API Shape

```text
POST /projects
GET /projects
POST /projects/{project_id}/experiments
GET /projects/{project_id}/experiments
POST /datasets
GET /datasets
GET /datasets/{dataset_id}
POST /datasets/{dataset_id}/files/eeg
POST /datasets/{dataset_id}/files/events
GET /datasets/{dataset_id}/validation
GET /datasets/{dataset_id}/events
GET /datasets/{dataset_id}/metadata
```

## Event And Behavior Logs

EEG experiments usually need event timing and behavioral data from PsychoPy, E-Prime, Presentation, Psychtoolbox, or a BIDS-style `events.tsv`.

Phase 1 should support:

1. PsychoPy CSV or TSV.
2. Generic CSV or TSV with user-provided column mapping.
3. BIDS-style `events.tsv`.
4. Existing MNE annotations in the EEG file.

Required normalized event fields:

```text
onset_seconds
duration_seconds
trial_type
stimulus
response
correct
reaction_time_seconds
source_row
```

PsychoPy column names vary by experiment, so ingestion should use a mapping rather than hard-coded column names.

Example mapping:

```json
{
  "onset_seconds": "stim_onset",
  "duration_seconds": "stim_duration",
  "trial_type": "condition",
  "stimulus": "stimulus_file",
  "response": "key_resp.keys",
  "correct": "key_resp.corr",
  "reaction_time_seconds": "key_resp.rt"
}
```

## Validation Rules

Blocking errors:

- EEG file cannot be read.
- Sampling rate or channel list is missing.
- Event onset values are missing or nonnumeric.
- Event onset is outside the EEG recording duration.
- Required mapping fields are missing.

Warnings:

- Event log has no response or accuracy columns.
- Event count is unexpectedly low.
- EEG annotations and uploaded event log disagree.
- Participant or session metadata is incomplete.
- Event duration is missing and must be inferred.

## Storage

```text
data/
  raw/
    uploads/
      projects.json
      experiments.json
      participants.json
      datasets/
        {dataset_id}/
          metadata.json
          eeg/
          events/
  processed/
  runs/
  cache/
```

The API should use repository functions rather than reading or writing these files directly. The initial JSON-backed repository lives in `eeg_io.registry.JsonRegistryRepository`.

Phase 1 can use JSON metadata files before introducing a database. The API should hide this detail behind repository/storage functions so a later database migration does not change route behavior.

EEG uploads additionally create:

```text
data/
  raw/
    uploads/
      datasets/
        {dataset_id}/
          uploaded_files.json
          recording.json
          eeg/
            {original_filename}
```

## Completion Criteria

- A dataset can be created through the API.
- Dataset creation verifies the selected project and experiment before storing participant/session metadata.
- EEG file upload stores the original file and extracts metadata.
- Event log upload stores the original file and returns a normalized event preview.
- Validation reports `valid`, `warnings`, and `errors`.
- The web UI shows dataset readiness before preprocessing.
