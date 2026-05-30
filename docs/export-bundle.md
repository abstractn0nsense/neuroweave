# Export Bundle

NeuroWeave export bundles are ZIP files intended for research sharing and
reproducibility review. The current MVP supports completed ERP runs and is built
from the run artifact manifest.

## ZIP Structure

```text
analysis_report.json
artifact_manifest.json
export_bundle_manifest.json
configs/
diagnostics/
figures/
provenance/
artifacts/
```

- `analysis_report.json`: human-readable JSON report for the completed run.
- `artifact_manifest.json`: source manifest with paths, checksums, sizes, and
  artifact types.
- `export_bundle_manifest.json`: bundle-level manifest listing every ZIP entry
  and structured diagnostics.
- `configs/`: config snapshots when the artifact manifest lists config files.
- `diagnostics/`: metadata, summaries, QC diagnostics, and other JSON diagnostics.
- `figures/`: plots and preview images such as ERP PNG/SVG outputs.
- `provenance/`: provenance JSON and source/run lineage artifacts.
- `artifacts/`: primary or uncategorized artifacts such as FIF outputs.

ERP export bundle manifests may also include:

- `comparison_summary`: selected comparison metric, condition pair, target,
  window, and descriptive difference when a comparison summary exists.
- `comparison_statistics`: Phase E statistics status, method, sample, result,
  assumptions, and structured diagnostics. Unavailable statistics are warnings,
  not export failures.

## Missing Artifacts

If an artifact is listed in `artifact_manifest.json` but the file is missing,
bundle creation continues. The missing item is omitted from the ZIP and recorded
as a structured warning in `export_bundle_manifest.json`:

```json
{
  "code": "artifact_missing",
  "severity": "warning",
  "source": "export_bundle",
  "impact": "Artifact 'example' was not included ...",
  "suggested_action": "Regenerate the source run artifact or rebuild the artifact manifest."
}
```

This keeps completed runs shareable while preserving enough diagnostics for a
reviewer to see that the bundle is incomplete.

## UI States

In the ERP run list:

- `Export unavailable`: the run is not completed or has no artifact manifest.
- `Export ready: report will be generated before ZIP download`: artifacts are
  ready and the report can be generated on demand.
- `Export ready: report, manifest, plots, provenance, diagnostics, and artifacts`:
  report generation has completed and the ZIP can be downloaded directly.
