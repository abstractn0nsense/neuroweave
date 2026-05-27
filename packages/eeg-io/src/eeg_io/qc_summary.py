from pathlib import Path
from typing import Any
import json

from eeg_io.artifact_manifest import ArtifactManifest, ArtifactReference, load_artifact_manifest


QC_SUMMARY_SCHEMA_VERSION = 1


class QcSummaryError(Exception):
    pass


def build_qc_summary(manifest_path: Path) -> dict[str, Any]:
    manifest = load_artifact_manifest(manifest_path)
    artifacts = {artifact.logical_name: artifact for artifact in manifest.artifacts}
    run_kind = _infer_run_kind(artifacts)
    summary: dict[str, Any] = {
        "schema_version": QC_SUMMARY_SCHEMA_VERSION,
        "run_kind": run_kind,
        "artifact_manifest": _manifest_summary(manifest),
    }

    if run_kind == "preprocessing":
        summary["preprocessing"] = _preprocessing_qc(artifacts)
    elif run_kind == "epoch":
        summary["epoch"] = _epoch_qc(artifacts)
    elif run_kind == "erp":
        summary["erp"] = _erp_qc(artifacts)
    else:
        summary["unknown"] = {
            "available_artifacts": sorted(artifacts),
        }

    return summary


def _infer_run_kind(artifacts: dict[str, ArtifactReference]) -> str:
    logical_names = set(artifacts)
    if {"preprocessing_summary", "filter_report"} & logical_names:
        return "preprocessing"
    if {"epoch_summary", "condition_counts", "drop_log"} & logical_names:
        return "epoch"
    if "erp_metadata" in logical_names:
        return "erp"
    return "unknown"


def _manifest_summary(manifest: ArtifactManifest) -> dict[str, Any]:
    return {
        "schema_version": manifest.schema_version,
        "artifact_root": str(manifest.artifact_root),
        "artifact_count": manifest.artifact_count,
        "missing_artifacts": [
            _artifact_summary(artifact)
            for artifact in manifest.missing_artifacts
        ],
    }


def _artifact_summary(artifact: ArtifactReference) -> dict[str, Any]:
    return {
        "logical_name": artifact.logical_name,
        "artifact_type": artifact.artifact_type,
        "path": str(artifact.path),
        "exists": artifact.exists,
    }


def _preprocessing_qc(artifacts: dict[str, ArtifactReference]) -> dict[str, Any]:
    preprocessing_summary = _read_json_artifact(
        artifacts,
        "preprocessing_summary",
        default={},
    )
    filter_report = _read_json_artifact(artifacts, "filter_report", default={})
    artifact_summary = _read_json_artifact(artifacts, "artifact_summary", default={})

    output_artifact = _dict_value(artifact_summary, "output")
    input_artifact = _dict_value(artifact_summary, "input")
    bad_channels = _dict_value(artifact_summary, "bad_channels")
    artifact_rejection = _dict_value(artifact_summary, "artifact_rejection")
    ica = _dict_value(artifact_summary, "ica")
    before_after = _dict_value(_dict_value(artifact_summary, "qc"), "before_after")
    bad_channel_report = _read_json_artifact(
        artifacts,
        "bad_channel_report",
        default=bad_channels,
    )
    artifact_rejection_report = _read_json_artifact(
        artifacts,
        "artifact_rejection_report",
        default=artifact_rejection,
    )
    ica_report = _read_json_artifact(
        artifacts,
        "ica_report",
        default=ica,
    )
    before_after_qc = _read_json_artifact(
        artifacts,
        "before_after_qc",
        default=before_after,
    )
    return {
        "summary": preprocessing_summary,
        "filters": {
            "high_pass": filter_report.get("high_pass"),
            "low_pass": filter_report.get("low_pass"),
            "notch": filter_report.get("notch"),
        },
        "reference": filter_report.get("reference"),
        "resample": filter_report.get("resample"),
        "channel_status": {
            "input_bad_channels": input_artifact.get("bad_channels", []),
            "input_bad_channel_count": input_artifact.get("bad_channel_count", 0),
            "output_bad_channels": output_artifact.get("bad_channels", []),
            "output_bad_channel_count": output_artifact.get("bad_channel_count", 0),
        },
        "bad_channel_detection": _dict_value(bad_channels, "detection"),
        "bad_channel_interpolation": _dict_value(bad_channels, "interpolation"),
        "artifact_rejection": artifact_rejection,
        "ica": ica,
        "before_after": before_after,
        "phase_b_artifacts": {
            "bad_channel_report": bad_channel_report,
            "artifact_rejection_report": artifact_rejection_report,
            "ica_report": ica_report,
            "before_after_qc": before_after_qc,
        },
    }


def _epoch_qc(artifacts: dict[str, ArtifactReference]) -> dict[str, Any]:
    epoch_summary = _read_json_artifact(artifacts, "epoch_summary", default={})
    condition_counts = _read_json_artifact(artifacts, "condition_counts", default={})
    drop_log = _read_json_artifact(artifacts, "drop_log", default={})

    return {
        "summary": epoch_summary,
        "condition_counts": condition_counts,
        "drop_log": {
            "summary": drop_log.get("summary", {}),
            "entry_count": len(drop_log.get("entries", []))
            if isinstance(drop_log.get("entries"), list)
            else 0,
        },
        "out_of_bounds": _dict_value(epoch_summary, "skipped_events"),
    }


def _erp_qc(artifacts: dict[str, ArtifactReference]) -> dict[str, Any]:
    erp_metadata = _read_json_artifact(artifacts, "erp_metadata", default={})
    conditions = erp_metadata.get("conditions", [])
    if not isinstance(conditions, list):
        conditions = []

    return {
        "metadata": erp_metadata,
        "condition_count": erp_metadata.get("condition_count", len(conditions)),
        "plot_status": _dict_value(erp_metadata, "plot").get(
            "status",
            erp_metadata.get("plot_status"),
        ),
        "conditions": [
            _erp_condition_qc(condition)
            for condition in conditions
            if isinstance(condition, dict)
        ],
    }


def _erp_condition_qc(condition: dict[str, Any]) -> dict[str, Any]:
    channel_summary = _dict_value(condition, "channel_time_summary")
    return {
        "condition": condition.get("condition"),
        "nave": condition.get("nave"),
        "gfp_peak": condition.get("gfp_peak"),
        "channel_peak": condition.get("channel_peak"),
        "channel_time_summary": channel_summary,
        "plot_status": condition.get("plot_status"),
        "plot_mode": condition.get("plot_mode"),
        "plot_channel": condition.get("plot_channel"),
        "plot_warnings": condition.get("plot_warnings", []),
    }


def _read_json_artifact(
    artifacts: dict[str, ArtifactReference],
    logical_name: str,
    *,
    default: dict[str, Any],
) -> dict[str, Any]:
    artifact = artifacts.get(logical_name)
    if artifact is None or not artifact.exists:
        return default
    try:
        payload = json.loads(artifact.path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise QcSummaryError(
            f"Invalid QC artifact JSON for {logical_name}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise QcSummaryError(f"QC artifact {logical_name} must be a JSON object.")
    return payload


def _dict_value(value: dict[str, Any], key: str) -> dict[str, Any]:
    item = value.get(key)
    return item if isinstance(item, dict) else {}
