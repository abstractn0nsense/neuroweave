from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ChannelMetadata:
    name: str
    type: str | None = None
    units: str | None = None
    status: str | None = None
    status_description: str | None = None


@dataclass(frozen=True)
class RecordingMetadata:
    dataset_id: str
    file_format: str
    channel_count: int
    sampling_rate_hz: float
    duration_seconds: float
    channel_names: list[str]
    channel_details: list[ChannelMetadata] = field(default_factory=list)
    line_frequency_hz: float | None = None
    reference: str | None = None


def recording_metadata_from_dict(data: dict) -> RecordingMetadata:
    return RecordingMetadata(
        dataset_id=str(data["dataset_id"]),
        file_format=str(data["file_format"]),
        channel_count=int(data["channel_count"]),
        sampling_rate_hz=float(data["sampling_rate_hz"]),
        duration_seconds=float(data["duration_seconds"]),
        channel_names=[str(channel_name) for channel_name in data["channel_names"]],
        channel_details=[
            channel_metadata_from_dict(channel)
            for channel in data.get("channel_details", [])
            if isinstance(channel, dict)
        ],
        line_frequency_hz=_optional_float(data.get("line_frequency_hz")),
        reference=_optional_string(data.get("reference")),
    )


def channel_metadata_from_dict(data: dict) -> ChannelMetadata:
    return ChannelMetadata(
        name=str(data["name"]),
        type=_optional_string(data.get("type")),
        units=_optional_string(data.get("units")),
        status=_optional_string(data.get("status")),
        status_description=_optional_string(data.get("status_description")),
    )


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
