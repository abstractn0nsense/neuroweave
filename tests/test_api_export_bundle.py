import json
import shutil
import zipfile
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient

from apps.api import main as api_main
from eeg_core.domain import (
    EpochConfig,
    EpochRun,
    EpochRunStatus,
    ErpConfig,
    ErpRun,
    ErpRunStatus,
    EventColumnMapping,
    EventLog,
    NormalizedEvent,
    PreprocessingConfig,
    PreprocessingRun,
    PreprocessingRunStatus,
    Recording,
)
from eeg_core.domain.recording import RecordingMetadata
from eeg_io.registry import JsonRegistryRepository, JsonRunRepository


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "qc"


def test_get_dataset_export_bundle_downloads_latest_completed_run(
    tmp_path,
    monkeypatch,
):
    client, run_repository = _client(tmp_path, monkeypatch)
    manifest_path = _copy_erp_fixture_with_figure(tmp_path)
    run_repository.save_erp_run(
        ErpRun(
            run_id="erp-001",
            dataset_id="dataset-001",
            config=ErpConfig(epoch_run_id="epoch-001", conditions=["standard"]),
            status=ErpRunStatus.COMPLETED,
            finished_at_utc="2026-05-26T00:00:00+00:00",
            output_metadata={"artifact_manifest_path": str(manifest_path)},
        )
    )

    response = client.get("/datasets/dataset-001/export-bundle")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "neuroweave_dataset-001_erp-001_export_bundle.zip" in response.headers[
        "content-disposition"
    ]
    with zipfile.ZipFile(BytesIO(response.content)) as bundle:
        assert sorted(bundle.namelist()) == [
            "analysis_report.json",
            "artifact_manifest.json",
            "artifacts/erp_metadata.json",
            "export_bundle_manifest.json",
            "figures/erp_standard_plot.png",
        ]
        analysis_report = json.loads(bundle.read("analysis_report.json"))
        bundle_manifest = json.loads(bundle.read("export_bundle_manifest.json"))

    assert analysis_report["dataset_id"] == "dataset-001"
    assert analysis_report["run_id"] == "erp-001"
    assert analysis_report["run_kind"] == "erp"
    assert analysis_report["config_snapshot"]["epoch_run_id"] == "epoch-001"
    assert bundle_manifest["analysis_report_included"] is True
    assert bundle_manifest["diagnostics"] == {"warnings": []}


def test_get_erp_run_export_bundle_accepts_direct_run_id(tmp_path, monkeypatch):
    client, run_repository = _client(tmp_path, monkeypatch)
    manifest_path = _copy_erp_fixture_with_figure(tmp_path)
    run_repository.save_erp_run(
        ErpRun(
            run_id="erp-001",
            dataset_id="dataset-001",
            config=ErpConfig(epoch_run_id="epoch-001"),
            status=ErpRunStatus.COMPLETED,
            finished_at_utc="2026-05-26T00:00:00+00:00",
            output_metadata={"artifact_manifest_path": str(manifest_path)},
        )
    )

    response = client.get("/erp-runs/erp-001/export-bundle")

    assert response.status_code == 200
    with zipfile.ZipFile(BytesIO(response.content)) as bundle:
        analysis_report = json.loads(bundle.read("analysis_report.json"))

    assert analysis_report["run_id"] == "erp-001"


