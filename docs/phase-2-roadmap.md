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

- The first processing backend is MNE-based and writes FIF output.
- Runs are created as `pending`, then executed by FastAPI background tasks.
- The UI polls pending/running runs until they reach `completed` or `failed`.
- Failed runs are persisted with warning and error details.

Next likely hardening:

1. Move background tasks into a durable worker process for very large EEG files.
2. Add cancellation and progress state.
3. Add richer artifact summaries.

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

## Phase 2.6: Warning And Error Capture

Implemented capture:

- MNE/Python warnings emitted while reading, preprocessing, and saving raw data are captured
- captured warnings are persisted on completed preprocessing runs
- failed preprocessing runs persist any warnings collected before failure
- failed preprocessing runs remain queryable through dataset run listing
- UI run rows already separate warning text from error text

## Phase 2.7: Background Preprocessing Runs

Implemented execution model:

- `POST /datasets/{id}/preprocessing-runs` validates the dataset and config, saves a `pending` run, and returns immediately
- background execution updates the run to `running`, then `completed` or `failed`
- successful runs persist output metadata, provenance, and captured warnings
- failed runs persist errors, captured warnings, and input provenance
- the web UI polls preprocessing runs while any selected-dataset run is `pending` or `running`

## Phase 2.8: Cancel Preprocessing Runs

Implemented cancellation:

- `POST /preprocessing-runs/{run_id}/cancel`
- pending runs are marked `cancelled` immediately
- running runs are marked `cancelling` as a best-effort cancellation request
- background execution skips runs already marked `cancelled`
- background execution converts `cancelling` runs to `cancelled` at the next completion checkpoint
- cancellation warnings are persisted on the run
- the web UI shows Cancel buttons for `pending` and `running` runs
