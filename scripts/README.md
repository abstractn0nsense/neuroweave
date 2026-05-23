# Scripts

Repository scripts live here.

Use this folder for repeatable local setup, fixture generation, and small maintenance commands. Scripts should be safe to re-run and should not require checking generated `data/` contents into git.

## API Setup

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_api.ps1
```

The script selects a supported CPython 3.12 or 3.13 interpreter and creates `apps/api/.venv`.

## Sample EEG Generation

```powershell
.\apps\api\.venv\Scripts\python.exe .\scripts\generate_sample_eeg.py
```

The script writes small deterministic FIF files to `tests/fixtures/eeg/` and local app samples to `data/raw/samples/`.

## Phase 0 Smoke Test

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke_phase0.ps1
```

The smoke test sets up the API environment, generates sample EEG files, runs Python tests, checks API endpoints with `TestClient`, and builds the web app.
