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

Use CPython 3.12 or 3.13 for the API environment. Python 3.14 mingw builds may not have compatible wheels for the Phase 0 dependencies yet.

### API

```powershell
cd apps/api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload
```

API URL: `http://127.0.0.1:8000`

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

### Web

```powershell
cd apps/web
npm install
npm run dev
```

Web URL: `http://127.0.0.1:5173`
