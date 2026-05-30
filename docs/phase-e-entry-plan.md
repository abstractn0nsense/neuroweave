# Phase E Entry Plan

Recorded on 2026-05-30 after the Phase D exit gate and current-regression
check.

## Entry Decision

Phase E is cleared to start.

Current gate results from `main` before opening Phase E implementation work:

- `git status --short --branch`: `## main...origin/main`
- `.\apps\api\.venv\Scripts\python.exe -m pytest tests -o cache_dir=data/cache/pytest-cache --basetemp data/cache/pytest-phase-e-preflight`:
  271 passed.
- `npm.cmd run build` in `apps/web`: passed.
- `npm.cmd run e2e:all` in `apps/web`: passed, including Phase 2
  preprocessing, Phase C batch retry, Phase 3 epoch, and Phase 3 ERP smoke
  tests.

Phase D can be treated as closed. The exit decision, regression gate, public
dataset smoke results, and carryover list are recorded in
`docs/phase-d-exit-report.md`.

## Phase E Goal

Phase E should turn the current descriptive ERP comparison and run-artifact
foundation into a first reproducible analysis layer.

This phase should prioritize:

- a stable inferential statistics contract for ERP comparison outputs;
- one narrow statistics MVP that can be validated against deterministic
  fixtures;
- report, export, and QC integration for the new statistics output;
- a read-only reproducibility graph that records dataset, run, config, artifact,
  and parent-child lineage;
- a safe rerun planning contract before any one-click rerun execution exists.

Phase E should not become a broad product-polish phase. Batch UI completion,
collaboration, advanced artifact review, broad public-data CI, and local data
governance are important, but they should stay out of the first Phase E track
unless the statistics and reproducibility foundation is already closed.

## Included In Phase E

The following items are in scope for this phase:

- Define a statistics result schema for ERP comparison summaries.
- Add one initial inferential statistics implementation for ERP mean-amplitude
  comparison.
- Preserve the existing descriptive comparison fields and the previous
  statistics-deferred marker as backward-compatible metadata where needed.
- Surface statistics results in API responses, `analysis_report.json`, export
  bundles, and QC-facing summaries.
- Define and generate a run reproducibility graph artifact for completed
  preprocessing, epoch, ERP, and comparison paths.
- Add a read-only reproducibility graph view in the web UI if the backend graph
  contract is stable.
- Add rerun-plan validation that reports whether a completed analysis can be
  recreated from available source files, configs, parent run IDs, and artifacts.
- Keep public dataset smoke workflows opt-in and local-data-safe.
- Add targeted tests for every new contract and keep the existing Phase 2,
  Phase C, and Phase 3 browser smokes passing.

## Deferred To Phase F Or Later

The following items are explicitly not required to close Phase E:

- Full statistics suite across all likely EEG designs.
- Permutation tests as the default path for every comparison.
- Cluster-based or time-by-channel multiple-comparison workflows.
- Group-level subject statistics and publication-grade tables.
- Automatic one-click rerun execution.
- Broad public dataset CI that downloads and runs multiple large EEG datasets by
  default.
- Complete multi-subject batch UI beyond the Phase C foundation.
- Collaboration, project archive sharing, and immutable shareable snapshots.
- Advanced artifact workflows such as ICA execution, bad-channel interpolation,
  and manual artifact review.
- Large visual regression suite for all ERP and QC views.
- Data governance polish such as explicit local data deletion, preview-version
  migration tooling, and retention-policy workflows.

## Compatibility Rules

Phase E changes must follow these rules:

- Do not rewrite completed run configs.
- Add fields and artifacts instead of renaming existing Phase 2, Phase C, Phase
  D, or Phase 3 fields.
- Keep legacy `raw_preprocessed.fif`, `epochs.fif`, and `evoked_*.fif` artifact
  names readable for at least this phase.
- Keep existing `comparison_summary.json` descriptive fields readable.
- Treat missing optional Phase D metadata as warnings, not hard failures.
- Keep public EEG data and generated local smoke manifests under ignored
  `data/` paths.
- Do not require network downloads in the default test gate.

