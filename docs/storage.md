# Storage Rules

NeuroWeave separates versioned test assets from local runtime data.

## Versioned In Git

```text
scripts/
  README.md             Repeatable local scripts and fixture generators
tests/
  fixtures/
    eeg/                Small EEG files for tests and development checks
```

Keep files in `tests/fixtures/eeg/` small, deterministic, and safe to commit. Prefer generated synthetic EEG fixtures during Phase 0.

## Local Only

```text
data/
  raw/
    samples/            Local sample datasets used by the app
    uploads/            User-uploaded EEG files
      projects.json      Local project registry
      experiments.json   Local experiment registry
      participants.json  Local participant registry
      datasets/          Dataset metadata plus uploaded files
  processed/            Derived EEG files and analysis outputs
  runs/                 Workflow run state, logs, and result bundles
  templates/            Workflow template registry JSON
  cache/                Temporary files and reusable computation cache
```

The entire `data/` directory is ignored by git. Do not add `data/.gitkeep`; app code and scripts should create required local folders at runtime.

## Path Policy

- Tests should read committed fixtures from `tests/fixtures/eeg/`.
- The API should read app-visible sample files from `data/raw/samples/`.
- User uploads should go to `data/raw/uploads/`.
- Dataset-scoped upload files should go to `data/raw/uploads/datasets/{dataset_id}/eeg/` and `data/raw/uploads/datasets/{dataset_id}/events/`.
- Processing outputs should go to `data/processed/`.
- Workflow execution records should go to `data/runs/`.
- Workflow templates should go to `data/templates/{template_id}/template.json`.
- Rebuildable temporary files should go to `data/cache/`.
