from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Sequence

from eeg_core.domain import (
    ArtifactHandlingConfig,
    BadChannelDetectionConfig,
    BadChannelInterpolationConfig,
    EpochConfig,
    ErpConfig,
    EventColumnMapping,
    EventLog,
    NormalizedEvent,
    IcaConfig,
    PreprocessingConfig,
    PreprocessingQcConfig,
    diagnostic_warnings_from_strings,
)
from eeg_processing.epoching import EpochingError, epoch_preprocessed_eeg
from eeg_processing.erp import ErpError, generate_erps_from_epochs
from eeg_processing.preprocessing import PreprocessingError, preprocess_raw_eeg


SCHEMA_VERSION = 1
PREPROCESSING_JOB = "preprocessing"
EPOCHING_JOB = "epoching"
ERP_JOB = "erp"
SUPPORTED_JOBS = {PREPROCESSING_JOB, EPOCHING_JOB, ERP_JOB}


class WorkerCliError(Exception):
    pass


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run EEG processing worker jobs.")
    parser.add_argument("job", choices=sorted(SUPPORTED_JOBS))
    parser.add_argument("--payload", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        payload = load_payload(args.payload)
        payload_job = payload.get("job")
        if payload_job != args.job:
            raise WorkerCliError(
                f"CLI job {args.job!r} does not match payload job {payload_job!r}."
            )
        exit_code, result = run_payload(payload)
    except Exception as exc:
        exit_code = 1
        result = _base_result(
            {
                "schema_version": SCHEMA_VERSION,
                "job": args.job,
                "run_id": None,
            },
            status="failed",
            error=str(exc),
        )

    write_result(args.result, result)
    return exit_code


def load_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WorkerCliError(f"Invalid payload JSON: {exc}") from exc
    except OSError as exc:
        raise WorkerCliError(f"Could not read payload file: {exc}") from exc

    if not isinstance(payload, dict):
        raise WorkerCliError("Payload must be a JSON object.")
    return payload


def write_result(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run_payload(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    validation_error = _payload_validation_error(payload)
    if validation_error is not None:
        return (
            1,
            _base_result(payload, status="failed", error=validation_error),
        )

    job = str(payload["job"])
    return _run_supported_payload(job, payload)


def _run_supported_payload(
    job: str,
    payload: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    if job == PREPROCESSING_JOB:
        return _run_preprocessing_payload(payload)
    if job == EPOCHING_JOB:
        return _run_epoching_payload(payload)
    if job == ERP_JOB:
        return _run_erp_payload(payload)
    return _unimplemented_job_result(job, payload)


def _unimplemented_job_result(
    job: str,
    payload: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    return (
        1,
        _base_result(
            payload,
            status="failed",
            error=f"Worker job is not implemented yet: {job}",
        ),
    )


def _payload_validation_error(payload: dict[str, Any]) -> str | None:
    schema_version = payload.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        return f"Unsupported worker payload schema_version: {schema_version!r}"

    job = payload.get("job")
    if not isinstance(job, str) or not job:
        return "Payload job must be a non-empty string."
    if job not in SUPPORTED_JOBS:
        return f"Unsupported worker job: {job}"

    run_id = payload.get("run_id")
    if run_id is not None and not isinstance(run_id, str):
        return "Payload run_id must be a string or null."

    return None


def _run_preprocessing_payload(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    try:
        input_path = _required_path(payload, "input_path")
        output_path = _required_path(payload, "output_path")
        config = _preprocessing_config_from_payload(payload.get("config", {}))
        metadata = preprocess_raw_eeg(input_path, output_path, config)
    except WorkerCliError as exc:
        return (
            1,
            _base_result(
                payload,
                status="failed",
                error=str(exc),
            ),
        )
    except PreprocessingError as exc:
        return (
            1,
            _base_result(
                payload,
                status="failed",
                warnings=exc.processing_warnings,
                error=str(exc),
            ),
        )
    except Exception as exc:
        return (
            1,
            _base_result(
                payload,
                status="failed",
                error=f"Preprocessing worker failed: {exc}",
            ),
        )

    return (
        0,
        _base_result(payload, status="completed", metadata=metadata),
    )


def _run_epoching_payload(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    try:
        input_path = _required_path(payload, "input_path")
        output_path = _required_path(payload, "output_path")
        config = _epoch_config_from_payload(payload.get("config"))
        event_log = _event_log_from_payload(payload.get("event_log"))
        metadata = epoch_preprocessed_eeg(
            input_path=input_path,
            output_path=output_path,
            event_log=event_log,
            config=config,
            preprocessing_run_id=config.preprocessing_run_id,
        )
    except WorkerCliError as exc:
        return (
            1,
            _base_result(
                payload,
                status="failed",
                error=str(exc),
            ),
        )
    except EpochingError as exc:
        return (
            1,
            _base_result(
                payload,
                status="failed",
                warnings=exc.processing_warnings,
                error=str(exc),
            ),
        )
    except Exception as exc:
        return (
            1,
            _base_result(
                payload,
                status="failed",
                error=f"Epoching worker failed: {exc}",
            ),
        )

    return (
        0,
        _base_result(payload, status="completed", metadata=metadata),
    )


def _run_erp_payload(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    try:
        epochs_path = _required_path(payload, "epochs_path")
        output_directory = _required_path(payload, "output_directory")
        config = _erp_config_from_payload(payload.get("config"))
        metadata = generate_erps_from_epochs(
            epochs_path=epochs_path,
            output_directory=output_directory,
            config=config,
        )
    except WorkerCliError as exc:
        return (
            1,
            _base_result(
                payload,
                status="failed",
                error=str(exc),
            ),
        )
    except ErpError as exc:
        return (
            1,
            _base_result(
                payload,
                status="failed",
                warnings=exc.processing_warnings,
                error=str(exc),
            ),
        )
    except Exception as exc:
        return (
            1,
            _base_result(
                payload,
                status="failed",
                error=f"ERP worker failed: {exc}",
            ),
        )

    return (
        0,
        _base_result(payload, status="completed", metadata=metadata),
    )


def _required_path(payload: dict[str, Any], key: str) -> Path:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise WorkerCliError(f"Payload {key} must be a non-empty string.")
    return Path(value)


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise WorkerCliError(f"Payload {key} must be a non-empty string.")
    return value


def _required_float(payload: dict[str, Any], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool):
        raise WorkerCliError(f"Payload {key} must be a number.")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise WorkerCliError(f"Payload {key} must be a number.") from exc


def _preprocessing_config_from_payload(value: Any) -> PreprocessingConfig:
    if not isinstance(value, dict):
        raise WorkerCliError("Payload config must be a JSON object.")

    bad_channel_detection = _optional_config_object(
        value.get("bad_channel_detection"),
        "bad_channel_detection",
    )
    bad_channel_interpolation = _optional_config_object(
        value.get("bad_channel_interpolation"),
        "bad_channel_interpolation",
    )
    ica = _optional_config_object(value.get("ica"), "ica")
    artifact_handling = _optional_config_object(
        value.get("artifact_handling"),
        "artifact_handling",
    )
    qc = _optional_config_object(value.get("qc"), "qc")
    return PreprocessingConfig(
        artifact_schema_version=int(
            _optional_float(value.get("artifact_schema_version"), "artifact_schema_version")
            or 1
        ),
        high_pass_hz=_optional_float(value.get("high_pass_hz"), "high_pass_hz"),
        low_pass_hz=_optional_float(value.get("low_pass_hz"), "low_pass_hz"),
        notch_hz=_optional_float(value.get("notch_hz"), "notch_hz"),
        resample_hz=_optional_float(value.get("resample_hz"), "resample_hz"),
        reference=_optional_string(value.get("reference"), "reference"),
        manual_bad_channels=_string_list(
            value.get("manual_bad_channels"),
            "manual_bad_channels",
        ),
        bad_channel_detection=BadChannelDetectionConfig(
            enabled=_bool_or_default(
                bad_channel_detection.get("enabled"),
                "bad_channel_detection.enabled",
                False,
            ),
            method=_optional_string(
                bad_channel_detection.get("method"),
                "bad_channel_detection.method",
            )
            or "none",
            minimum_correlation=_optional_float(
                bad_channel_detection.get("minimum_correlation"),
                "bad_channel_detection.minimum_correlation",
            ),
            zscore_threshold=_optional_float(
                bad_channel_detection.get("zscore_threshold"),
                "bad_channel_detection.zscore_threshold",
            ),
        ),
        bad_channel_interpolation=BadChannelInterpolationConfig(
            enabled=_bool_or_default(
                bad_channel_interpolation.get("enabled"),
                "bad_channel_interpolation.enabled",
                False,
            ),
            reset_bads=_bool_or_default(
                bad_channel_interpolation.get("reset_bads"),
                "bad_channel_interpolation.reset_bads",
                True,
            ),
        ),
        ica=IcaConfig(
            enabled=_bool_or_default(ica.get("enabled"), "ica.enabled", False),
            method=_optional_string(ica.get("method"), "ica.method") or "fastica",
            n_components=_optional_number(ica.get("n_components"), "ica.n_components"),
            random_state=int(
                _optional_float(ica.get("random_state"), "ica.random_state") or 97
            ),
            max_iter=_max_iter_value(ica.get("max_iter")),
            exclude_components=_int_list(
                ica.get("exclude_components"),
                "ica.exclude_components",
            ),
            eog_channels=_string_list(ica.get("eog_channels"), "ica.eog_channels"),
            ecg_channels=_string_list(ica.get("ecg_channels"), "ica.ecg_channels"),
        ),
        artifact_handling=ArtifactHandlingConfig(
            eog_enabled=_bool_or_default(
                artifact_handling.get("eog_enabled"),
                "artifact_handling.eog_enabled",
                False,
            ),
            ecg_enabled=_bool_or_default(
                artifact_handling.get("ecg_enabled"),
                "artifact_handling.ecg_enabled",
                False,
            ),
            eog_channels=_string_list(
                artifact_handling.get("eog_channels"),
                "artifact_handling.eog_channels",
            ),
            ecg_channels=_string_list(
                artifact_handling.get("ecg_channels"),
                "artifact_handling.ecg_channels",
            ),
            create_annotations=_bool_or_default(
                artifact_handling.get("create_annotations"),
                "artifact_handling.create_annotations",
                True,
            ),
        ),
        qc=PreprocessingQcConfig(
            enabled=_bool_or_default(qc.get("enabled"), "qc.enabled", True),
            include_before_after=_bool_or_default(
                qc.get("include_before_after"),
                "qc.include_before_after",
                True,
            ),
            metrics=_string_list(
                qc.get("metrics"),
                "qc.metrics",
                default=["channel_status", "amplitude", "annotations"],
            ),
        ),
    )


def _epoch_config_from_payload(value: Any) -> EpochConfig:
    if not isinstance(value, dict):
        raise WorkerCliError("Payload config must be a JSON object.")

    return EpochConfig(
        preprocessing_run_id=_required_string(value, "preprocessing_run_id"),
        condition_field=_required_string(value, "condition_field"),
        tmin_seconds=_required_float(value, "tmin_seconds"),
        tmax_seconds=_required_float(value, "tmax_seconds"),
        baseline_start_seconds=_optional_float(
            value.get("baseline_start_seconds"),
            "baseline_start_seconds",
        ),
        baseline_end_seconds=_optional_float(
            value.get("baseline_end_seconds"),
            "baseline_end_seconds",
        ),
        reject_eeg_uv=_optional_float(value.get("reject_eeg_uv"), "reject_eeg_uv"),
    )


def _event_log_from_payload(value: Any) -> EventLog:
    if not isinstance(value, dict):
        raise WorkerCliError("Payload event_log must be a JSON object.")

    events = value.get("events", [])
    if not isinstance(events, list):
        raise WorkerCliError("Payload event_log.events must be a list.")

    mapping = value.get("mapping", {})
    if not isinstance(mapping, dict):
        raise WorkerCliError("Payload event_log.mapping must be a JSON object.")

    provenance = value.get("provenance", {})
    return EventLog(
        event_log_id=_required_string(value, "event_log_id"),
        dataset_id=_required_string(value, "dataset_id"),
        file_id=_required_string(value, "file_id"),
        mapping=EventColumnMapping(
            onset_seconds=_optional_string(mapping.get("onset_seconds"), "onset_seconds"),
            duration_seconds=_optional_string(
                mapping.get("duration_seconds"),
                "duration_seconds",
            ),
            trial_type=_optional_string(mapping.get("trial_type"), "trial_type"),
            stimulus=_optional_string(mapping.get("stimulus"), "stimulus"),
            response=_optional_string(mapping.get("response"), "response"),
            correct=_optional_string(mapping.get("correct"), "correct"),
            reaction_time_seconds=_optional_string(
                mapping.get("reaction_time_seconds"),
                "reaction_time_seconds",
            ),
        ),
        row_count=int(_required_float(value, "row_count")),
        filter_count=int(value.get("filter_count", 0)),
        provenance=dict(provenance) if isinstance(provenance, dict) else {},
        events=[_normalized_event_from_payload(event) for event in events],
    )


def _erp_config_from_payload(value: Any) -> ErpConfig:
    if not isinstance(value, dict):
        raise WorkerCliError("Payload config must be a JSON object.")

    return ErpConfig(
        epoch_run_id=_required_string(value, "epoch_run_id"),
        conditions=_optional_string_list(value.get("conditions"), "conditions"),
        picks=_optional_string_list(value.get("picks"), "picks"),
        method=_optional_string(value.get("method"), "method") or "mean",
        plot_mode=_optional_string(value.get("plot_mode"), "plot_mode") or "gfp",
        plot_channel=_optional_string(value.get("plot_channel"), "plot_channel"),
    )


def _optional_string_list(value: Any, field_name: str) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise WorkerCliError(f"Payload config {field_name} must be a list or null.")
    return [str(item) for item in value]


def _optional_config_object(value: Any, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise WorkerCliError(f"Payload config {field_name} must be a JSON object.")
    return value


def _string_list(
    value: Any,
    field_name: str,
    *,
    default: list[str] | None = None,
) -> list[str]:
    if value is None:
        return list(default or [])
    if not isinstance(value, list):
        raise WorkerCliError(f"Payload config {field_name} must be a list.")
    return [str(item) for item in value]


def _int_list(value: Any, field_name: str) -> list[int]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise WorkerCliError(f"Payload config {field_name} must be a list.")
    try:
        return [int(item) for item in value]
    except (TypeError, ValueError) as exc:
        raise WorkerCliError(
            f"Payload config {field_name} must contain integers."
        ) from exc


def _optional_number(value: Any, field_name: str) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise WorkerCliError(f"Payload config {field_name} must be a number or null.")
    if isinstance(value, int):
        return value
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise WorkerCliError(
            f"Payload config {field_name} must be a number or null."
        ) from exc


def _bool_or_default(value: Any, field_name: str, default: bool) -> bool:
    parsed = _optional_bool(value, field_name)
    return default if parsed is None else parsed


def _max_iter_value(value: Any) -> int | str:
    if value is None:
        return "auto"
    if value == "auto":
        return "auto"
    if isinstance(value, bool):
        raise WorkerCliError("Payload config ica.max_iter must be an integer or auto.")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise WorkerCliError(
            "Payload config ica.max_iter must be an integer or auto."
        ) from exc


def _normalized_event_from_payload(value: Any) -> NormalizedEvent:
    if not isinstance(value, dict):
        raise WorkerCliError("Payload event_log.events entries must be JSON objects.")

    return NormalizedEvent(
        onset_seconds=_required_float(value, "onset_seconds"),
        source_row=int(_required_float(value, "source_row")),
        duration_seconds=_optional_float(
            value.get("duration_seconds"),
            "duration_seconds",
        ),
        trial_type=_optional_string(value.get("trial_type"), "trial_type"),
        stimulus=_optional_string(value.get("stimulus"), "stimulus"),
        response=_optional_string(value.get("response"), "response"),
        correct=_optional_bool(value.get("correct"), "correct"),
        reaction_time_seconds=_optional_float(
            value.get("reaction_time_seconds"),
            "reaction_time_seconds",
        ),
    )


def _optional_float(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise WorkerCliError(f"Payload config {field_name} must be a number or null.")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise WorkerCliError(
            f"Payload config {field_name} must be a number or null."
        ) from exc


def _optional_string(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise WorkerCliError(f"Payload config {field_name} must be a string or null.")
    return value


def _optional_bool(value: Any, field_name: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise WorkerCliError(f"Payload {field_name} must be a boolean or null.")
    return value


def _base_result(
    payload: dict[str, Any],
    *,
    status: str,
    metadata: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    warning_values = warnings if warnings is not None else _metadata_warnings(metadata)
    return {
        "schema_version": SCHEMA_VERSION,
        "job": payload.get("job"),
        "run_id": payload.get("run_id"),
        "status": status,
        "metadata": metadata or {},
        "warnings": warning_values,
        "diagnostics": _diagnostics_payload_from_warnings(
            warning_values,
            source=_warning_source_from_payload(payload),
        ),
        "error": error,
    }


def _diagnostics_payload_from_warnings(
    warnings: list[str],
    *,
    source: str,
) -> dict[str, list[dict[str, Any]]]:
    diagnostics = diagnostic_warnings_from_strings(warnings, source=source)
    structured_warnings = diagnostics.get("warnings", [])
    return {
        "warnings": [asdict(warning) for warning in structured_warnings]
    }


def _metadata_warnings(metadata: dict[str, Any] | None) -> list[str]:
    if not isinstance(metadata, dict):
        return []
    warnings = metadata.get("warnings", [])
    if not isinstance(warnings, list):
        return []
    return [str(warning) for warning in warnings]


def _warning_source_from_payload(payload: dict[str, Any]) -> str:
    return "worker"


if __name__ == "__main__":
    raise SystemExit(main())