## One-Prompt Work Slices

Each item below is sized so it can be given to Codex as one implementation
request.

### E0. Phase E Entry Plan

- Add this entry plan.
- Link the plan to the Phase D exit baseline.
- Separate Phase E scope from Phase F-or-later work.
- Do not change runtime code.

Acceptance:

- `docs/phase-e-entry-plan.md` exists.
- Phase E included and deferred scopes are explicit.
- Current regression gate results are recorded.

Status: complete in this document.

### E1. Statistics Contract Baseline

- Define the statistics output shape for ERP comparisons.
- Include method, design, assumptions, input metric, condition pair, sample
  counts, statistic value, p-value, effect size, confidence interval fields, and
  diagnostics.
- Add deterministic fixture expectations without implementing the full
  statistics engine.

Acceptance:

- Contract tests define the expected JSON shape.
- Existing comparison summaries remain backward-compatible.
- Documentation explains which statistics are implemented versus planned.

Status: complete. See `docs/statistics-contract.md`,
`docs/schemas/erp-comparison-statistics.schema.json`, and
`tests/fixtures/statistics/`.

### E2. Mean-Amplitude Statistics MVP

- Implement one initial inferential test for ERP mean-amplitude comparison.
- Prefer the simplest defensible design supported by the existing comparison
  inputs.
- Return structured diagnostics when the selected comparison cannot support the
  requested test.

Acceptance:

- Deterministic tests cover a successful comparison and an unsupported
  comparison.
- `comparison_summary.json` includes the new statistics object.
- Existing Phase 3 ERP smoke still passes.

Status: complete. ERP comparison summaries now support Phase E paired
mean-amplitude t-test statistics when subject-level paired observations are
supplied, and structured unavailable diagnostics otherwise.

### E3. Statistics Report And Export Integration

- Surface the E2 statistics result in ERP comparison API responses.
- Add the result to `analysis_report.json`.
- Include the result and diagnostics in export bundles without changing the
  existing bundle structure.

Acceptance:

- Report and export tests cover both implemented and unavailable statistics.
- Missing or unsupported statistics appear as structured diagnostics.
- Existing export bundle tests still pass.

Status: complete. Analysis reports now include `comparison_statistics`, and
export bundle manifests include comparison/statistics summaries plus statistics
diagnostics.

### E4. Reproducibility Graph Contract

- Define a reproducibility graph artifact for completed analysis paths.
- Include dataset IDs, run IDs, config hashes or snapshots, parent-child run
  relationships, artifact logical names, artifact paths, checksums when
  available, worker metadata, and Phase D provenance links.

Acceptance:

- Completed runs can generate `reproducibility_graph.json`.
- Tests cover preprocessing, epoch, ERP, comparison, and batch-created run
  lineage.
- Missing optional provenance creates warnings, not hard failures.

### E5. Reproducibility Graph Read-Only UI

- Add a compact read-only view for the reproducibility graph.
- Show dataset, preprocessing, epoch, ERP, comparison, config, and artifact
  lineage without adding rerun execution.

Acceptance:

- The UI handles missing graph data gracefully.
- Existing test IDs used by Phase 2, Phase C, and Phase 3 browser smokes remain
  stable.
- Web build passes.

### E6. One-Click Rerun Planning Contract

- Add an API path or service that creates a rerun plan for a completed analysis.
- Validate source file availability, parent runs, config snapshots, artifact
  presence, and compatibility warnings.
- Do not execute the rerun in this slice.

Acceptance:

- Rerun plan tests cover ready, blocked, and partially recoverable cases.
- The plan is deterministic and does not mutate existing runs.
- The response clearly separates blockers from warnings.

### E7. Phase E Exit Gate

- Run the full Python test gate, web build, and `npm.cmd run e2e:all`.
- Record final statistics and reproducibility behavior.
- Move unfinished public-data CI, collaboration, advanced artifact workflow,
  visual regression, batch UI, and data governance items to Phase F or later.

Acceptance:

- Regression gate passes.
- Phase E artifacts and contracts are documented.
- Phase F-or-later carryover is explicit.
