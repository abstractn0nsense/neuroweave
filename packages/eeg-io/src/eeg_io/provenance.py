from typing import Any


PROVENANCE_SCHEMA_VERSION = 1


def build_provenance_payload(
    *,
    run_id: str,
    dataset_id: str,
    run_kind: str,
    config_snapshot: dict[str, Any],
    sources: list[dict[str, Any]],
    artifacts: list[dict[str, Any]],
    software_versions: dict[str, str],
    created_at_utc: str,
) -> dict[str, Any]:
    return {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "created_at_utc": created_at_utc,
        "run": {
            "run_id": run_id,
            "dataset_id": dataset_id,
            "run_kind": run_kind,
        },
        "sources": sources,
        "config_snapshot": config_snapshot,
        "software_versions": software_versions,
        "artifacts": artifacts,
    }
