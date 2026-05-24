from dataclasses import dataclass


@dataclass(frozen=True)
class RecordingMetadata:
    dataset_id: str
    file_format: str
    channel_count: int
    sampling_rate_hz: float
    duration_seconds: float
    channel_names: list[str]


def recording_metadata_from_dict(data: dict) -> RecordingMetadata:
    return RecordingMetadata(
        dataset_id=str(data["dataset_id"]),
        file_format=str(data["file_format"]),
        channel_count=int(data["channel_count"]),
        sampling_rate_hz=float(data["sampling_rate_hz"]),
        duration_seconds=float(data["duration_seconds"]),
        channel_names=[str(channel_name) for channel_name in data["channel_names"]],
    )
