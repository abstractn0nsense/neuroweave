from dataclasses import dataclass


@dataclass(frozen=True)
class RecordingMetadata:
    dataset_id: str
    file_format: str
    channel_count: int
    sampling_rate_hz: float
    duration_seconds: float
    channel_names: list[str]

