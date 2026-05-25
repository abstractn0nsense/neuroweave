# NeuroWeave Desktop

This is the Phase A10 Electron shell MVP. It opens the existing NeuroWeave web UI
inside a desktop app window and manages the local FastAPI backend process.

This package does not bundle the web build, installer, updater, or packaged
backend runtime yet. In development mode it starts the repository FastAPI backend
from `apps/api/.venv`, waits for `/health`, then loads the existing Vite web UI.

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

- does not assume the repository layout
- writes logs under Electron `userData/logs`
- expects future installer work to provide a backend runtime
- can be wired before bundling with `NEUROWEAVE_API_COMMAND`,
  `NEUROWEAVE_API_ARGS`, and `NEUROWEAVE_API_CWD`

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

The shell keeps Node integration disabled and opens external URLs in the system
browser.
