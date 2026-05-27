from pathlib import Path
from typing import Any, Callable
from dataclasses import asdict
import warnings as python_warnings

from eeg_core.domain import PreprocessingConfig


class PreprocessingError(Exception):
    def __init__(self, message: str, processing_warnings: list[str] | None = None):
        super().__init__(message)
        self.processing_warnings = processing_warnings or []


CancelCheck = Callable[[], bool]


def preprocess_raw_eeg(
    input_path: Path,
    output_path: Path,
    config: PreprocessingConfig,
    should_cancel: CancelCheck | None = None,
) -> dict[str, Any]:
    manual_warnings: list[str] = []
    warning_records: list[python_warnings.WarningMessage] = []
    filter_report: dict[str, Any] = {
        "high_pass": _operation_report(
            enabled=config.high_pass_hz is not None,
            parameters={"cutoff_hz": config.high_pass_hz},
        ),
        "low_pass": _operation_report(
            enabled=config.low_pass_hz is not None,
            parameters={"cutoff_hz": config.low_pass_hz},
        ),
        "notch": _operation_report(
            enabled=config.notch_hz is not None,
            parameters={"frequency_hz": config.notch_hz},
        ),
        "reference": _operation_report(
            enabled=bool(config.reference),
            parameters={"reference": config.reference},
        ),
        "resample": _operation_report(
            enabled=config.resample_hz is not None,
            parameters={"target_sampling_rate_hz": config.resample_hz},
        ),
    }
    contract_warnings = _artifact_contract_warnings(config)
    try:
        with python_warnings.catch_warnings(record=True) as warning_records:
            python_warnings.simplefilter("always")

            _check_cancelled(should_cancel, manual_warnings)
            raw = _read_raw(input_path)
            _check_cancelled(should_cancel, manual_warnings)
            input_sampling_rate = float(raw.info["sfreq"])
            input_channel_count = len(raw.ch_names)
            input_duration = (
                raw.n_times / input_sampling_rate if input_sampling_rate else 0
            )
            input_artifact_summary = _artifact_summary(raw)
            input_qc_snapshot = _qc_snapshot(raw)
            manual_bad_channels = _apply_manual_bad_channels(raw, config)
            _check_cancelled(should_cancel, manual_warnings)
            bad_channel_detection = _bad_channel_detection_report(raw, config)
            manual_warnings.extend(bad_channel_detection.get("warnings", []))
            _check_cancelled(should_cancel, manual_warnings)
            bad_channel_interpolation = _interpolate_bad_channels(raw, config)
            manual_warnings.extend(bad_channel_interpolation.get("warnings", []))
            _check_cancelled(should_cancel, manual_warnings)

            if config.high_pass_hz is not None or config.low_pass_hz is not None:
                _check_cancelled(should_cancel, manual_warnings)
                raw.filter(
                    l_freq=config.high_pass_hz or None,
                    h_freq=config.low_pass_hz,
                    verbose=False,
                )
                if config.high_pass_hz is not None:
                    filter_report["high_pass"]["status"] = "applied"
                if config.low_pass_hz is not None:
                    filter_report["low_pass"]["status"] = "applied"
                _check_cancelled(should_cancel, manual_warnings)

            if config.notch_hz is not None:
                nyquist = float(raw.info["sfreq"]) / 2
                if config.notch_hz >= nyquist:
                    reason = (
                        f"Skipped notch filter at {config.notch_hz:g} Hz because Nyquist is {nyquist:g} Hz."
                    )
                    manual_warnings.append(reason)
                    filter_report["notch"]["status"] = "skipped"
                    filter_report["notch"]["reason"] = reason
                else:
                    _check_cancelled(should_cancel, manual_warnings)
                    raw.notch_filter(freqs=[config.notch_hz], verbose=False)
                    filter_report["notch"]["status"] = "applied"
                    _check_cancelled(should_cancel, manual_warnings)

            if config.reference:
                reference = config.reference.strip().lower()
                if reference in {"average", "avg"}:
                    _check_cancelled(should_cancel, manual_warnings)
                    raw.set_eeg_reference("average", verbose=False)
                    filter_report["reference"]["status"] = "applied"
                    filter_report["reference"]["parameters"] = {
                        "reference": "average",
                    }
                    _check_cancelled(should_cancel, manual_warnings)
                elif reference in {"none", "original"}:
                    manual_warnings.append("Reference unchanged.")
                    filter_report["reference"]["status"] = "skipped"
                    filter_report["reference"]["reason"] = "Reference unchanged."
                else:
                    channels = [
                        channel.strip()
                        for channel in config.reference.split(",")
                        if channel.strip()
                    ]
                    if channels:
                        _check_cancelled(should_cancel, manual_warnings)
                        raw.set_eeg_reference(channels, verbose=False)
                        filter_report["reference"]["status"] = "applied"
                        filter_report["reference"]["parameters"] = {
                            "reference": channels,
                        }
                        _check_cancelled(should_cancel, manual_warnings)
                    else:
                        filter_report["reference"]["status"] = "skipped"
                        filter_report["reference"]["reason"] = "No reference channels provided."

            if config.resample_hz is not None:
                _check_cancelled(should_cancel, manual_warnings)
                raw.resample(config.resample_hz, verbose=False)
                filter_report["resample"]["status"] = "applied"
                _check_cancelled(should_cancel, manual_warnings)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            _check_cancelled(should_cancel, manual_warnings)
            raw.save(output_path, overwrite=True, verbose=False)
            _check_cancelled(should_cancel, manual_warnings)
    except PreprocessingError as exc:
        raise PreprocessingError(
            str(exc),
            processing_warnings=_dedupe(
                manual_warnings
                + contract_warnings
                + _format_warning_records(warning_records)
                + exc.processing_warnings
            ),
        ) from exc
    except Exception as exc:
        raise PreprocessingError(
            f"Preprocessing failed: {exc}",
            processing_warnings=_dedupe(
                manual_warnings + contract_warnings + _format_warning_records(warning_records)
            ),
        ) from exc

    sampling_rate = float(raw.info["sfreq"])
    output_duration = raw.n_times / sampling_rate if sampling_rate else 0
    output_artifact_summary = _artifact_summary(raw)
    output_qc_snapshot = _qc_snapshot(raw)
    before_after_qc = _before_after_qc_summary(
        config,
        before=input_qc_snapshot,
        after=output_qc_snapshot,
    )
    warnings = _dedupe(
        manual_warnings + contract_warnings + _format_warning_records(warning_records)
    )
    preprocessing_summary = {
        "input": {
            "path": str(input_path),
            "channel_count": input_channel_count,
            "sampling_rate_hz": input_sampling_rate,
            "duration_seconds": input_duration,
        },
        "output": {
            "path": str(output_path),
            "channel_count": len(raw.ch_names),
            "sampling_rate_hz": sampling_rate,
            "duration_seconds": output_duration,
            "file_format": "fif",
        },
        "config": _config_summary(config),
        "warnings": warnings,
    }
    return {
        "channel_count": len(raw.ch_names),
        "sampling_rate_hz": sampling_rate,
        "duration_seconds": output_duration,
        "file_format": "fif",
        "input_sampling_rate_hz": input_sampling_rate,
        "input_duration_seconds": input_duration,
        "mne_version": _mne_version(),
        "warnings": warnings,
        "diagnostics": {
            "preprocessing_summary": preprocessing_summary,
            "filter_report": filter_report,
            "artifact_summary": {
                "schema_version": config.artifact_schema_version,
                "input": input_artifact_summary,
                "output": output_artifact_summary,
                "bad_channels": _bad_channel_contract_summary(
                    config,
                    manual_bad_channels=manual_bad_channels,
                    detection=bad_channel_detection,
                    interpolation=bad_channel_interpolation,
                ),
                "artifact_rejection": {
                    "enabled": False,
                    "schema_version": config.artifact_schema_version,
                    "config": asdict(config.artifact_handling),
                    "reason": "Artifact detection and rejection are configured by contract but not executed in Phase B1.",
                },
                "ica": _ica_contract_summary(config),
                "qc": {
                    "schema_version": config.artifact_schema_version,
                    "config": asdict(config.qc),
                    "status": "completed" if config.qc.enabled else "disabled",
                    "before_after": before_after_qc,
                },
            },
        },
    }


