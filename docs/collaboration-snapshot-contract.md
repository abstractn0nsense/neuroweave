# Collaboration Snapshot Contract

Phase E defines collaboration as an immutable local archive snapshot, not a
hosted collaboration service. A snapshot is a shareable, content-addressed
manifest plus a future ZIP payload that lets another researcher inspect project
metadata, run metadata, reports, provenance, and artifact manifests without
requiring a shared server.

Schema:

- `docs/schemas/project-archive-manifest.schema.json`

Fixture:

- `tests/fixtures/collaboration/project_archive_manifest_v1.json`

## Scope

In scope:

- Project archive manifest shape.
- Included and excluded data policy.
- Checksum contract for every archive entry.
- Immutable snapshot semantics.

Out of scope:

- Hosted collaboration.
- Access control and identities beyond local `created_by` metadata.
- Archive generation UI.
- Raw-data redistribution policy beyond explicit include/exclude flags.
- Import/merge of a collaborator archive.

## Archive Manifest

`project_archive_manifest.json` is the root descriptor for a shareable archive.
It must be stored inside the archive and may also be kept beside the archive ZIP
for quick inspection.

Required sections:

- `schema_version`: currently `1`.
- `manifest_kind`: `project_archive_manifest`.
- `archive_id`: stable archive id.
- `created_at_utc`: creation timestamp.
- `created_by`: local user or tool identity when available.
- `immutability`: snapshot and content-addressing rules.
- `project`: project, experiment, dataset, run, and template ids in scope.
- `included_data_policy`: what categories are included.
- `excluded_data_policy`: what categories are intentionally omitted.
- `entries`: archive file entries with paths, kind, size, and checksum.
- `checksums`: archive-level checksum metadata.
- `diagnostics`: structured warnings.

## Included Data Policy

Preview snapshots default to reviewable metadata rather than redistributing raw
participant data.

The included policy has explicit booleans:

- `include_raw_uploads`: whether raw EEG/event/sidecar uploads are bundled.
- `include_derivatives`: whether derived FIF or other heavy analysis outputs are
  bundled.
- `include_reports`: must be true for a useful collaboration snapshot.
- `include_manifests`: must be true; artifact manifests are the review spine.
- `include_provenance`: must be true; reviewers need source and config lineage.

When raw uploads or derivatives are excluded, the archive can still support
review of reports, QC summaries, manifests, config snapshots, and lineage, but
it cannot reproduce the full analysis without separately shared data.

## Excluded Data Policy

The excluded policy records intentional omissions. Supported categories are:

- `raw_eeg`
- `event_logs`
- `sidecars`
- `derived_fif`
- `local_logs`
- `runtime_cache`
- `secrets`

Archives must never include `secrets`, local runtime cache, worker stdout/stderr
logs, `.env` files, or machine-specific app state unless a future contract
explicitly defines a redaction path.

If participant data is excluded, the manifest should include a warning such as
`raw_data_excluded` so reviewers know the archive is inspection-only rather than
rerunnable.

## Checksum Contract

Every `entries[]` item must include:

- `archive_path`: path inside the archive, using forward slashes.
- `source_path`: original local path or `null` when not available.
- `entry_kind`: controlled entry type.
- `dataset_id`: dataset id or `null`.
- `run_id`: run id or `null`.
- `logical_name`: stable logical name.
- `size_bytes`: byte size of the archived file.
- `checksum_sha256`: SHA-256 digest of the archived file bytes.

The manifest also includes:

- `checksums.algorithm`: `sha256`.
- `checksums.entry_count`: must equal `entries.length`.
- `checksums.manifest_payload_digest_sha256`: digest of the canonical manifest
  payload before embedding an archive digest.
- `checksums.archive_digest_sha256`: digest of the final archive ZIP when the
  ZIP exists; `null` is allowed for manifest-only planning.

The archive digest cannot be used to mutate entries in place. If content changes,
create a new `archive_id` and a new manifest.

## Immutability

Collaboration snapshots are immutable:

- `immutability.snapshot` must be true.
- `immutability.content_addressed` must be true.
- `immutability.mutation_policy` must be `append_new_archive_only`.
- Existing manifests must not be rewritten to represent new content.

If a researcher exports a corrected report or newly approved artifact action,
that produces a new archive snapshot. The old archive remains valid and
reviewable.

## Relationship To Existing Artifacts

This contract builds on existing Phase D/E artifacts:

- `artifact_manifest.json` remains the per-run artifact authority.
- `analysis_report.json` remains the human-readable run report.
- `export_bundle_manifest.json` remains the ERP-run ZIP manifest.
- `reproducibility_graph` remains the run lineage graph.

The project archive manifest references or includes those artifacts, but it does
not replace them.

## Validation Rules

Consumers should reject an archive manifest when:

- `schema_version` is unsupported.
- `manifest_kind` is not `project_archive_manifest`.
- `checksums.algorithm` is not `sha256`.
- `checksums.entry_count` does not equal `entries.length`.
- An entry checksum is missing or malformed.
- `archive_path` is absolute or escapes the archive root.
- `excluded_data_policy.excluded_categories` omits `secrets`.

Consumers should warn, not reject, when:

- raw data is excluded.
- derived data is excluded.
- archive digest is `null` because only manifest planning was generated.
- source paths are missing but archived entries have valid checksums.
