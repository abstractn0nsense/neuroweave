import csv
import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path("scripts/prepare_physionet_eegmmi_demo.py")


def _load_script_module():
    spec = importlib.util.spec_from_file_location(
        "prepare_physionet_eegmmi_demo",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_physionet_demo_event_csv_generation_is_offline(tmp_path):
    script = _load_script_module()
    destination = tmp_path / "S001R03_events.csv"

    count = script.write_event_csv(
        [
            script.DemoEvent(0.0, 4.2, "T0"),
            script.DemoEvent(4.2, 4.1, "T1"),
            script.DemoEvent(8.3, 4.1, "T2"),
        ],
        destination,
        "S001R03",
    )

    with destination.open(newline="", encoding="utf-8") as csv_file:
        rows = list(csv.DictReader(csv_file))

    assert count == 3
    assert rows[0]["trial_type"] == "rest"
    assert rows[1]["trial_type"] == "left_fist"
    assert rows[2]["trial_type"] == "right_fist"
    assert rows[1]["task"] == "executed_left_right_fist"
    assert rows[1]["onset"] == "4.200000"
    assert rows[1]["duration"] == "4.100000"


def test_physionet_demo_smoke_manifest_is_offline(tmp_path):
    script = _load_script_module()
    eeg_path = Path("data/raw/public-samples/S001R03.edf")
    event_path = Path("data/raw/public-samples/S001R03_events.csv")
    manifest_path = tmp_path / "S001R03_neuroweave_smoke.json"

    payload = script.build_smoke_manifest(
        record="S001R03",
        eeg_path=eeg_path,
        event_csv_path=event_path,
        event_count=30,
    )
    script.write_smoke_manifest(
        destination=manifest_path,
        record="S001R03",
        eeg_path=eeg_path,
        event_csv_path=event_path,
        event_count=30,
    )

    written = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert payload["profile_id"] == "physionet_eegmmi_s001r03"
    assert payload["local_files"]["eeg_recording"] == "data/raw/public-samples/S001R03.edf"
    assert payload["event_mapping"]["trial_type"] == "trial_type"
    assert payload["epoching"]["expected_conditions"] == [
        "rest",
        "left_fist",
        "right_fist",
    ]
    assert payload["comparison"]["condition_a"] == "left_fist"
    assert payload["comparison"]["condition_b"] == "right_fist"
    assert payload["expected_warnings_snapshot"].endswith(
        "physionet_eegmmi_s001r03_expected_warnings.json"
    )
    assert written == payload


def test_physionet_demo_url_targets_public_edf():
    script = _load_script_module()

    assert (
        script.physionet_record_url("S001R03")
        == "https://physionet.org/files/eegmmidb/1.0.0/S001/S001R03.edf"
    )


def test_physionet_demo_run_label_mapping():
    script = _load_script_module()

    assert script.trial_type_for_annotation(3, "T1") == "left_fist"
    assert script.trial_type_for_annotation(3, "T2") == "right_fist"
    assert script.trial_type_for_annotation(5, "T1") == "both_fists"
    assert script.trial_type_for_annotation(5, "T2") == "both_feet"
