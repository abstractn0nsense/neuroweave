import json
import shutil
from pathlib import Path

import pytest

from eeg_io.qc_summary import QcSummaryError, build_qc_summary


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "qc"


def test_build_qc_summary_reads_preprocessing_artifacts():
    summary = build_qc_summary(FIXTURE_ROOT / "preprocessing" / "artifact_manifest.json")

    assert summary["schema_version"] == 1
    assert summary["run_kind"] == "preprocessing"
    assert summary["preprocessing"]["filters"]["high_pass"]["status"] == "applied"
    assert summary["preprocessing"]["filters"]["notch"]["status"] == "skipped"
    assert summary["preprocessing"]["reference"]["parameters"]["reference"] == "average"
    assert summary["preprocessing"]["resample"]["status"] == "applied"
    assert summary["preprocessing"]["channel_status"] == {
        "input_bad_channels": ["Fp1"],
        "input_bad_channel_count": 1,
        "output_bad_channels": [],
        "output_bad_channel_count": 0,
    }
    assert "before_after" in summary["preprocessing"]


def test_build_qc_summary_reads_epoch_artifacts():
    summary = build_qc_summary(FIXTURE_ROOT / "epoch" / "artifact_manifest.json")

    assert summary["run_kind"] == "epoch"
    assert summary["epoch"]["condition_counts"]["totals"] == {
        "candidate": 3,
        "retained": 2,
        "dropped": 1,
    }
    assert summary["epoch"]["drop_log"]["summary"]["dropped_epoch_count"] == 1
    assert summary["epoch"]["drop_log"]["entry_count"] == 1
    assert summary["epoch"]["out_of_bounds"] == {"out_of_bounds": 1}


def test_build_qc_summary_reads_erp_artifacts():
    summary = build_qc_summary(FIXTURE_ROOT / "erp" / "artifact_manifest.json")

    assert summary["run_kind"] == "erp"
    assert summary["erp"]["condition_count"] == 2
    assert summary["erp"]["plot_status"] == "partial"
    assert summary["erp"]["conditions"][0] == {
        "condition": "standard",
        "nave": 12,
        "gfp_peak": 3.4,
        "channel_peak": 5.6,
        "channel_time_summary": {},
        "plot_status": "completed",
        "plot_mode": "gfp",
        "plot_channel": None,
        "plot_warnings": [],
    }
    assert summary["erp"]["conditions"][1]["plot_warnings"] == [
        "Plot generation failed."
    ]


def test_build_qc_summary_reports_missing_manifest_artifacts(tmp_path):
    shutil.copytree(FIXTURE_ROOT / "epoch", tmp_path / "epoch")
    (tmp_path / "epoch" / "drop_log.json").unlink()

    summary = build_qc_summary(tmp_path / "epoch" / "artifact_manifest.json")

    assert summary["run_kind"] == "epoch"
    assert summary["artifact_manifest"]["missing_artifacts"][0]["logical_name"] == (
        "drop_log"
    )
    assert summary["epoch"]["drop_log"] == {"summary": {}, "entry_count": 0}


def test_build_qc_summary_rejects_invalid_json_artifact(tmp_path):
    shutil.copytree(FIXTURE_ROOT / "preprocessing", tmp_path / "preprocessing")
    (tmp_path / "preprocessing" / "filter_report.json").write_text(
        "{",
        encoding="utf-8",
    )

    with pytest.raises(QcSummaryError, match="filter_report"):
        build_qc_summary(tmp_path / "preprocessing" / "artifact_manifest.json")


def test_build_qc_summary_handles_unknown_manifest(tmp_path):
    manifest_path = tmp_path / "artifact_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_root": ".",
                "artifact_count": 0,
                "artifacts": [],
            }
        ),
        encoding="utf-8",
    )

    summary = build_qc_summary(manifest_path)

    assert summary["run_kind"] == "unknown"
    assert summary["unknown"] == {"available_artifacts": []}
