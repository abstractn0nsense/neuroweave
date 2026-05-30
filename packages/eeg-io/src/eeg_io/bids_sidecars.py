from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import csv
import json


NULL_VALUES = {"", "n/a", "na", "null", "none"}
BIDS_SIDECAR_DISCOVERY_SCHEMA_VERSION = 1

_SIDECAR_SUFFIXES = {
    "eeg_json": "_eeg.json",
    "channels_tsv": "_channels.tsv",
    "events_tsv": "_events.tsv",
    "electrodes_tsv": "_electrodes.tsv",
    "coordsystem_json": "_coordsystem.json",
}

_REFERENCE_SUFFIXES = (
    "_eeg.vhdr",
    "_eeg.eeg",
    "_eeg.edf",
    "_eeg.bdf",
    "_eeg.set",
    "_eeg.fif",
    "_eeg.fif.gz",
    "_events.tsv",
    "_events.csv",
)


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


@dataclass(frozen=True)
class BidsSidecarDiagnostic:
    severity: str
    source: str
    code: str
    impact: str | None = None
    suggested_action: str | None = None


@dataclass(frozen=True)
class BidsSidecarCandidate:
    sidecar_type: str
    path: Path
    status: str
    diagnostics: list[BidsSidecarDiagnostic] = field(default_factory=list)


@dataclass(frozen=True)
class BidsSidecarDiscovery:
    reference_path: Path
    bids_basename: str
    candidates: list[BidsSidecarCandidate] = field(default_factory=list)
    diagnostics: list[BidsSidecarDiagnostic] = field(default_factory=list)
    schema_version: int = BIDS_SIDECAR_DISCOVERY_SCHEMA_VERSION


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


def discover_bids_sidecars(reference_path: Path) -> BidsSidecarDiscovery:
    """Find and validate BIDS sidecars adjacent to an EEG or events file."""
    reference_path = reference_path.resolve()
    bids_basename = bids_basename_from_path(reference_path)
    candidates: list[BidsSidecarCandidate] = []
    diagnostics: list[BidsSidecarDiagnostic] = []

    for sidecar_type, suffix in _SIDECAR_SUFFIXES.items():
        sidecar_path = reference_path.parent / f"{bids_basename}{suffix}"
        if not sidecar_path.exists():
            continue
        candidate = _validate_sidecar_candidate(
            sidecar_type=sidecar_type,
            path=sidecar_path,
        )
        candidates.append(candidate)
        diagnostics.extend(candidate.diagnostics)

    return BidsSidecarDiscovery(
        reference_path=reference_path,
        bids_basename=bids_basename,
        candidates=candidates,
        diagnostics=diagnostics,
    )


def bids_basename_from_path(path: Path) -> str:
    filename = path.name
    lower_filename = filename.lower()
    for suffix in _REFERENCE_SUFFIXES:
        if lower_filename.endswith(suffix):
            return filename[: -len(suffix)]

    suffix = path.suffix
    stem = path.name[: -len(suffix)] if suffix else path.name
    lower_stem = stem.lower()
    for marker in ("_eeg", "_events"):
        if lower_stem.endswith(marker):
            return stem[: -len(marker)]
    return stem


def _validate_sidecar_candidate(
    *,
    sidecar_type: str,
    path: Path,
) -> BidsSidecarCandidate:
    try:
        if sidecar_type == "channels_tsv":
            read_channels_tsv(path)
            status = "valid"
        elif sidecar_type == "eeg_json":
            read_eeg_json(path)
            status = "valid"
        elif sidecar_type == "events_tsv":
            _validate_events_tsv(path)
            status = "valid"
        else:
            status = "discovered"
    except BidsSidecarError as exc:
        return BidsSidecarCandidate(
            sidecar_type=sidecar_type,
            path=path,
            status="invalid",
            diagnostics=[
                BidsSidecarDiagnostic(
                    severity="warning",
                    source="bids",
                    code="bids_sidecar_invalid",
                    impact=f"{sidecar_type} sidecar could not be parsed: {exc}",
                    suggested_action=(
                        "Review the BIDS sidecar file before relying on its metadata."
                    ),
                )
            ],
        )

    return BidsSidecarCandidate(
        sidecar_type=sidecar_type,
        path=path,
        status=status,
    )


def _validate_events_tsv(path: Path) -> None:
    text = path.read_text(encoding="utf-8-sig")
    if not text.strip():
        raise BidsSidecarError("BIDS events sidecar is empty.")

    reader = csv.DictReader(text.splitlines(), delimiter="\t")
    if not reader.fieldnames:
        raise BidsSidecarError("BIDS events sidecar header row is missing.")
    if "onset" not in reader.fieldnames:
        raise BidsSidecarError("BIDS events sidecar is missing required column: onset.")


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
