# NeuroWeave Desktop

This is the Phase A9 Electron shell MVP. It opens the existing NeuroWeave web UI
inside a desktop app window during local development.

This package does not bundle the API, web build, installer, updater, or backend
runtime yet. Start the existing local API and Vite web server first, then launch
the desktop shell.

## Development

From the repository root:

```powershell
.\Start NeuroWeave.bat
```

In a second terminal:

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

## Checks

```powershell
npm run check
```

The shell keeps Node integration disabled and opens external URLs in the system
browser.
