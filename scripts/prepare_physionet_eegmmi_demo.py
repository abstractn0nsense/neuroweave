"""Prepare the PhysioNet EEGMMI S001R03 public demo files.

The script downloads one public EDF file into the ignored data directory and
creates a NeuroWeave-compatible event CSV from the EDF+ annotations.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from urllib.request import urlretrieve

import mne


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "raw" / "public-samples"
DEFAULT_RECORD = "S001R03"
DEFAULT_PROFILE_ID = "physionet_eegmmi_s001r03"
PHYSIONET_EEGMMI_BASE_URL = "https://physionet.org/files/eegmmidb/1.0.0"
CSV_FIELDS = [
    "onset",
    "duration",
    "trial_type",
    "stimulus",
    "source_description",
    "run",
    "task",
]


@dataclass(frozen=True)
class DemoEvent:
    onset: float
    duration: float
    source_description: str


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Download PhysioNet EEGMMI S001R03 and create a NeuroWeave event CSV."
        )
    )
    parser.add_argument("--record", default=DEFAULT_RECORD)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--events-only",
        action="store_true",
        help="Skip download and create the CSV from an existing EDF file.",
    )
    args = parser.parse_args()

    record = args.record.upper()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    edf_path = output_dir / f"{record}.edf"
    event_csv_path = output_dir / f"{record}_events.csv"
    manifest_path = output_dir / f"{record}_neuroweave_smoke.json"

    if not args.events_only and not edf_path.exists():
        download_physionet_record(record, edf_path)

    if not edf_path.exists():
        raise FileNotFoundError(
            f"Missing EDF file: {edf_path}. Run without --events-only first."
        )

    events = read_edf_annotations(edf_path)
    row_count = write_event_csv(events, event_csv_path, record)
    write_smoke_manifest(
        destination=manifest_path,
        record=record,
        eeg_path=edf_path,
        event_csv_path=event_csv_path,
        event_count=row_count,
    )

    print("Prepared PhysioNet EEGMMI demo:")
    print(f"  EEG Recording: {edf_path}")
    print(f"  Event Log:     {event_csv_path}")
    print(f"  Smoke Manifest:{manifest_path}")
    print(f"  Events:        {row_count}")
    print("Upload both files in NeuroWeave, then follow docs/public-demo-physionet-eegmmi.md.")


def download_physionet_record(record: str, destination: Path) -> None:
    url = physionet_record_url(record)
    destination.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {url}")
    urlretrieve(url, destination)


def physionet_record_url(record: str) -> str:
    subject = record[:4]
    return f"{PHYSIONET_EEGMMI_BASE_URL}/{subject}/{record}.edf"


def read_edf_annotations(edf_path: Path) -> list[DemoEvent]:
    raw = mne.io.read_raw_edf(edf_path, preload=False, verbose="ERROR")
    return [
        DemoEvent(
            onset=float(onset),
            duration=float(duration),
            source_description=str(description),
        )
        for onset, duration, description in zip(
            raw.annotations.onset,
            raw.annotations.duration,
            raw.annotations.description,
            strict=True,
        )
    ]


def write_event_csv(
    events: Iterable[DemoEvent],
    destination: Path,
    record: str,
) -> int:
    run_number = parse_run_number(record)
    task = task_label_for_run(run_number)
    destination.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with destination.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for event in events:
            trial_type = trial_type_for_annotation(run_number, event.source_description)
            writer.writerow(
                {
                    "onset": f"{event.onset:.6f}",
                    "duration": f"{event.duration:.6f}",
                    "trial_type": trial_type,
                    "stimulus": event.source_description,
                    "source_description": event.source_description,
                    "run": f"R{run_number:02d}",
                    "task": task,
                }
            )
            count += 1

    return count


def build_smoke_manifest(
    *,
    record: str,
    eeg_path: Path,
    event_csv_path: Path,
    event_count: int,
) -> dict:
    run_number = parse_run_number(record)
    return {
        "schema_version": 1,
        "profile_id": DEFAULT_PROFILE_ID,
        "source_dataset": {
            "name": "PhysioNet EEG Motor Movement/Imagery Dataset",
            "version": "1.0.0",
            "record": record,
            "url": physionet_record_url(record),
            "doi": "https://doi.org/10.13026/C28G6P",
            "license": "Open Data Commons Attribution License v1.0",
        },
        "storage_policy": {
            "public_data_root": "data/raw/public-samples/",
            "git_policy": "Generated public EEG files remain under ignored data/ paths.",
        },
        "local_files": {
            "eeg_recording": _repo_relative_path(eeg_path),
            "event_log": _repo_relative_path(event_csv_path),
        },
        "event_mapping": {
            "onset_seconds": "onset",
            "duration_seconds": "duration",
            "trial_type": "trial_type",
            "stimulus": "stimulus",
        },
        "workflow": [
            "ingest_eeg_and_events",
            "save_event_mapping",
            "validate_dataset",
            "run_preprocessing",
            "run_epoching",
            "run_erp",
            "run_comparison_summary",
        ],
        "epoching": {
            "condition_field": "trial_type",
            "expected_conditions": _expected_conditions_for_run(run_number),
        },
        "comparison": {
            "condition_a": "left_fist" if run_number in {3, 4, 7, 8, 11, 12} else "both_fists",
            "condition_b": "right_fist" if run_number in {3, 4, 7, 8, 11, 12} else "both_feet",
            "use_gfp": True,
            "metric": "mean_amplitude_uv",
            "statistics_implemented": False,
        },
        "expected_warnings_snapshot": (
            "tests/fixtures/public_smoke/"
            "physionet_eegmmi_s001r03_expected_warnings.json"
        ),
        "event_count": event_count,
    }


def write_smoke_manifest(
    *,
    destination: Path,
    record: str,
    eeg_path: Path,
    event_csv_path: Path,
    event_count: int,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = build_smoke_manifest(
        record=record,
        eeg_path=eeg_path,
        event_csv_path=event_csv_path,
        event_count=event_count,
    )
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _expected_conditions_for_run(run_number: int) -> list[str]:
    if run_number in {3, 4, 7, 8, 11, 12}:
        return ["rest", "left_fist", "right_fist"]
    if run_number in {5, 6, 9, 10, 13, 14}:
        return ["rest", "both_fists", "both_feet"]
    return ["rest"]


def _repo_relative_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def parse_run_number(record: str) -> int:
    try:
        return int(record.upper().split("R", maxsplit=1)[1])
    except (IndexError, ValueError) as exc:
        raise ValueError(f"Record must look like S001R03, got: {record}") from exc


def task_label_for_run(run_number: int) -> str:
    if run_number in {3, 7, 11}:
        return "executed_left_right_fist"
    if run_number in {4, 8, 12}:
        return "imagined_left_right_fist"
    if run_number in {5, 9, 13}:
        return "executed_both_fists_or_feet"
    if run_number in {6, 10, 14}:
        return "imagined_both_fists_or_feet"
    return "baseline"


def trial_type_for_annotation(run_number: int, description: str) -> str:
    code = description.strip().upper()
    if code == "T0":
        return "rest"

    if run_number in {3, 4, 7, 8, 11, 12}:
        return {"T1": "left_fist", "T2": "right_fist"}.get(code, code.lower())

    if run_number in {5, 6, 9, 10, 13, 14}:
        return {"T1": "both_fists", "T2": "both_feet"}.get(code, code.lower())

    return code.lower()


if __name__ == "__main__":
    main()
