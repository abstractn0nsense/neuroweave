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

## Public PhysioNet Demo

```powershell
.\apps\api\.venv\Scripts\python.exe .\scripts\prepare_physionet_eegmmi_demo.py
```

This opt-in script downloads PhysioNet EEGMMI `S001R03.edf` to
`data/raw/public-samples/` and creates `S001R03_events.csv` from the EDF+
annotations. It also writes `S001R03_neuroweave_smoke.json`, which records the
fixed ingest -> preprocessing -> epoch -> ERP -> comparison contract. The
generated files stay under the ignored `data/` directory and must not be
committed.

If the EDF already exists locally, regenerate only the CSV with:

```powershell
.\apps\api\.venv\Scripts\python.exe .\scripts\prepare_physionet_eegmmi_demo.py --events-only
```

See `docs/public-data-smoke-fixtures.md`,
`docs/public-demo-physionet-eegmmi.md`, and
`docs/public-demo-openneuro-bids.md` for the public-data smoke profiles and
expected warning snapshots.

GitHub Actions also has a manual opt-in workflow:
`.github/workflows/public-dataset-smoke.yml`. It is not attached to pull request
or `main` push CI. By default it only runs the offline public-smoke contract
tests; set `download_public_data=true` in the manual dispatch form to download
the PhysioNet EDF and prepare the manifest/event CSV artifacts.

## Click-to-Run Launcher

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_neuroweave.ps1
```

The root `Start NeuroWeave.bat` file calls this script for double-click startup. It starts the API and web servers, waits for `http://127.0.0.1:8000/health` and `http://127.0.0.1:5173`, writes logs to `data/logs/api.log` and `data/logs/web.log`, and opens the browser.

The start script is idempotent for this checkout. It reuses healthy repo-owned
listeners, stops stale repo-owned listeners, and refuses to take over ports owned
by unrelated processes. Runtime process markers are written under
`data/runtime/`.

Create Desktop and Start Menu shortcuts with:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_neuroweave_shortcut.ps1
```

The shortcut uses a generated icon at `data/app/neuroweave.ico`, hides server windows, and opens the browser when the app is ready.

Stop the default local servers with:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop_neuroweave.ps1
```

The stop script uses both runtime markers and listening ports, and only stops
processes whose command line points at the current checkout.

## Desktop Packaging Backend

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_backend_exe.ps1
```

This builds `dist/desktop/backend/neuroweave-api.exe` with PyInstaller. The
Electron package step copies that executable into `resources/backend/` and starts
it in packaged mode. Runtime logs and research data are written to Electron
`userData`, while development builds continue using the repository `data/`
directory.

Generate the desktop installer icon with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_desktop_icon.ps1
```

The Electron installer build uses `dist/desktop/icon/neuroweave.ico` for the app,
Desktop shortcut, Start Menu shortcut, and uninstall entry.

Run the lifecycle smoke before desktop packaging changes:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke_lifecycle.ps1
```

It starts the app, verifies API health and worker threads, starts again to check
idempotency, checks `data/logs/` and `data/runtime/`, then stops repo-owned
processes.

## Phase 0 Smoke Test

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke_phase0.ps1
```

The smoke test sets up the API environment, generates sample EEG files, runs Python tests, checks API endpoints with `TestClient`, and builds the web app.
