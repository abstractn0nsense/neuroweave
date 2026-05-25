from pathlib import Path
import csv

from eeg_core.domain import EventColumnMapping, EventLog, NormalizedEvent

_NULL_TOKENS = {"", "n/a", "na", "null"}


class EventLogPreviewError(Exception):
    pass


class EventLogNormalizationError(Exception):
    pass


def preview_event_log(path: Path, max_rows: int = 10) -> dict:
    text = path.read_text(encoding="utf-8-sig")
    if not text.strip():
        raise EventLogPreviewError("Event log is empty")

    delimiter = _detect_delimiter(text, path)
    reader = csv.DictReader(text.splitlines(), delimiter=delimiter)
    if not reader.fieldnames:
        raise EventLogPreviewError("Event log header row is missing")

    rows = []
    total_rows = 0
    for row in reader:
        total_rows += 1
        if len(rows) < max_rows:
            rows.append(dict(row))

    return {
        "columns": list(reader.fieldnames),
        "delimiter": delimiter,
        "preview_rows": rows,
        "row_count": total_rows,
    }


def read_event_log_rows(path: Path) -> tuple[list[str], list[dict[str, str | None]]]:
    text = path.read_text(encoding="utf-8-sig")
    if not text.strip():
        raise EventLogPreviewError("Event log is empty")

    delimiter = _detect_delimiter(text, path)
    reader = csv.DictReader(text.splitlines(), delimiter=delimiter)
    if not reader.fieldnames:
        raise EventLogPreviewError("Event log header row is missing")

    return list(reader.fieldnames), [dict(row) for row in reader]


def normalize_event_log(
    *,
    dataset_id: str,
    event_log_id: str,
    file_id: str,
    path: Path,
    mapping: EventColumnMapping,
) -> EventLog:
    columns, rows = read_event_log_rows(path)
    _require_column(columns, mapping.onset_seconds, "onset_seconds")

    events = [
        _normalize_event(row=row, source_row=index, mapping=mapping)
        for index, row in enumerate(rows, start=1)
    ]
    return EventLog(
        event_log_id=event_log_id,
        dataset_id=dataset_id,
        file_id=file_id,
        mapping=mapping,
        row_count=len(rows),
        events=events,
    )


def _normalize_event(
    *,
    row: dict[str, str | None],
    source_row: int,
    mapping: EventColumnMapping,
) -> NormalizedEvent:
    onset = _required_float(row, mapping.onset_seconds, "onset_seconds", source_row)
    duration = _optional_float(
        row,
        mapping.duration_seconds,
        "duration_seconds",
        source_row,
    )
    reaction_time = _optional_float(
        row,
        mapping.reaction_time_seconds,
        "reaction_time_seconds",
        source_row,
    )
    return NormalizedEvent(
        onset_seconds=onset,
        duration_seconds=duration,
        trial_type=_optional_str(row, mapping.trial_type),
        stimulus=_optional_str(row, mapping.stimulus),
        response=_optional_str(row, mapping.response),
        correct=_optional_bool(row, mapping.correct, source_row),
        reaction_time_seconds=reaction_time,
        source_row=source_row,
    )


def _require_column(
    columns: list[str],
    column_name: str | None,
    target_field: str,
) -> None:
    if not column_name:
        raise EventLogNormalizationError(f"Mapping is missing required field: {target_field}")
    if column_name not in columns:
        raise EventLogNormalizationError(
            f"Mapped column for {target_field} was not found: {column_name}"
        )


def _required_float(
    row: dict[str, str | None],
    column_name: str | None,
    target_field: str,
    source_row: int,
) -> float:
    value = _optional_float(row, column_name, target_field, source_row)
    if value is None:
        raise EventLogNormalizationError(
            f"Missing numeric {target_field} at source row {source_row}"
        )
    return value


def _optional_float(
    row: dict[str, str | None],
    column_name: str | None,
    target_field: str,
    source_row: int,
) -> float | None:
    value = _optional_str(row, column_name)
    if value is None:
        return None

    try:
        return float(value)
    except ValueError as exc:
        raise EventLogNormalizationError(
            f"Invalid numeric {target_field} at source row {source_row}: {value}"
        ) from exc


def _optional_bool(
    row: dict[str, str | None],
    column_name: str | None,
    source_row: int,
) -> bool | None:
    value = _optional_str(row, column_name)
    if value is None:
        return None

    normalized = value.lower()
    if normalized in {"1", "true", "t", "yes", "y", "correct"}:
        return True
    if normalized in {"0", "false", "f", "no", "n", "incorrect"}:
        return False
    raise EventLogNormalizationError(
        f"Invalid boolean correct value at source row {source_row}: {value}"
    )


def _optional_str(row: dict[str, str | None], column_name: str | None) -> str | None:
    if not column_name:
        return None
    value = row.get(column_name)
    if value is None:
        return None
    stripped = value.strip()
    if stripped.lower() in _NULL_TOKENS:
        return None
    return stripped


def _detect_delimiter(text: str, path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".tsv":
        return "\t"
    if suffix == ".csv":
        return ","

    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",\t")
        return dialect.delimiter
    except csv.Error:
        if "\t" in text.partition("\n")[0]:
            return "\t"
        return ","
