from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import re
import warnings as python_warnings

from eeg_core.domain import ComparisonConfig, ErpConfig


class ErpError(Exception):
    def __init__(self, message: str, processing_warnings: list[str] | None = None):
        super().__init__(message)
        self.processing_warnings = processing_warnings or []


class ComparisonError(Exception):
    pass


@dataclass(frozen=True)
class ErpConditionArtifact:
    condition: str
    safe_condition: str
    evoked_path: str
    nave: int
    channel_count: int
    time_min_seconds: float
    time_max_seconds: float
    sampling_rate_hz: float
    channel_time_summary: dict[str, Any]
    plot_status: str
    plot_mode: str
    plot_channel: str | None
    plot_png_path: str | None
    plot_svg_path: str | None
    plot_warnings: list[str]


def generate_erps_from_epochs(
    epochs_path: Path,
    output_directory: Path,
    config: ErpConfig,
) -> dict[str, Any]:
    warning_records: list[python_warnings.WarningMessage] = []
    try:
        with python_warnings.catch_warnings(record=True) as warning_records:
            python_warnings.simplefilter("always")

            import mne

            epochs = mne.read_epochs(epochs_path, preload=True, verbose=False)
            picks = config.picks if config.picks else None
            if picks is not None:
                epochs = epochs.copy().pick(picks)

            conditions = _selected_conditions(
                available_conditions=sorted(epochs.event_id),
                requested_conditions=config.conditions,
            )
            output_directory.mkdir(parents=True, exist_ok=True)
            artifacts: list[ErpConditionArtifact] = []
            plot_warnings: list[str] = []

            for condition in conditions:
                condition_epochs = epochs[condition]
                if len(condition_epochs) == 0:
                    raise ErpError(f"Condition has no retained epochs: {condition}")

                evoked = condition_epochs.average(method=config.method)
                safe_condition = safe_condition_filename(condition)
                evoked_path = output_directory / f"evoked_{safe_condition}.fif"
                evoked.save(evoked_path, overwrite=True, verbose=False)
                plot_metadata = _write_evoked_plot(
                    evoked=evoked,
                    output_directory=output_directory,
                    safe_condition=safe_condition,
                    config=config,
                )
                plot_warnings.extend(plot_metadata["plot_warnings"])
                artifacts.append(
                    ErpConditionArtifact(
                        condition=condition,
                        safe_condition=safe_condition,
                        evoked_path=str(evoked_path),
                        nave=int(evoked.nave),
                        channel_count=len(evoked.ch_names),
                        time_min_seconds=float(evoked.times[0]),
                        time_max_seconds=float(evoked.times[-1]),
                        sampling_rate_hz=float(evoked.info["sfreq"]),
                        channel_time_summary=_channel_time_summary(evoked),
                        plot_status=str(plot_metadata["plot_status"]),
                        plot_mode=str(plot_metadata["plot_mode"]),
                        plot_channel=plot_metadata["plot_channel"],
                        plot_png_path=plot_metadata["plot_png_path"],
                        plot_svg_path=plot_metadata["plot_svg_path"],
                        plot_warnings=plot_metadata["plot_warnings"],
                    )
                )
    except ErpError as exc:
        raise ErpError(
            str(exc),
            processing_warnings=_dedupe(
                _format_warning_records(warning_records) + exc.processing_warnings
            ),
        ) from exc
    except Exception as exc:
        raise ErpError(
            f"ERP generation failed: {exc}",
            processing_warnings=_dedupe(_format_warning_records(warning_records)),
        ) from exc

    warnings = _dedupe(_format_warning_records(warning_records) + plot_warnings)
    condition_payloads = [
        {
            "condition": artifact.condition,
            "safe_condition": artifact.safe_condition,
            "evoked_path": artifact.evoked_path,
            "nave": artifact.nave,
            "channel_count": artifact.channel_count,
            "time_min_seconds": artifact.time_min_seconds,
            "time_max_seconds": artifact.time_max_seconds,
            "sampling_rate_hz": artifact.sampling_rate_hz,
            "channel_time_summary": artifact.channel_time_summary,
            "plot_status": artifact.plot_status,
            "plot_mode": artifact.plot_mode,
            "plot_channel": artifact.plot_channel,
            "plot_png_path": artifact.plot_png_path,
            "plot_svg_path": artifact.plot_svg_path,
            "plot_warnings": artifact.plot_warnings,
        }
        for artifact in artifacts
    ]
    plot_count = sum(
        1
        for condition in condition_payloads
        if condition.get("plot_status") == "completed"
    )
    return {
        "file_format": "fif",
        "mne_version": str(mne.__version__),
        "input_epoch_run_id": config.epoch_run_id,
        "input_epochs_path": str(epochs_path),
        "condition_count": len(condition_payloads),
        "evoked_count": len(condition_payloads),
        "plot_count": plot_count,
        "plot_status": "completed" if plot_count == len(condition_payloads) else "partial",
        "conditions": condition_payloads,
        "warnings": warnings,
        "metadata": {
            "schema_version": 1,
            "input": {
                "epoch_run_id": config.epoch_run_id,
                "epochs_path": str(epochs_path),
            },
            "config": {
                "epoch_run_id": config.epoch_run_id,
                "conditions": config.conditions,
                "picks": config.picks,
                "method": config.method,
                "plot_mode": config.plot_mode,
                "plot_channel": config.plot_channel,
            },
            "conditions": condition_payloads,
            "plot": {
                "mode": config.plot_mode,
                "channel": config.plot_channel,
                "status": "completed"
                if plot_count == len(condition_payloads)
                else "partial",
                "completed_count": plot_count,
                "requested_count": len(condition_payloads),
            },
            "warnings": warnings,
        },
    }


