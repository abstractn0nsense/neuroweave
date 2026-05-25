# NeuroWeave Desktop

This is the Phase A10 Electron shell MVP. It opens the existing NeuroWeave web UI
inside a desktop app window and manages the local FastAPI backend process.

This package does not create an installer or updater yet. In development mode it
starts the repository FastAPI backend from `apps/api/.venv`, waits for `/health`,
then loads the existing Vite web UI. In packaged mode it loads the React
production build from Electron resources and starts the bundled backend
executable from Electron resources.

## Development

Set up the API environment and start the existing Vite web server:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_api.ps1
cd apps/web
npm install
npm run dev
```

In a second terminal, launch the desktop shell:

```powershell
cd apps/desktop
npm install
npm run dev
```

By default, the desktop shell loads:

```text
http://127.0.0.1:5173
```

Override the target web URL when needed:

```powershell
$env:NEUROWEAVE_WEB_URL = "http://127.0.0.1:5175"
npm run dev
```

The backend defaults to `http://127.0.0.1:8000/health`. Override ports and
timeouts with:

```powershell
$env:NEUROWEAVE_API_PORT = "8100"
$env:NEUROWEAVE_BACKEND_TIMEOUT_MS = "90000"
npm run dev
```

If you want to keep managing the backend yourself:

```powershell
npm run dev:external-backend
```

## Backend Lifecycle

Development mode:

- starts `apps/api/.venv/Scripts/python.exe -m uvicorn main:app`
- writes backend output to `data/logs/desktop-api.log`
- reuses a healthy API already responding on the configured health URL
- terminates only the backend child process started by Electron on app quit

Packaged mode:

- loads `resources/web/index.html`
- starts `resources/backend/neuroweave-api.exe`
- writes logs under Electron `userData/logs`
- stores local research data under Electron `userData/data`
- can be overridden before bundling with `NEUROWEAVE_API_COMMAND`,
  `NEUROWEAVE_API_ARGS`, `NEUROWEAVE_API_CWD`, and
  `NEUROWEAVE_DESKTOP_DATA_DIR`

Packaged local data layout:

```text
userData/
  logs/                 desktop-api.log
  data/
    raw/samples/        local sample EEG files
    raw/uploads/        user-uploaded recordings and event logs
    runs/               run state
    processed/          preprocessing outputs
    epochs/             epoch outputs
    erp/                ERP outputs, plots, reports, bundles
```

## Packaging

Build the React production app:

```powershell
npm run build:web
```

Build the PyInstaller backend executable:

```powershell
npm run build:backend
```

Create an unpacked Windows Electron app directory:

```powershell
npm run package:dir
```

The packaged app is written to `apps/desktop/dist-app-unpacked/win-unpacked/`.
This is not an installer; it is the app directory used to verify bundled
resources before the installer phase. The A11 directory build keeps `asar`
disabled so repeated local packaging and resource inspection are straightforward.

## Checks

```powershell
npm run check
```

Backend launch smoke:

```powershell
$env:NEUROWEAVE_API_PORT = "8110"
npm run smoke:backend
Remove-Item Env:\NEUROWEAVE_API_PORT
```

Packaged resource smoke without creating an installer:

```powershell
$env:NEUROWEAVE_DESKTOP_FORCE_PACKAGED_MODE = "1"
$env:NEUROWEAVE_DESKTOP_RESOURCES_DIR = "..\..\dist\desktop"
$env:NEUROWEAVE_API_PORT = "8114"
npm run smoke:backend
Remove-Item Env:\NEUROWEAVE_DESKTOP_FORCE_PACKAGED_MODE
Remove-Item Env:\NEUROWEAVE_DESKTOP_RESOURCES_DIR
Remove-Item Env:\NEUROWEAVE_API_PORT
```

The shell keeps Node integration disabled and opens external URLs in the system
browser.
