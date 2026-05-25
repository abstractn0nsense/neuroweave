import json
import shutil
from pathlib import Path

import pytest

from eeg_io.analysis_report import (
    ANALYSIS_REPORT_SCHEMA_VERSION,
    AnalysisReportError,
    build_analysis_report,
    write_analysis_report,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "qc"


def test_build_analysis_report_includes_config_provenance_and_qc_summary(tmp_path):
    manifest_path = _copy_epoch_fixture_with_provenance(tmp_path)

    report = build_analysis_report(
        dataset_id="dataset-1",
        run_id="epoch-run-1",
        run_kind="epoch",
        artifact_manifest_path=manifest_path,
        created_at_utc="2026-05-26T00:00:00+00:00",
    )

    assert report["schema_version"] == ANALYSIS_REPORT_SCHEMA_VERSION
    assert report["created_at_utc"] == "2026-05-26T00:00:00+00:00"
    assert report["dataset_id"] == "dataset-1"
    assert report["run_id"] == "epoch-run-1"
    assert report["run_kind"] == "epoch"
    assert report["config_snapshot"] == {
        "condition_field": "trial_type",
        "tmin_seconds": -0.2,
        "tmax_seconds": 0.8,
    }
    assert report["provenance"]["sources"]["event_file"] == "events.tsv"
    assert report["qc_summary"]["run_kind"] == "epoch"
    assert report["qc_summary"]["epoch"]["condition_counts"]["totals"] == {
        "candidate": 3,
        "retained": 2,
        "dropped": 1,
    }
    assert report["artifact_manifest"]["artifact_count"] == 4
    assert report["diagnostics"]["warnings"] == []


def test_write_analysis_report_creates_analysis_report_json(tmp_path):
    manifest_path = _copy_epoch_fixture_with_provenance(tmp_path)
    output_path = tmp_path / "analysis_report.json"

    result_path = write_analysis_report(
        output_path,
        dataset_id="dataset-1",
        run_id="epoch-run-1",
        run_kind="epoch",
        artifact_manifest_path=manifest_path,
        created_at_utc="2026-05-26T00:00:00+00:00",
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert result_path == output_path
    assert payload["schema_version"] == ANALYSIS_REPORT_SCHEMA_VERSION
    assert payload["provenance"]["software_versions"]["python"] == "3.12.0"
    assert payload["qc_summary"]["epoch"]["drop_log"]["entry_count"] == 1


def test_build_analysis_report_allows_config_snapshot_override(tmp_path):
    manifest_path = _copy_epoch_fixture_with_provenance(tmp_path)

    report = build_analysis_report(
        dataset_id="dataset-1",
        run_id="epoch-run-1",
        run_kind="epoch",
        artifact_manifest_path=manifest_path,
        config_snapshot={"condition_field": "override"},
    )

    assert report["config_snapshot"] == {"condition_field": "override"}


def test_build_analysis_report_includes_extra_sections(tmp_path):
    manifest_path = _copy_epoch_fixture_with_provenance(tmp_path)

    report = build_analysis_report(
        dataset_id="dataset-1",
        run_id="epoch-run-1",
        run_kind="epoch",
        artifact_manifest_path=manifest_path,
        extra_sections={
            "dataset_metadata": {"participant_label": "sub-001"},
            "event_summary": {"event_count": 12},
        },
    )

    assert report["dataset_metadata"] == {"participant_label": "sub-001"}
    assert report["event_summary"] == {"event_count": 12}


def test_build_analysis_report_reports_missing_provenance(tmp_path):
    shutil.copytree(FIXTURE_ROOT / "epoch", tmp_path / "epoch")

    report = build_analysis_report(
        dataset_id="dataset-1",
        run_id="epoch-run-1",
        run_kind="epoch",
        artifact_manifest_path=tmp_path / "epoch" / "artifact_manifest.json",
    )

    assert report["provenance"] == {}
    assert report["config_snapshot"] == {}
    assert report["diagnostics"]["warnings"][0]["code"] == "provenance_missing"


def test_build_analysis_report_reports_missing_manifest_artifacts(tmp_path):
    manifest_path = _copy_epoch_fixture_with_provenance(tmp_path)
    (manifest_path.parent / "drop_log.json").unlink()

    report = build_analysis_report(
        dataset_id="dataset-1",
        run_id="epoch-run-1",
        run_kind="epoch",
        artifact_manifest_path=manifest_path,
    )

    assert report["qc_summary"]["epoch"]["drop_log"] == {
        "summary": {},
        "entry_count": 0,
    }
    assert report["diagnostics"]["warnings"] == [
        {
            "code": "artifact_missing",
            "severity": "warning",
            "source": "analysis_report",
            "impact": (
                "Artifact 'drop_log' is listed in the manifest but was not found."
            ),
            "suggested_action": (
                "Regenerate the source run artifact or rebuild the artifact manifest."
            ),
        }
    ]


def test_build_analysis_report_rejects_invalid_provenance_json(tmp_path):
    manifest_path = _copy_epoch_fixture_with_provenance(tmp_path)
    (manifest_path.parent / "provenance.json").write_text("{", encoding="utf-8")

    with pytest.raises(AnalysisReportError, match="Invalid provenance JSON"):
        build_analysis_report(
            dataset_id="dataset-1",
            run_id="epoch-run-1",
            run_kind="epoch",
            artifact_manifest_path=manifest_path,
        )


def _copy_epoch_fixture_with_provenance(tmp_path: Path) -> Path:
    run_root = tmp_path / "epoch"
    shutil.copytree(FIXTURE_ROOT / "epoch", run_root)
    (run_root / "provenance.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run": {
                    "dataset_id": "dataset-1",
                    "run_id": "epoch-run-1",
                    "run_kind": "epoch",
                },
                "sources": {
                    "eeg_file": "raw.fif",
                    "event_file": "events.tsv",
                },
                "config_snapshot": {
                    "condition_field": "trial_type",
                    "tmin_seconds": -0.2,
                    "tmax_seconds": 0.8,
                },
                "software_versions": {
                    "python": "3.12.0",
                    "mne": "1.7.0",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    manifest_path = run_root / "artifact_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"].append(
        {
            "logical_name": "provenance",
            "artifact_type": "provenance_json",
            "path": "provenance.json",
        }
    )
    manifest["artifact_count"] = len(manifest["artifacts"])
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest_path
