# Public Dataset Smoke Fixtures

Phase D public-data smoke fixtures are contracts, not committed EEG data. They
define the repeatable local workflow, expected warning policy, and storage
locations for public EEG datasets.

## Profiles

| Profile | Dataset | Data source | Local data root | Expected warning snapshot |
| --- | --- | --- | --- | --- |
| `physionet_eegmmi_s001r03` | PhysioNet EEGMMI `S001R03` | `scripts/prepare_physionet_eegmmi_demo.py` | `data/raw/public-samples/` | `tests/fixtures/public_smoke/physionet_eegmmi_s001r03_expected_warnings.json` |
| `openneuro_bids_style_sample` | OpenNeuro EEG-BIDS sample, documented with `ds002718` | OpenNeuro download outside git | `data/raw/public-samples/openneuro/ds002718/` | `tests/fixtures/public_smoke/openneuro_bids_style_expected_warnings.json` |

## Fixed Workflow

Every public smoke should follow the same high-level path:

1. Store public files only under ignored `data/` paths.
2. Ingest the EEG recording.
3. Ingest or discover adjacent metadata sidecars.
4. Ingest the event log.
5. Save event mapping.
6. Validate the dataset.
7. Run preprocessing.
8. Run epoching with an explicit condition field.
9. Run ERP generation.
10. Run descriptive comparison summary.
11. Review structured diagnostics before interpreting outputs.

## Warning Policy

Expected warning snapshots use the D4 taxonomy:

- `bids`
- `event_mapping`
- `validation`
- `worker`
- `artifact`
- `export_bundle`
- `batch`

Legacy `warnings: list[str]` remains part of run responses. New warning paths
must also be represented under `diagnostics.warnings[]` with `code`, `severity`,
`source`, `impact`, and `suggested_action`.

## Reproducibility Boundary

The committed tests stay offline. They verify scripts, manifest contracts,
expected warning snapshots, and documentation references. Network-dependent
downloads and real public EEG files are opt-in local checks because they can be
large, slow, and license-sensitive.