def _read_raw(path: Path):
    import mne

    readers = {
        ".fif": mne.io.read_raw_fif,
        ".edf": mne.io.read_raw_edf,
        ".bdf": mne.io.read_raw_bdf,
        ".vhdr": mne.io.read_raw_brainvision,
        ".set": mne.io.read_raw_eeglab,
    }
    reader = readers.get(path.suffix.lower())
    if reader is None:
        raise PreprocessingError(f"Unsupported EEG file format: {path.suffix}")

    try:
        return reader(path, preload=True, verbose=False)
    except Exception as exc:
        raise PreprocessingError(f"Could not read EEG data: {exc}") from exc


def _mne_version() -> str:
    import mne

    return str(mne.__version__)


def _operation_report(
    enabled: bool,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    return {
        "enabled": enabled,
        "status": "pending" if enabled else "not_requested",
        "parameters": parameters,
    }


def _config_summary(config: PreprocessingConfig) -> dict[str, Any]:
    return asdict(config)


def _artifact_summary(raw: Any) -> dict[str, Any]:
    annotations = getattr(raw, "annotations", [])
    descriptions = [
        str(description)
        for description in getattr(annotations, "description", [])
    ]
    return {
        "bad_channels": [str(channel) for channel in raw.info.get("bads", [])],
        "bad_channel_count": len(raw.info.get("bads", [])),
        "annotation_count": len(annotations),
        "annotation_descriptions": sorted(set(descriptions)),
    }


def _qc_snapshot(raw: Any) -> dict[str, Any]:
    return {
        "channel_status": _channel_status_snapshot(raw),
        "annotations": _annotation_summary(raw),
        "variance": _variance_summary(raw),
        "psd": _psd_summary(raw),
    }


def _annotation_summary(raw: Any) -> dict[str, Any]:
    annotations = getattr(raw, "annotations", [])
    descriptions = [
        str(description)
        for description in getattr(annotations, "description", [])
    ]
    return {
        "count": len(annotations),
        "descriptions": sorted(set(descriptions)),
    }


def _variance_summary(raw: Any) -> dict[str, Any]:
    selected = _eeg_detection_data(raw)
    if selected is None:
        return {
            "channel_count": 0,
            "mean_uv2": None,
            "median_uv2": None,
            "min_uv2": None,
            "max_uv2": None,
            "channels": [],
        }

    channel_names, data = selected
    import numpy as np

    variances_uv2 = np.var(data, axis=1) * 1_000_000_000_000
    return {
        "channel_count": len(channel_names),
        "mean_uv2": float(np.mean(variances_uv2)),
        "median_uv2": float(np.median(variances_uv2)),
        "min_uv2": float(np.min(variances_uv2)),
        "max_uv2": float(np.max(variances_uv2)),
        "channels": [
            {
                "channel": channel,
                "variance_uv2": float(variance),
            }
            for channel, variance in zip(channel_names, variances_uv2)
        ],
    }


def _psd_summary(raw: Any) -> dict[str, Any]:
    selected = _eeg_detection_data(raw)
    if selected is None:
        return {
            "channel_count": 0,
            "sampling_rate_hz": float(raw.info["sfreq"]),
            "total_power_uv2": None,
            "bands": {},
        }

    channel_names, data = selected
    import numpy as np

    sampling_rate = float(raw.info["sfreq"])
    if data.shape[1] < 2 or sampling_rate <= 0:
        return {
            "channel_count": len(channel_names),
            "sampling_rate_hz": sampling_rate,
            "total_power_uv2": None,
            "bands": {},
        }

    demeaned = data - np.mean(data, axis=1, keepdims=True)
    frequencies = np.fft.rfftfreq(demeaned.shape[1], d=1 / sampling_rate)
    power_uv2 = (np.abs(np.fft.rfft(demeaned, axis=1)) ** 2) * 1_000_000_000_000
    nyquist = sampling_rate / 2
    bands = {
        "delta": (1.0, 4.0),
        "theta": (4.0, 8.0),
        "alpha": (8.0, 13.0),
        "beta": (13.0, 30.0),
        "gamma": (30.0, 45.0),
    }
    band_summary: dict[str, Any] = {}
    for band_name, (low_hz, high_hz) in bands.items():
        if low_hz >= nyquist:
            continue
        high_hz = min(high_hz, nyquist)
        mask = (frequencies >= low_hz) & (frequencies < high_hz)
        if not np.any(mask):
            continue
        band_power = np.mean(power_uv2[:, mask], axis=1)
        band_summary[band_name] = {
            "low_hz": low_hz,
            "high_hz": high_hz,
            "mean_power_uv2": float(np.mean(band_power)),
            "median_power_uv2": float(np.median(band_power)),
        }

    positive_mask = frequencies > 0
    total_power = (
        float(np.mean(power_uv2[:, positive_mask]))
        if np.any(positive_mask)
        else None
    )
    return {
        "channel_count": len(channel_names),
        "sampling_rate_hz": sampling_rate,
        "total_power_uv2": total_power,
        "bands": band_summary,
    }


def _before_after_qc_summary(
    config: PreprocessingConfig,
    *,
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    if not config.qc.enabled:
        return {
            "enabled": False,
            "before": {},
            "after": {},
            "delta": {},
        }

    return {
        "enabled": True,
        "before": before,
        "after": after,
        "delta": {
            "bad_channel_count": _numeric_delta(
                before["channel_status"].get("bad_channel_count"),
                after["channel_status"].get("bad_channel_count"),
            ),
            "annotation_count": _numeric_delta(
                before["annotations"].get("count"),
                after["annotations"].get("count"),
            ),
            "variance_mean_uv2": _numeric_delta(
                before["variance"].get("mean_uv2"),
                after["variance"].get("mean_uv2"),
            ),
            "variance_mean_ratio": _numeric_ratio(
                before["variance"].get("mean_uv2"),
                after["variance"].get("mean_uv2"),
            ),
            "psd_total_power_uv2": _numeric_delta(
                before["psd"].get("total_power_uv2"),
                after["psd"].get("total_power_uv2"),
            ),
            "psd_total_power_ratio": _numeric_ratio(
                before["psd"].get("total_power_uv2"),
                after["psd"].get("total_power_uv2"),
            ),
        },
    }


def _numeric_delta(before: Any, after: Any) -> float | int | None:
    if not isinstance(before, (int, float)) or not isinstance(after, (int, float)):
        return None
    return after - before


def _numeric_ratio(before: Any, after: Any) -> float | None:
    if (
        not isinstance(before, (int, float))
        or not isinstance(after, (int, float))
        or before == 0
    ):
        return None
    return after / before


def _bad_channel_contract_summary(
    config: PreprocessingConfig,
    *,
    manual_bad_channels: list[str],
    detection: dict[str, Any],
    interpolation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": config.artifact_schema_version,
        "manual": {
            "channels": list(config.manual_bad_channels),
            "applied_channels": manual_bad_channels,
            "status": "applied" if manual_bad_channels else "not_requested",
        },
        "detection": detection,
        "interpolation": interpolation,
    }


def _apply_manual_bad_channels(raw: Any, config: PreprocessingConfig) -> list[str]:
    requested_channels = list(dict.fromkeys(config.manual_bad_channels))
    if not requested_channels:
        return []

    channel_names = set(raw.ch_names)
    missing_channels = [
        channel for channel in requested_channels if channel not in channel_names
    ]
    if missing_channels:
        raise PreprocessingError(
            "Manual bad channels were not found in the recording: "
            + ", ".join(missing_channels)
        )

    existing_bads = [str(channel) for channel in raw.info.get("bads", [])]
    bads = set(existing_bads)
    bads.update(requested_channels)
    raw.info["bads"] = [channel for channel in raw.ch_names if channel in bads]
    return requested_channels


def _interpolate_bad_channels(raw: Any, config: PreprocessingConfig) -> dict[str, Any]:
    interpolation_config = config.bad_channel_interpolation
    before = _channel_status_snapshot(raw)
    base_report: dict[str, Any] = {
        "schema_version": config.artifact_schema_version,
        "config": asdict(interpolation_config),
        "status": "not_requested",
        "before": before,
        "after": before,
        "interpolated_channels": [],
        "warnings": [],
    }
    if not interpolation_config.enabled:
        return base_report

    bad_channels = list(before["bad_channels"])
    if not bad_channels:
        return {
            **base_report,
            "status": "skipped",
            "reason": "No bad channels were marked before interpolation.",
        }

    montage_source = _ensure_interpolation_montage(raw)
    try:
        raw.interpolate_bads(
            reset_bads=interpolation_config.reset_bads,
            verbose=False,
        )
    except Exception as exc:
        raise PreprocessingError(f"Bad channel interpolation failed: {exc}") from exc

    after = _channel_status_snapshot(raw)
    return {
        **base_report,
        "status": "applied",
        "before": before,
        "after": after,
        "interpolated_channels": bad_channels,
        "reset_bads": interpolation_config.reset_bads,
        "montage_source": montage_source,
    }


def _channel_status_snapshot(raw: Any) -> dict[str, Any]:
    bad_channels = [str(channel) for channel in raw.info.get("bads", [])]
    return {
        "bad_channels": bad_channels,
        "bad_channel_count": len(bad_channels),
    }


def _ensure_interpolation_montage(raw: Any) -> str:
    dig_points = raw.info.get("dig") or []
    if dig_points:
        return "existing"

    try:
        raw.set_montage("standard_1020", match_case=False, on_missing="ignore")
    except Exception:
        return "unavailable"
    return "standard_1020"


def _bad_channel_detection_report(raw: Any, config: PreprocessingConfig) -> dict[str, Any]:
    detection_config = config.bad_channel_detection
    base_report: dict[str, Any] = {
        "schema_version": config.artifact_schema_version,
        "config": asdict(detection_config),
        "method": detection_config.method,
        "status": "not_requested",
        "candidate_count": 0,
        "candidates": [],
        "metrics": {},
        "warnings": [],
    }
    if not detection_config.enabled:
        return base_report

    method = detection_config.method.lower()
    if method == "ransac":
        base_report["status"] = "unsupported"
        base_report["warnings"] = [
            "RANSAC bad channel detection requires a later optional dependency path; no candidates were generated."
        ]
        return base_report
    if method not in {"flat", "deviation"}:
        base_report["status"] = "unsupported"
        base_report["warnings"] = [
            f"Unsupported bad channel detection method: {detection_config.method}"
        ]
        return base_report

    selected = _eeg_detection_data(raw)
    if selected is None:
        base_report["status"] = "no_data"
        base_report["warnings"] = [
            "Bad channel detection could not run because no EEG data channels were available."
        ]
        return base_report

    channel_names, data = selected
    import numpy as np

    std_uv = np.std(data, axis=1) * 1_000_000
    ptp_uv = np.ptp(data, axis=1) * 1_000_000
    log_std = np.log10(np.maximum(std_uv, 1e-12))
    zscores = _robust_zscores(log_std)
    correlations = _channel_correlations(data)
    zscore_threshold = detection_config.zscore_threshold or 5.0
    minimum_correlation = detection_config.minimum_correlation
    flat_threshold_uv = max(float(np.median(ptp_uv)) * 1e-6, 1e-9)

    candidates: list[dict[str, Any]] = []
    for index, channel_name in enumerate(channel_names):
        reasons: list[str] = []
        if ptp_uv[index] <= flat_threshold_uv:
            reasons.append("flat")
        if method == "deviation" and abs(float(zscores[index])) >= zscore_threshold:
            reasons.append("variance_deviation")
        if (
            method == "deviation"
            and minimum_correlation is not None
            and correlations[index] is not None
            and correlations[index] < minimum_correlation
        ):
            reasons.append("low_correlation")
        if reasons:
            candidates.append(
                {
                    "channel": channel_name,
                    "reasons": reasons,
                    "metrics": {
                        "std_uv": float(std_uv[index]),
                        "peak_to_peak_uv": float(ptp_uv[index]),
                        "log_std_robust_zscore": float(zscores[index]),
                        "correlation": correlations[index],
                    },
                }
            )

    base_report.update(
        {
            "status": "completed",
            "candidate_count": len(candidates),
            "candidates": candidates,
            "metrics": {
                "channel_count": len(channel_names),
                "zscore_threshold": zscore_threshold,
                "minimum_correlation": minimum_correlation,
                "flat_threshold_uv": flat_threshold_uv,
            },
        }
    )
    return base_report


def _eeg_detection_data(raw: Any) -> tuple[list[str], Any] | None:
    import mne

    picks = mne.pick_types(
        raw.info,
        eeg=True,
        meg=False,
        eog=False,
        ecg=False,
        stim=False,
        exclude=[],
    )
    if len(picks) == 0:
        return None
    channel_names = [raw.ch_names[pick] for pick in picks]
    return channel_names, raw.get_data(picks=picks)


def _robust_zscores(values: Any) -> Any:
    import numpy as np

    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    if mad > 0:
        return 0.6745 * (values - median) / mad
    std = float(np.std(values))
    if std > 0:
        return (values - float(np.mean(values))) / std
    return np.zeros_like(values)


def _channel_correlations(data: Any) -> list[float | None]:
    import numpy as np

    if data.shape[0] < 3:
        return [None for _ in range(data.shape[0])]

    correlations: list[float | None] = []
    for index in range(data.shape[0]):
        peer_data = np.delete(data, index, axis=0)
        peer_reference = np.median(peer_data, axis=0)
        if np.std(data[index]) == 0 or np.std(peer_reference) == 0:
            correlations.append(None)
            continue
        value = float(np.corrcoef(data[index], peer_reference)[0, 1])
        correlations.append(value if np.isfinite(value) else None)
    return correlations


def _ica_contract_summary(config: PreprocessingConfig) -> dict[str, Any]:
    return {
        "schema_version": config.artifact_schema_version,
        "config": asdict(config.ica),
        "status": "schema_only" if config.ica.enabled else "not_requested",
    }


def _artifact_contract_warnings(config: PreprocessingConfig) -> list[str]:
    warnings: list[str] = []
    if config.artifact_handling.eog_enabled or config.artifact_handling.ecg_enabled:
        warnings.append(
            "EOG/ECG artifact handling config was captured but is not executed until Phase B6."
        )
    if config.ica.enabled:
        warnings.append("ICA config was captured but is not executed until Phase B7.")
    return warnings


def _check_cancelled(
    should_cancel: CancelCheck | None,
    manual_warnings: list[str],
) -> None:
    if should_cancel and should_cancel():
        manual_warnings.append("Cancellation observed at preprocessing checkpoint.")
        raise PreprocessingError("Preprocessing cancelled.")


def _format_warning_records(
    warning_records: list[python_warnings.WarningMessage],
) -> list[str]:
    return [
        f"{warning.category.__name__}: {warning.message}"
        for warning in warning_records
    ]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped
