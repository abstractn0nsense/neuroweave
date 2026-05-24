# API App

Server-side entrypoint for EEG workflows.

## Local Development

Use CPython 3.12 or 3.13 for the local API environment. On Windows, prefer the repository setup script because `python` may resolve to MSYS Python instead of CPython.

```powershell
powershell -ExecutionPolicy Bypass -File ..\..\scripts\setup_api.ps1
.\.venv\Scripts\Activate.ps1
uvicorn main:app --reload
```

The development server runs on `http://127.0.0.1:8000`.

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Sample dataset endpoints:

```text
GET /datasets/samples
GET /datasets/samples/{id}/metadata
```

The API reads app-visible sample EEG files from `data/raw/samples/`. Supported Phase 0 formats are FIF, EDF, BDF, BrainVision VHDR, and EEGLAB SET.

Phase 1 project and experiment endpoints:

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
POST /datasets/{dataset_id}/events/mapping
GET /datasets/{dataset_id}/events
GET /datasets/{dataset_id}/validation
POST /datasets/{dataset_id}/preprocessing-runs
GET /datasets/{dataset_id}/preprocessing-runs
GET /preprocessing-runs/{run_id}
POST /preprocessing-runs/{run_id}/cancel
POST /datasets/{dataset_id}/epoch-runs
GET /datasets/{dataset_id}/epoch-runs
GET /epoch-runs/{run_id}
POST /datasets/{dataset_id}/erp-runs
GET /datasets/{dataset_id}/erp-runs
GET /erp-runs/{run_id}
POST /erp-runs/{run_id}/comparison-summary
```

These endpoints write through `eeg_io.registry.JsonRegistryRepository` to the local JSON registry under `data/raw/uploads/`.

Run metadata is written through `eeg_io.registry.JsonRunRepository` under `data/runs/`. New run records include a `run_kind` and `schema_version` marker while remaining compatible with older preprocessing run JSON that does not have those fields. Processed FIF outputs are written under `data/processed/`.

Preprocessing config validation rejects invalid filter ordering, cutoff frequencies at or above Nyquist, upsampling beyond the input sampling rate, and custom reference channels that do not exist in the uploaded recording.

Completed preprocessing runs store provenance in `output_metadata`, including input file identity, paths, checksums, size, input/output signal metadata, output checksum, and MNE version. The run `config` field is the persisted preprocessing configuration snapshot.

Completed preprocessing runs also write diagnostics beside `raw_preprocessed_raw.fif`: `preprocessing_summary.json`, `filter_report.json`, and `artifact_summary.json`. Their paths and key artifact counts are recorded in `output_metadata`. Completed runs also write `artifact_manifest.json` with file paths, sizes, checksums, and artifact types for the primary FIF and diagnostics. Existing runs that still point at `raw_preprocessed.fif` remain readable through the backend fallback path.

Phase 3 analysis output roots are configurable with `NEUROWEAVE_EPOCHS_DIR` and `NEUROWEAVE_ERP_DIR`. When unset, epoch artifacts will default to `data/epochs/{dataset_id}/{run_id}/` and ERP artifacts will default to `data/erp/{dataset_id}/{run_id}/`.

`POST /datasets/{dataset_id}/epoch-runs` creates a validation-backed `pending` epoch run from a completed preprocessing run, then queues MNE epoch execution in the local epoch worker. Completed epoch runs write `epochs-epo.fif`, `epoch_summary.json`, `condition_counts.json`, `drop_log.json`, and `artifact_manifest.json` under `data/epochs/{dataset_id}/{run_id}/`. Epoch diagnostics include versioned summary metadata, UI-oriented condition counts, timing/baseline details, and deterministic drop reason summaries; failed runs remain queryable without diagnostics paths. Existing runs that still point at `epochs.fif` remain readable through the backend fallback path.

`POST /datasets/{dataset_id}/erp-runs` creates a `pending` ERP run from a completed epoch run, then queues condition-level evoked generation in the local ERP worker. Completed ERP runs write `evoked_{condition}-ave.fif`, `erp_{condition}.png`, `erp_{condition}.svg`, `erp_metadata.json`, and `artifact_manifest.json` under `data/erp/{dataset_id}/{run_id}/`. ERP metadata stores the original condition labels, nave, channel/time bounds, sampling rate, compact peak/GFP summaries in microvolts, and plot status. Plot failures are captured as warnings while the ERP run remains completed and queryable if evoked generation succeeds. Comparison generation can still read legacy `evoked_{condition}.fif` metadata when the legacy file exists.

Artifact files are served through `GET /artifacts/{run_id}/{filename}` with run artifact-root validation instead of exposing unrestricted filesystem paths.

`POST /erp-runs/{run_id}/comparison-summary` writes descriptive Phase 3 comparison prep under the ERP run artifact directory as `comparison_summary.json`. The summary stores the selected condition pair, channel or GFP target, mean-amplitude window, condition means, A-B difference, and an explicit marker that statistical testing is deferred to Phase 4.

Preprocessing runs also persist captured MNE/Python warnings in `warnings`. Failed runs persist `errors`, retain input provenance, and remain available through the run lookup endpoints.

`POST /datasets/{dataset_id}/preprocessing-runs` creates a `pending` run and returns immediately after enqueueing it in the local preprocessing worker. Use `GET /preprocessing-runs/{run_id}` or `GET /datasets/{dataset_id}/preprocessing-runs` to poll for `running`, `completed`, or `failed` status. On API startup, the worker recovers `pending` and stale `running` runs from `data/runs`.

`POST /preprocessing-runs/{run_id}/cancel` cancels pending runs immediately. Running runs are marked `cancelling` and become `cancelled` at the next background checkpoint.

Cancellation requests persist `cancel_requested_at_utc`. The preprocessing worker checks cancellation before and after read, filter, notch, reference, resample, and save stages. MNE execution runs in a child process so running jobs can also be terminated when cancellation is requested during a long processing call.

Expected responsibilities:

- expose dataset, workflow, job, and result endpoints
- validate request and response shapes
- compose workflow use cases with EEG I/O and processing packages
- handle authentication and runtime configuration when those features are added
- expose future chat-command endpoints without placing chat logic directly in the API layer

Do not put reusable EEG domain rules here. Move them to `packages/eeg-core`.
