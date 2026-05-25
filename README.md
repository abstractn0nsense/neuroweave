# NeuroWeave

NeuroWeave is being prepared as a neuroscience and EEG workflow project.

## Structure

```text
apps/
  api/                  Server/API entrypoint for EEG workflows
  web/                  Web UI for EEG workflow setup and review
packages/
  eeg-core/             EEG domain models and pipeline contracts
  eeg-processing/       Signal preprocessing and analysis steps
  eeg-io/               EEG file readers, writers, and dataset adapters
  workflow-engine/      Pipeline execution graph and job state
  chat-interface/       Future chat layer for controlling EEG workflows
  shared/               Shared config, types, and small utilities
docs/
  architecture.md       Folder boundaries and dependency rules
  eeg-workflow.md       Initial EEG workflow outline
  user-guide-ko.md      Korean user guide for the current local app
  user-guide-en.md      English user guide for the current local app
  public-demo-physionet-eegmmi.md
                        Opt-in public EEGMMI demo workflow
  export-bundle.md      ZIP export structure and diagnostics contract
  neuro-weave-growth-pipeline.md
                        Product and research-platform growth pipeline
  phase-1-ingestion.md  External experiment upload and event-log plan
  storage.md            Versioned fixture and local data rules
  decisions/            Architecture decision notes
scripts/
  README.md             Repeatable local setup and fixture generation scripts
tests/
  fixtures/eeg/         Shared EEG test fixtures
```

## Dependency Direction

Keep dependencies flowing inward:

```text
apps -> packages/workflow-engine -> packages/eeg-processing -> packages/eeg-core
apps -> packages/eeg-io -> packages/eeg-core
apps -> packages/chat-interface -> packages/workflow-engine
apps -> packages/shared
```

`eeg-core` should not import app code, UI frameworks, database clients, or vendor SDKs. The chat layer is intentionally thin for now and should depend on the workflow layer instead of becoming the source of EEG domain rules.

## Storage Rules

Versioned repository assets:

```text
scripts/                Repeatable setup and fixture generation scripts
tests/fixtures/eeg/     Small EEG fixtures used by tests
```

Local runtime data is ignored by git:

```text
data/
  raw/
    samples/            Local sample EEG files used by the app
    uploads/            User-uploaded EEG files
  processed/            Derived EEG outputs
  runs/                 Workflow run state and result bundles
  cache/                Temporary or rebuildable cache files
```

Do not commit `data/` contents or add `data/.gitkeep`. Scripts and app startup code should create local data folders when needed. See `docs/storage.md` for the full policy.

## Local Development

Phase 0 uses local per-app environments:

- API: Python `.venv` inside `apps/api`
- Web: npm dependencies inside `apps/web/node_modules`

Use CPython 3.12 or 3.13 for the API environment. Python 3.14 mingw builds may not have compatible wheels for the Phase 0 dependencies yet. On Windows, prefer the setup script because `python` may resolve to MSYS Python instead of CPython.

### Double-Click Run

On Windows, double-click `Start NeuroWeave.bat` from the repository root. The launcher starts the API and web servers, waits until both respond, writes logs under `data/logs/`, and opens `http://127.0.0.1:5173`.

If the servers are already running, the launcher reuses them instead of starting duplicates. To stop repository-owned listeners on the default ports, double-click `Stop NeuroWeave.bat`.

For an app-like entrypoint, install Windows shortcuts:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_neuroweave_shortcut.ps1
```

This creates Desktop and Start Menu shortcuts with a NeuroWeave icon. The shortcut hides runtime server windows and opens only the browser once the local app is ready.

### Phase 0 Quickstart

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_api.ps1
.\apps\api\.venv\Scripts\python.exe .\scripts\generate_sample_eeg.py

cd apps/api
.\.venv\Scripts\Activate.ps1
uvicorn main:app --reload
```

API URL: `http://127.0.0.1:8000`

In a second terminal:

```powershell
cd apps/web
npm install
npm run dev
```

Web URL: `http://127.0.0.1:5173`

The Phase 0 web screen displays API health, sample EEG datasets, and selected sample metadata.

### User Guides

Current UI guide:

- Korean: `docs/user-guide-ko.md`
- English: `docs/user-guide-en.md`

The app is split into `Setup` and `Analysis` workspace modes. Use `Setup` to create
or select projects, experiments, and datasets. Dataset selection stays in Setup so
the active dataset can be reviewed first. Use `Continue Analysis` to move into file
upload, validation, preprocessing, epoching, ERP preview, QC, and export-oriented
workflows.

### Smoke Test

Run this after dependency setup or before committing Phase 0 changes:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke_phase0.ps1
```

The smoke test generates sample EEG files, runs API/package tests, checks sample API endpoints, and builds the web app.

### API Checks

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Sample dataset endpoints:

```text
GET /datasets/samples
GET /datasets/samples/{id}/metadata
```

Sample EEG files are read from `data/raw/samples/`, which is created locally by the API and ignored by git.

Generate deterministic Phase 0 sample EEG files:

```powershell
.\apps\api\.venv\Scripts\python.exe .\scripts\generate_sample_eeg.py
```

This writes committed test fixtures to `tests/fixtures/eeg/` and local app samples to `data/raw/samples/`.

### Public PhysioNet Demo

Prepare a real public EDF demo from PhysioNet EEGMMI `S001R03`:

```powershell
.\apps\api\.venv\Scripts\python.exe .\scripts\prepare_physionet_eegmmi_demo.py
```

This downloads `S001R03.edf` and writes `S001R03_events.csv` under
`data/raw/public-samples/`. The `data/` directory is ignored by git, so the
public recording is never committed. Follow
`docs/public-demo-physionet-eegmmi.md` to upload the files and run
preprocessing, epoching, and ERP preview.

## Product Pipeline

The long-term workflow is organized around external experiment sessions:

```text
upload EEG recording and event log
  -> validate metadata and timing
  -> preprocess signal
  -> run analysis
  -> produce plots, tables, and export bundles
```

See `docs/phase-1-ingestion.md` for the next phase, including PsychoPy-style event and behavior logs.

See `docs/phase-2-roadmap.md` for the current Phase 2 plan: click-to-run launch, app-like launch polish, and preprocessing handoff.
