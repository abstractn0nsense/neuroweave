from pathlib import Path
import csv

from eeg_core.domain import (
    EventColumnMapping,
    EventLog,
    EventRowFilter,
    NormalizedEvent,
)

_NULL_TOKENS = {"", "n/a", "na", "none", "null"}
_MAPPING_SOURCE_FIELDS = (
    "onset_seconds",
    "duration_seconds",
    "trial_type",
    "stimulus",
    "response",
    "correct",
    "reaction_time_seconds",
)
EVENT_MAPPING_PRESETS: dict[str, EventColumnMapping] = {
    "psychopy": EventColumnMapping(
        onset_seconds="stim_onset",
        duration_seconds="stim_duration",
        trial_type="condition",
        response="key_resp.keys",
        correct="key_resp.corr",
        reaction_time_seconds="key_resp.rt",
    ),
    "bids_events": EventColumnMapping(
        onset_seconds="onset",
        duration_seconds="duration",
        trial_type="trial_type",
        stimulus="stimulus",
        response="response",
        correct="correct",
        reaction_time_seconds="response_time",
    ),
    "eeglab_annotations": EventColumnMapping(
        onset_seconds="onset",
        duration_seconds="duration",
        trial_type="type",
    ),
}


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
    row_filter: EventRowFilter | None = None,
    condition_column: str | None = None,
    provenance: dict | None = None,
) -> EventLog:
    condition_column = _normalized_condition_column(condition_column)
    columns, rows = read_event_log_rows(path)
    _require_column(columns, mapping.onset_seconds, "onset_seconds")
    _require_filter_columns(columns, row_filter)
    _require_condition_column(columns, condition_column)
    filtered_rows = _filter_event_rows(rows, row_filter)

    events = [
        _normalize_event(
            row=row,
            source_row=index,
            mapping=mapping,
            row_filter=row_filter,
            condition_column=condition_column,
        )
        for index, row in filtered_rows
    ]
    return EventLog(
        event_log_id=event_log_id,
        dataset_id=dataset_id,
        file_id=file_id,
        mapping=mapping,
        row_count=len(rows),
        filter_count=len(rows) - len(filtered_rows),
        row_filter=row_filter,
        condition_column=condition_column,
        provenance=provenance or {},
        events=events,
    )


def event_mapping_preset(name: str) -> EventColumnMapping:
    try:
        return EVENT_MAPPING_PRESETS[name]
    except KeyError as exc:
        raise EventLogNormalizationError(f"Unknown event mapping preset: {name}") from exc


def _filter_event_rows(
    rows: list[dict[str, str | None]],
    row_filter: EventRowFilter | None,
) -> list[tuple[int, dict[str, str | None]]]:
    indexed_rows = list(enumerate(rows, start=1))
    if row_filter is None:
        return indexed_rows

    return [
        (source_row, row)
        for source_row, row in indexed_rows
        if _row_matches_include(row, row_filter) and not _row_matches_exclude(row, row_filter)
    ]


def _require_filter_columns(
    columns: list[str],
    row_filter: EventRowFilter | None,
) -> None:
    if row_filter is None:
        return
    for condition in [*row_filter.include, *row_filter.exclude]:
        if condition.column not in columns:
            raise EventLogNormalizationError(
                f"Row filter column was not found: {condition.column}"
            )


def _require_condition_column(
    columns: list[str],
    condition_column: str | None,
) -> None:
    if condition_column is None:
        return
    if condition_column not in columns:
        raise EventLogNormalizationError(
            f"Condition column was not found: {condition_column}"
        )


def _row_matches_include(row: dict[str, str | None], row_filter: EventRowFilter) -> bool:
    return all(
        _row_value(row, condition.column) == _normalized_filter_value(condition.equals)
        for condition in row_filter.include
    )


def _row_matches_exclude(row: dict[str, str | None], row_filter: EventRowFilter) -> bool:
    return any(
        _row_value(row, condition.column) == _normalized_filter_value(condition.equals)
        for condition in row_filter.exclude
    )


def _row_value(row: dict[str, str | None], column_name: str) -> str | None:
    value = row.get(column_name)
    if value is None:
        return None
    return _normalized_filter_value(value)


def _normalized_filter_value(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if stripped.lower() in _NULL_TOKENS:
        return None
    return stripped


def _normalized_condition_column(condition_column: str | None) -> str | None:
    if condition_column is None:
        return None
    stripped = condition_column.strip()
    if stripped.lower() in _NULL_TOKENS:
        return None
    return stripped


def _normalize_event(
    *,
    row: dict[str, str | None],
    source_row: int,
    mapping: EventColumnMapping,
    row_filter: EventRowFilter | None,
    condition_column: str | None,
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
        trial_type=_derive_condition(row, mapping, condition_column),
        stimulus=_optional_str(row, mapping.stimulus),
        response=_optional_str(row, mapping.response),
        correct=_optional_bool(row, mapping.correct, source_row),
        reaction_time_seconds=reaction_time,
        source_row=source_row,
        source_columns=_selected_source_columns(
            row=row,
            mapping=mapping,
            row_filter=row_filter,
            condition_column=condition_column,
        ),
    )


def _derive_condition(
    row: dict[str, str | None],
    mapping: EventColumnMapping,
    condition_column: str | None,
) -> str | None:
    if condition_column is not None:
        return _optional_str(row, condition_column)

    mapped = _optional_str(row, mapping.trial_type)
    if mapped is not None:
        return mapped

    bids_trial_type = _optional_str(row, "trial_type")
    if bids_trial_type is not None:
        return bids_trial_type

    return _optional_str(row, "value")


def _selected_source_columns(
    *,
    row: dict[str, str | None],
    mapping: EventColumnMapping,
    row_filter: EventRowFilter | None,
    condition_column: str | None,
) -> dict[str, str | None]:
    column_names = _selected_source_column_names(
        row=row,
        mapping=mapping,
        row_filter=row_filter,
        condition_column=condition_column,
    )
    return {
        column_name: _normalized_filter_value(row.get(column_name))
        for column_name in column_names
        if column_name in row
    }


def _selected_source_column_names(
    *,
    row: dict[str, str | None],
    mapping: EventColumnMapping,
    row_filter: EventRowFilter | None,
    condition_column: str | None,
) -> list[str]:
    names: list[str] = []
    for field_name in _MAPPING_SOURCE_FIELDS:
        column_name = getattr(mapping, field_name)
        if column_name:
            names.append(column_name)

    if row_filter is not None:
        names.extend(condition.column for condition in row_filter.include)
        names.extend(condition.column for condition in row_filter.exclude)

    if condition_column:
        names.append(condition_column)
    else:
        if "trial_type" in row:
            names.append("trial_type")
        if "value" in row:
            names.append("value")

    return list(dict.fromkeys(names))


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