def test_create_erp_analysis_report_writes_report_and_manifest_entry(
    tmp_path,
    monkeypatch,
):
    client, run_repository = _client(tmp_path, monkeypatch)
    registry_repository = api_main.registry_repository
    manifest_path = _copy_erp_fixture_with_figure(tmp_path)
    comparison_path = manifest_path.parent / "comparison_summary.json"
    comparison_path.write_text(
        json.dumps({"metric": "mean_amplitude_uv", "difference": {"mean": 1.2}})
        + "\n",
        encoding="utf-8",
    )
    registry_repository.save_recording(
        Recording(
            recording_id="recording-001",
            dataset_id="dataset-001",
            file_id="file-001",
            metadata=RecordingMetadata(
                dataset_id="dataset-001",
                file_format="fif",
                channel_count=2,
                sampling_rate_hz=100.0,
                duration_seconds=6.0,
                channel_names=["Cz", "Pz"],
            ),
        )
    )
    registry_repository.save_event_log(
        EventLog(
            event_log_id="events-001",
            dataset_id="dataset-001",
            file_id="events-file-001",
            mapping=EventColumnMapping(
                onset_seconds="onset",
                duration_seconds="duration",
                trial_type="trial_type",
            ),
            row_count=3,
            events=[
                NormalizedEvent(1.0, 1, trial_type="standard"),
                NormalizedEvent(2.0, 2, trial_type="target"),
                NormalizedEvent(3.0, 3, trial_type="target"),
            ],
        )
    )
    run_repository.save_preprocessing_run(
        PreprocessingRun(
            run_id="pre-001",
            dataset_id="dataset-001",
            config=PreprocessingConfig(high_pass_hz=1.0, low_pass_hz=40.0),
            status=PreprocessingRunStatus.COMPLETED,
            warnings=["pre warning"],
        )
    )
    run_repository.save_epoch_run(
        EpochRun(
            run_id="epoch-001",
            dataset_id="dataset-001",
            config=EpochConfig(
                preprocessing_run_id="pre-001",
                condition_field="trial_type",
                tmin_seconds=-0.2,
                tmax_seconds=0.8,
            ),
            status=EpochRunStatus.COMPLETED,
            output_metadata={"input_preprocessing_run_id": "pre-001"},
        )
    )
    run_repository.save_erp_run(
        ErpRun(
            run_id="erp-001",
            dataset_id="dataset-001",
            config=ErpConfig(epoch_run_id="epoch-001", conditions=["standard", "target"]),
            status=ErpRunStatus.COMPLETED,
            output_path=str(manifest_path.parent / "erp_metadata.json"),
            output_metadata={
                "artifact_manifest_path": str(manifest_path),
                "artifact_root": str(manifest_path.parent),
                "input_preprocessing_run_id": "pre-001",
                "preview_plot_url": "/artifacts/erp-001/erp_standard.png",
                "comparison_summary_path": str(comparison_path),
            },
            warnings=["erp warning"],
        )
    )

    response = client.post("/erp-runs/erp-001/analysis-report")

    assert response.status_code == 200
    payload = response.json()
    report = payload["report"]
    assert report["dataset_metadata"]["participant_label"] == "sub-001"
    assert report["dataset_metadata"]["recording"]["sampling_rate_hz"] == 100.0
    assert report["event_summary"]["condition_counts"] == {
        "standard": 1,
        "target": 2,
    }
    assert report["preprocessing_config"]["high_pass_hz"] == 1.0
    assert report["epoch_config"]["condition_field"] == "trial_type"
    assert report["erp_config"]["conditions"] == ["standard", "target"]
    assert report["warnings"]["preprocessing"]["warnings"] == ["pre warning"]
    assert report["warnings"]["erp"]["warnings"] == ["erp warning"]
    assert report["preview_plot"]["url"] == "/artifacts/erp-001/erp_standard.png"
    assert report["comparison_summary"]["metric"] == "mean_amplitude_uv"
    assert payload["report_url"] == "/artifacts/erp-001/analysis_report.json"
    assert payload["erp_run"]["output_metadata"]["analysis_report_available"] is True

    report_path = manifest_path.parent / "analysis_report.json"
    assert report_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert any(
        artifact["logical_name"] == "analysis_report"
        for artifact in manifest["artifacts"]
    )


def test_get_export_bundle_includes_missing_artifact_warning(tmp_path, monkeypatch):
    client, run_repository = _client(tmp_path, monkeypatch)
    manifest_path = _copy_erp_fixture_with_figure(tmp_path)
    (manifest_path.parent / "erp_standard.png").unlink()
    run_repository.save_erp_run(
        ErpRun(
            run_id="erp-001",
            dataset_id="dataset-001",
            config=ErpConfig(epoch_run_id="epoch-001"),
            status=ErpRunStatus.COMPLETED,
            finished_at_utc="2026-05-26T00:00:00+00:00",
            output_metadata={"artifact_manifest_path": str(manifest_path)},
        )
    )

    response = client.get("/datasets/dataset-001/export-bundle")

    assert response.status_code == 200
    with zipfile.ZipFile(BytesIO(response.content)) as bundle:
        assert "figures/erp_standard_plot.png" not in bundle.namelist()
        bundle_manifest = json.loads(bundle.read("export_bundle_manifest.json"))

    assert bundle_manifest["diagnostics"]["warnings"][0]["code"] == (
        "artifact_missing"
    )
    assert bundle_manifest["diagnostics"]["warnings"][0]["source"] == "export_bundle"
    assert "erp_standard_plot" in bundle_manifest["diagnostics"]["warnings"][0][
        "impact"
    ]


def test_get_export_bundle_rejects_incomplete_run(tmp_path, monkeypatch):
    client, run_repository = _client(tmp_path, monkeypatch)
    run_repository.save_erp_run(
        ErpRun(
            run_id="erp-001",
            dataset_id="dataset-001",
            config=ErpConfig(epoch_run_id="epoch-001"),
            status=ErpRunStatus.PENDING,
        )
    )

    response = client.get("/erp-runs/erp-001/export-bundle")

    assert response.status_code == 409
    assert response.json()["detail"] == "Run is not completed"


def _client(tmp_path, monkeypatch):
    registry_repository = JsonRegistryRepository(tmp_path / "uploads")
    run_repository = JsonRunRepository(tmp_path / "runs")
    monkeypatch.setattr(api_main, "registry_repository", registry_repository)
    monkeypatch.setattr(api_main, "run_repository", run_repository)
    client = TestClient(api_main.app)
    client.post("/projects", json={"project_id": "project-001", "name": "Memory EEG"})
    client.post(
        "/projects/project-001/experiments",
        json={"experiment_id": "experiment-001", "name": "Oddball task"},
    )
    client.post(
        "/datasets",
        json={
            "dataset_id": "dataset-001",
            "project_id": "project-001",
            "experiment_id": "experiment-001",
            "participant_label": "sub-001",
            "session_label": "ses-001",
        },
    )
    return client, run_repository


def _copy_erp_fixture_with_figure(tmp_path: Path) -> Path:
    run_root = tmp_path / "artifacts" / "erp"
    shutil.copytree(FIXTURE_ROOT / "erp", run_root)
    (run_root / "erp_standard.png").write_bytes(b"png")
    manifest_path = run_root / "artifact_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"].append(
        {
            "logical_name": "erp_standard_plot",
            "artifact_type": "figure_png",
            "path": "erp_standard.png",
        }
    )
    manifest["artifact_count"] = len(manifest["artifacts"])
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest_path
