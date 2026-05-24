# Phase 2 Roadmap

Phase 2 now includes the remaining app-operational work from the former Phase 1 tail plus the first preprocessing handoff.

## Phase 2.1: Click-to-Run Launcher

Goal: run NeuroWeave without typing PowerShell commands.

Implemented entrypoints:

- `Start NeuroWeave.bat`
- `scripts/start_neuroweave.ps1`
- `Stop NeuroWeave.bat`
- `scripts/stop_neuroweave.ps1`

Launcher behavior:

- create `data/logs/` when needed
- install the API virtual environment when missing
- install web dependencies when `apps/web/node_modules` is missing
- start the API server on `http://127.0.0.1:8000`
- start the web server on `http://127.0.0.1:5173`
- wait for API and web health checks
- open the browser to `http://127.0.0.1:5173`
- write logs to `data/logs/api.log` and `data/logs/web.log`
- avoid starting duplicate servers when the existing URLs already respond

## Phase 2.2: App-Like Launch Polish

Goal: make the local server and browser shape feel like a lightweight desktop app.

Implemented work:

1. `scripts/install_neuroweave_shortcut.ps1` creates Desktop and Start Menu shortcuts.
2. The shortcut uses a generated NeuroWeave `.ico` at `data/app/neuroweave.ico`.
3. Runtime API and web server windows are hidden when launched from the shortcut.
4. The browser remains the primary user-facing surface.
5. The web app has a NeuroWeave SVG favicon.
6. README and script docs include the app-like launch guide.

Electron or Tauri should wait until the web and preprocessing workflows are stable.

## Phase 2.3: Preprocessing Handoff

Goal: pass a valid dataset into actual MNE preprocessing.

Core objects:

- `PreprocessingConfig`
- `PreprocessingRun`

Configuration fields:

- high-pass filter
- low-pass filter
- notch filter
- resample rate
- reference

Run metadata:

- run ID
- dataset ID
- status
- started and finished timestamps
- output path
- warnings and errors

API shape:

```text
POST /datasets/{id}/preprocessing-runs
GET /preprocessing-runs/{run_id}
GET /datasets/{id}/preprocessing-runs
```

Storage shape:

```text
data/
  runs/
    {run_id}/
      run.json
  processed/
    {dataset_id}/
      {run_id}/
        raw_preprocessed.fif
```

UI shape:

- enable preprocessing only for valid datasets
- collect filter settings
- show run status
- show output metadata
