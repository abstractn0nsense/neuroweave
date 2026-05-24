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
```

These endpoints write through `eeg_io.registry.JsonRegistryRepository` to the local JSON registry under `data/raw/uploads/`.

Preprocessing run metadata is written through `eeg_io.registry.JsonRunRepository` under `data/runs/`, and processed FIF outputs are written under `data/processed/`.

Preprocessing config validation rejects invalid filter ordering, cutoff frequencies at or above Nyquist, upsampling beyond the input sampling rate, and custom reference channels that do not exist in the uploaded recording.

Completed preprocessing runs store provenance in `output_metadata`, including input file identity, paths, checksums, size, input/output signal metadata, output checksum, and MNE version. The run `config` field is the persisted preprocessing configuration snapshot.

Preprocessing runs also persist captured MNE/Python warnings in `warnings`. Failed runs persist `errors`, retain input provenance, and remain available through the run lookup endpoints.

Expected responsibilities:

- expose dataset, workflow, job, and result endpoints
- validate request and response shapes
- compose workflow use cases with EEG I/O and processing packages
- handle authentication and runtime configuration when those features are added
- expose future chat-command endpoints without placing chat logic directly in the API layer

Do not put reusable EEG domain rules here. Move them to `packages/eeg-core`.
