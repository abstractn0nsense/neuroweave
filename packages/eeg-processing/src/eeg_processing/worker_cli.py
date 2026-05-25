from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from eeg_core.domain import PreprocessingConfig
from eeg_processing.preprocessing import PreprocessingError, preprocess_raw_eeg


SCHEMA_VERSION = 1
PREPROCESSING_JOB = "preprocessing"
SUPPORTED_JOBS = {PREPROCESSING_JOB}


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
    if job == PREPROCESSING_JOB:
        return _run_preprocessing_payload(payload)

    return (
        1,
        _base_result(
            payload,
            status="failed",
            error=f"Unsupported worker job: {job}",
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


def _required_path(payload: dict[str, Any], key: str) -> Path:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise WorkerCliError(f"Payload {key} must be a non-empty string.")
    return Path(value)


def _preprocessing_config_from_payload(value: Any) -> PreprocessingConfig:
    if not isinstance(value, dict):
        raise WorkerCliError("Payload config must be a JSON object.")

    return PreprocessingConfig(
        high_pass_hz=_optional_float(value.get("high_pass_hz"), "high_pass_hz"),
        low_pass_hz=_optional_float(value.get("low_pass_hz"), "low_pass_hz"),
        notch_hz=_optional_float(value.get("notch_hz"), "notch_hz"),
        resample_hz=_optional_float(value.get("resample_hz"), "resample_hz"),
        reference=_optional_string(value.get("reference"), "reference"),
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


def _base_result(
    payload: dict[str, Any],
    *,
    status: str,
    metadata: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "job": payload.get("job"),
        "run_id": payload.get("run_id"),
        "status": status,
        "metadata": metadata or {},
        "warnings": warnings or [],
        "error": error,
    }


if __name__ == "__main__":
    raise SystemExit(main())
