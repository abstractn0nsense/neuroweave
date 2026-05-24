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
```

These endpoints write through `eeg_io.registry.JsonRegistryRepository` to the local JSON registry under `data/raw/uploads/`.

Expected responsibilities:

- expose dataset, workflow, job, and result endpoints
- validate request and response shapes
- compose workflow use cases with EEG I/O and processing packages
- handle authentication and runtime configuration when those features are added
- expose future chat-command endpoints without placing chat logic directly in the API layer

Do not put reusable EEG domain rules here. Move them to `packages/eeg-core`.
