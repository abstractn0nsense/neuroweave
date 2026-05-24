from pathlib import Path
import csv


class EventLogPreviewError(Exception):
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
