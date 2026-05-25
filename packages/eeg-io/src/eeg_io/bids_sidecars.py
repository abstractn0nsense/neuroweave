from dataclasses import dataclass
from pathlib import Path
from typing import Any
import csv
import json


NULL_VALUES = {"", "n/a", "na", "null", "none"}


class BidsSidecarError(Exception):
    pass


@dataclass(frozen=True)
class BidsChannel:
    name: str
    type: str | None = None
    units: str | None = None
    status: str | None = None
    status_description: str | None = None


@dataclass(frozen=True)
class BidsEegSidecar:
    line_frequency_hz: float | None = None
    reference: str | None = None


def read_channels_tsv(path: Path) -> list[BidsChannel]:
    text = path.read_text(encoding="utf-8-sig")
    if not text.strip():
        raise BidsSidecarError("BIDS channels sidecar is empty.")

    reader = csv.DictReader(text.splitlines(), delimiter="\t")
    if not reader.fieldnames:
        raise BidsSidecarError("BIDS channels sidecar header row is missing.")
    if "name" not in reader.fieldnames:
        raise BidsSidecarError("BIDS channels sidecar is missing required column: name.")

    channels: list[BidsChannel] = []
    for index, row in enumerate(reader, start=1):
        name = _required_string(row.get("name"), "name", index)
        channels.append(
            BidsChannel(
                name=name,
                type=_optional_string(row.get("type")),
                units=_optional_string(row.get("units")),
                status=_optional_string(row.get("status")),
                status_description=_optional_string(
                    row.get("status_description")
                ),
            )
        )
    return channels


def read_eeg_json(path: Path) -> BidsEegSidecar:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise BidsSidecarError(f"Invalid BIDS EEG JSON sidecar: {exc}") from exc

    if not isinstance(payload, dict):
        raise BidsSidecarError("BIDS EEG JSON sidecar must be a JSON object.")

    return BidsEegSidecar(
        line_frequency_hz=_line_frequency(payload.get("PowerLineFrequency")),
        reference=_optional_string(payload.get("EEGReference")),
    )


def _line_frequency(value: Any) -> float | None:
    normalized = _optional_string(value)
    if normalized is None:
        return None
    if normalized.lower() == "n/a":
        return None
    try:
        return float(normalized)
    except ValueError as exc:
        raise BidsSidecarError(
            f"PowerLineFrequency must be numeric or n/a: {value}"
        ) from exc


def _required_string(value: Any, field_name: str, row_index: int) -> str:
    normalized = _optional_string(value)
    if normalized is None:
        raise BidsSidecarError(
            f"BIDS channels sidecar row {row_index} is missing required {field_name}."
        )
    return normalized


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if normalized.lower() in NULL_VALUES:
        return None
    return normalized
