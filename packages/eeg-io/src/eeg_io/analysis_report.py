from pathlib import Path
from typing import Any
from datetime import datetime, timezone
import json

from eeg_io.artifact_manifest import ArtifactReference, load_artifact_manifest
from eeg_io.qc_summary import build_qc_summary


ANALYSIS_REPORT_SCHEMA_VERSION = 1


class AnalysisReportError(Exception):
    pass


def build_analysis_report(
    *,
    dataset_id: str,
    run_id: str,
    run_kind: str,
    artifact_manifest_path: Path,
    config_snapshot: dict[str, Any] | None = None,
    extra_sections: dict[str, Any] | None = None,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    manifest = load_artifact_manifest(artifact_manifest_path)
    provenance, provenance_warnings = _read_provenance(manifest.artifacts)
    qc_summary = build_qc_summary(artifact_manifest_path)
    effective_config = (
        config_snapshot
        if config_snapshot is not None
        else _dict_value(provenance, "config_snapshot")
    )

    report = {
        "schema_version": ANALYSIS_REPORT_SCHEMA_VERSION,
        "created_at_utc": created_at_utc or _utc_now_iso(),
        "dataset_id": dataset_id,
        "run_id": run_id,
        "run_kind": run_kind,
        "config_snapshot": effective_config,
        "provenance": provenance,
        "qc_summary": qc_summary,
        "diagnostics": {
            "warnings": [
                *provenance_warnings,
                *[
                    {
                        "code": "artifact_missing",
                        "severity": "warning",
                        "source": "analysis_report",
                        "impact": (
                            f"Artifact {artifact.logical_name!r} is listed in the "
                            "manifest but was not found."
                        ),
                        "suggested_action": (
                            "Regenerate the source run artifact or rebuild the "
                            "artifact manifest."
                        ),
                    }
                    for artifact in manifest.missing_artifacts
                ],
            ],
        },
        "artifact_manifest": {
            "schema_version": manifest.schema_version,
            "artifact_root": str(manifest.artifact_root),
            "artifact_count": manifest.artifact_count,
            "artifacts": [
                _artifact_report_entry(artifact)
                for artifact in manifest.artifacts
            ],
            "missing_artifacts": [
                _artifact_report_entry(artifact)
                for artifact in manifest.missing_artifacts
            ],
        },
    }
    if extra_sections:
        report.update(extra_sections)
    return report


def write_analysis_report(
    output_path: Path,
    *,
    dataset_id: str,
    run_id: str,
    run_kind: str,
    artifact_manifest_path: Path,
    config_snapshot: dict[str, Any] | None = None,
    extra_sections: dict[str, Any] | None = None,
    created_at_utc: str | None = None,
) -> Path:
    payload = build_analysis_report(
        dataset_id=dataset_id,
        run_id=run_id,
        run_kind=run_kind,
        artifact_manifest_path=artifact_manifest_path,
        config_snapshot=config_snapshot,
        extra_sections=extra_sections,
        created_at_utc=created_at_utc,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def _read_provenance(
    artifacts: list[ArtifactReference],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    provenance_artifact = next(
        (
            artifact
            for artifact in artifacts
            if artifact.logical_name == "provenance" and artifact.exists
        ),
        None,
    )
    if provenance_artifact is None:
        return {}, [
            {
                "code": "provenance_missing",
                "severity": "warning",
                "source": "analysis_report",
                "impact": "No provenance artifact was found in the artifact manifest.",
                "suggested_action": (
                    "Run the analysis with provenance-enabled output metadata."
                ),
            }
        ]

    try:
        payload = json.loads(provenance_artifact.path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AnalysisReportError(f"Invalid provenance JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise AnalysisReportError("Provenance artifact must be a JSON object.")
    return payload, []


def _artifact_report_entry(artifact: ArtifactReference) -> dict[str, Any]:
    return {
        "logical_name": artifact.logical_name,
        "artifact_type": artifact.artifact_type,
        "path": str(artifact.path),
        "size_bytes": artifact.size_bytes,
        "checksum_sha256": artifact.checksum_sha256,
        "created_at_utc": artifact.created_at_utc,
        "exists": artifact.exists,
    }


def _dict_value(value: dict[str, Any], key: str) -> dict[str, Any]:
    item = value.get(key)
    return item if isinstance(item, dict) else {}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
