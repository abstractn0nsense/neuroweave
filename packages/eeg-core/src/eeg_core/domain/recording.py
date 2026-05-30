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
class SourceFileMetadata:
    role: str
    original_filename: str
    stored_path: str
    size_bytes: int | None = None
    checksum_sha256: str | None = None
    content_type: str | None = None
    sidecar_type: str | None = None
    status: str | None = None
    diagnostics: list[dict[str, Any]] = field(default_factory=list)


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
    source_files: list[SourceFileMetadata] = field(default_factory=list)
    sidecar_discovery: dict[str, Any] = field(default_factory=dict)


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
        source_files=[
            source_file_metadata_from_dict(source_file)
            for source_file in data.get("source_files", [])
            if isinstance(source_file, dict)
        ],
        sidecar_discovery=(
            dict(data.get("sidecar_discovery"))
            if isinstance(data.get("sidecar_discovery"), dict)
            else {}
        ),
    )


def channel_metadata_from_dict(data: dict) -> ChannelMetadata:
    return ChannelMetadata(
        name=str(data["name"]),
        type=_optional_string(data.get("type")),
        units=_optional_string(data.get("units")),
        status=_optional_string(data.get("status")),
        status_description=_optional_string(data.get("status_description")),
    )


def source_file_metadata_from_dict(data: dict) -> SourceFileMetadata:
    diagnostics = data.get("diagnostics")
    return SourceFileMetadata(
        role=str(data["role"]),
        original_filename=str(data["original_filename"]),
        stored_path=str(data["stored_path"]),
        size_bytes=_optional_int(data.get("size_bytes")),
        checksum_sha256=_optional_string(data.get("checksum_sha256")),
        content_type=_optional_string(data.get("content_type")),
        sidecar_type=_optional_string(data.get("sidecar_type")),
        status=_optional_string(data.get("status")),
        diagnostics=[
            dict(diagnostic)
            for diagnostic in diagnostics
            if isinstance(diagnostic, dict)
        ]
        if isinstance(diagnostics, list)
        else [],
    )


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
