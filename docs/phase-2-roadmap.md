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

Implemented core objects:

- `PreprocessingConfig`
- `PreprocessingRun`

Implemented configuration fields:

- high-pass filter
- low-pass filter
- notch filter
- resample rate
- reference

Implemented run metadata:

- run ID
- dataset ID
- status
- started and finished timestamps
- output path
- warnings and errors

Implemented API shape:

```text
POST /datasets/{id}/preprocessing-runs
GET /preprocessing-runs/{run_id}
GET /datasets/{id}/preprocessing-runs
```

Implemented storage shape:

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

Implemented UI shape:

- enable preprocessing only for valid datasets
- collect filter settings
- show run status
- show output metadata

Current scope:

- Runs execute synchronously in the API process.
- The first processing backend is MNE-based and writes FIF output.
- Failed runs are persisted with error details before the API returns the failure.

Next likely hardening:

1. Move long preprocessing jobs into a background worker.
2. Add cancellation and progress state.
3. Add richer MNE output metadata and artifact summaries.

## Phase 2.4: Preprocessing Config Hardening

Implemented validation:

- `high_pass_hz` must be lower than `low_pass_hz` when both are set
- filter cutoff and notch frequencies must be below the input Nyquist frequency
- `resample_hz` must not exceed the input sampling rate
- custom reference values must name existing EEG channels
- UI blocks obvious numeric and high/low ordering mistakes before sending the request
- API returns `422` with explicit validation messages for invalid preprocessing settings

## Phase 2.5: Run Provenance

Implemented provenance:

- run config is persisted as the `PreprocessingRun.config` snapshot
- input file ID, original filename, stored path, size, and checksum are stored
- input file format, channel count, sampling rate, duration, and channel names are stored
- output path, size, checksum, file format, channel count, sampling rate, and duration are stored
- MNE version is stored with the completed run metadata
- UI run summaries read the output metadata keys while remaining compatible with older run metadata