def safe_condition_filename(condition: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", condition.strip())
    safe = safe.strip("._-")
    return safe or "condition"


def generate_comparison_summary(
    erp_metadata_path: Path,
    output_path: Path,
    config: ComparisonConfig,
) -> dict[str, Any]:
    import mne
    import numpy as np

    erp_metadata = json.loads(erp_metadata_path.read_text(encoding="utf-8"))
    conditions = _metadata_conditions_by_label(erp_metadata)
    if config.condition_a not in conditions:
        raise ComparisonError(f"Condition not found: {config.condition_a}")
    if config.condition_b not in conditions:
        raise ComparisonError(f"Condition not found: {config.condition_b}")
    if config.condition_a == config.condition_b:
        raise ComparisonError("Comparison conditions must be different.")
    if config.metric != "mean_amplitude_uv":
        raise ComparisonError("Comparison metric must be 'mean_amplitude_uv'.")
    if config.window_start_seconds >= config.window_end_seconds:
        raise ComparisonError("window_start_seconds must be lower than window_end_seconds.")
    if config.use_gfp and config.channel:
        raise ComparisonError("Use either GFP or a channel, not both.")
    if not config.use_gfp and not config.channel:
        raise ComparisonError("A channel is required when use_gfp is false.")

    condition_a = conditions[config.condition_a]
    condition_b = conditions[config.condition_b]
    with python_warnings.catch_warnings():
        python_warnings.simplefilter("ignore", RuntimeWarning)
        evoked_a = mne.read_evokeds(
            str(condition_a["evoked_path"]),
            condition=0,
            verbose=False,
        )
        evoked_b = mne.read_evokeds(
            str(condition_b["evoked_path"]),
            condition=0,
            verbose=False,
        )
    _validate_comparison_window(evoked_a.times, config)
    _validate_comparison_window(evoked_b.times, config)

    target = (
        {"type": "gfp", "channel": None}
        if config.use_gfp
        else {"type": "channel", "channel": config.channel}
    )
    mean_a = _mean_amplitude_uv(evoked_a, config)
    mean_b = _mean_amplitude_uv(evoked_b, config)
    payload = {
        "schema_version": 1,
        "erp_run_id": config.erp_run_id,
        "source_metadata_path": str(erp_metadata_path),
        "note": "Statistical testing is not implemented in Phase 3.",
        "metric": config.metric,
        "target": target,
        "window": {
            "start_seconds": config.window_start_seconds,
            "end_seconds": config.window_end_seconds,
        },
        "conditions": {
            "a": {
                "label": config.condition_a,
                "evoked_path": condition_a["evoked_path"],
                "mean_amplitude_uv": mean_a,
                "nave": condition_a.get("nave"),
            },
            "b": {
                "label": config.condition_b,
                "evoked_path": condition_b["evoked_path"],
                "mean_amplitude_uv": mean_b,
                "nave": condition_b.get("nave"),
            },
        },
        "difference": {
            "label": f"{config.condition_a} - {config.condition_b}",
            "mean_amplitude_uv": mean_a - mean_b,
        },
        "statistics": {
            "implemented": False,
            "phase": "Phase 4",
        },
        "mne_version": str(mne.__version__),
        "numpy_version": str(np.__version__),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def _metadata_conditions_by_label(erp_metadata: dict[str, Any]) -> dict[str, dict[str, Any]]:
    items = erp_metadata.get("conditions")
    if not isinstance(items, list):
        raise ComparisonError("ERP metadata does not contain condition entries.")

    conditions: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        label = item.get("condition")
        evoked_path = item.get("evoked_path")
        if isinstance(label, str) and isinstance(evoked_path, str):
            conditions[label] = item
    if not conditions:
        raise ComparisonError("ERP metadata does not contain usable conditions.")
    return conditions


def _validate_comparison_window(times: Any, config: ComparisonConfig) -> None:
    if config.window_end_seconds < float(times[0]) or config.window_start_seconds > float(times[-1]):
        raise ComparisonError("Comparison window must overlap the ERP time range.")
    mask = (times >= config.window_start_seconds) & (times <= config.window_end_seconds)
    if not mask.any():
        raise ComparisonError("Comparison window contains no ERP samples.")


def _mean_amplitude_uv(evoked: Any, config: ComparisonConfig) -> float:
    data_uv = evoked.data * 1e6
    mask = (evoked.times >= config.window_start_seconds) & (
        evoked.times <= config.window_end_seconds
    )
    if config.use_gfp:
        values = data_uv.std(axis=0)[mask]
    else:
        assert config.channel is not None
        if config.channel not in evoked.ch_names:
            raise ComparisonError(f"Channel not found: {config.channel}")
        values = data_uv[evoked.ch_names.index(config.channel), mask]
    return float(values.mean())


def _selected_conditions(
    available_conditions: list[str],
    requested_conditions: list[str] | None,
) -> list[str]:
    if not available_conditions:
        raise ErpError("Epochs contain no conditions.")

    conditions = (
        available_conditions
        if not requested_conditions
        else [condition for condition in requested_conditions if condition]
    )
    missing = sorted(set(conditions).difference(available_conditions))
    if missing:
        raise ErpError(f"Requested conditions are not available: {', '.join(missing)}")
    if not conditions:
        raise ErpError("At least one ERP condition is required.")
    return conditions


def _channel_time_summary(evoked: Any) -> dict[str, Any]:
    import numpy as np

    data_uv = evoked.data * 1e6
    times = evoked.times
    ch_names = evoked.ch_names

    positive_index = np.unravel_index(np.argmax(data_uv), data_uv.shape)
    negative_index = np.unravel_index(np.argmin(data_uv), data_uv.shape)
    gfp_uv = data_uv.std(axis=0)
    gfp_index = int(np.argmax(gfp_uv))

    return {
        "peak_positive": _peak_payload(
            channel_names=ch_names,
            times=times,
            data_uv=data_uv,
            index=positive_index,
        ),
        "peak_negative": _peak_payload(
            channel_names=ch_names,
            times=times,
            data_uv=data_uv,
            index=negative_index,
        ),
        "global_field_power_peak": {
            "time_seconds": float(times[gfp_index]),
            "amplitude_uv": float(gfp_uv[gfp_index]),
        },
    }


def _write_evoked_plot(
    evoked: Any,
    output_directory: Path,
    safe_condition: str,
    config: ErpConfig,
) -> dict[str, Any]:
    plot_mode = config.plot_mode if config.plot_mode in {"gfp", "channel"} else "gfp"
    plot_channel = config.plot_channel.strip() if config.plot_channel else None
    png_path = output_directory / f"erp_{safe_condition}.png"
    svg_path = output_directory / f"erp_{safe_condition}.svg"

    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt

        times_ms = evoked.times * 1000
        if plot_mode == "channel" and plot_channel:
            if plot_channel not in evoked.ch_names:
                raise ValueError(f"Plot channel not found: {plot_channel}")
            channel_index = evoked.ch_names.index(plot_channel)
            values_uv = evoked.data[channel_index] * 1e6
            ylabel = "Amplitude (uV)"
            title = f"{safe_condition} / {plot_channel}"
        else:
            plot_mode = "gfp"
            plot_channel = None
            values_uv = evoked.data.std(axis=0) * 1e6
            ylabel = "GFP (uV)"
            title = f"{safe_condition} / GFP"

        figure, axis = plt.subplots(figsize=(7.2, 3.8), dpi=144)
        axis.plot(times_ms, values_uv, color="#38bdf8", linewidth=1.8)
        axis.axvline(0, color="#94a3b8", linewidth=0.8, linestyle="--")
        axis.axhline(0, color="#475569", linewidth=0.6)
        axis.set_title(title)
        axis.set_xlabel("Time (ms)")
        axis.set_ylabel(ylabel)
        axis.grid(True, color="#cbd5e1", linewidth=0.4, alpha=0.45)
        figure.tight_layout()
        figure.savefig(png_path)
        figure.savefig(svg_path)
        plt.close(figure)
    except Exception as exc:
        return {
            "plot_status": "failed",
            "plot_mode": plot_mode,
            "plot_channel": plot_channel,
            "plot_png_path": None,
            "plot_svg_path": None,
            "plot_warnings": [f"ERP plot generation failed: {exc}"],
        }

    return {
        "plot_status": "completed",
        "plot_mode": plot_mode,
        "plot_channel": plot_channel,
        "plot_png_path": str(png_path),
        "plot_svg_path": str(svg_path),
        "plot_warnings": [],
    }


def _peak_payload(
    channel_names: list[str],
    times: Any,
    data_uv: Any,
    index: tuple[int, int],
) -> dict[str, str | float]:
    channel_index, time_index = int(index[0]), int(index[1])
    return {
        "channel": channel_names[channel_index],
        "time_seconds": float(times[time_index]),
        "amplitude_uv": float(data_uv[channel_index, time_index]),
    }


def _format_warning_records(
    warning_records: list[python_warnings.WarningMessage],
) -> list[str]:
    return [str(warning.message) for warning in warning_records]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped
