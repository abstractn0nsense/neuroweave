# API App

Server-side entrypoint for EEG workflows.

## Local Development

```powershell
cd apps/api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload
```

The development server runs on `http://127.0.0.1:8000`.

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Expected responsibilities:

- expose dataset, workflow, job, and result endpoints
- validate request and response shapes
- compose workflow use cases with EEG I/O and processing packages
- handle authentication and runtime configuration when those features are added
- expose future chat-command endpoints without placing chat logic directly in the API layer

Do not put reusable EEG domain rules here. Move them to `packages/eeg-core`.
