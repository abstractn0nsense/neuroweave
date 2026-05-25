import shutil
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
    PreprocessingConfig,
    PreprocessingRun,
    PreprocessingRunStatus,
)
from eeg_io.registry import JsonRegistryRepository, JsonRunRepository


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "qc"


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


def _copy_fixture(tmp_path, name: str) -> Path:
    destination = tmp_path / "artifacts" / name
    shutil.copytree(FIXTURE_ROOT / name, destination)
    return destination / "artifact_manifest.json"


def test_get_qc_summary_uses_latest_completed_run(tmp_path, monkeypatch):
    client, run_repository = _client(tmp_path, monkeypatch)
    preprocessing_manifest = _copy_fixture(tmp_path, "preprocessing")
    erp_manifest = _copy_fixture(tmp_path, "erp")
    run_repository.save_preprocessing_run(
        PreprocessingRun(
            run_id="preprocess-001",
            dataset_id="dataset-001",
            config=PreprocessingConfig(),
            status=PreprocessingRunStatus.COMPLETED,
            finished_at_utc="2026-05-26T00:00:00+00:00",
            output_metadata={"artifact_manifest_path": str(preprocessing_manifest)},
        )
    )
    run_repository.save_erp_run(
        ErpRun(
            run_id="erp-001",
            dataset_id="dataset-001",
            config=ErpConfig(epoch_run_id="epoch-001"),
            status=ErpRunStatus.COMPLETED,
            finished_at_utc="2026-05-26T00:01:00+00:00",
            output_metadata={"artifact_manifest_path": str(erp_manifest)},
        )
    )

    response = client.get("/datasets/dataset-001/qc-summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["dataset_id"] == "dataset-001"
    assert payload["run_id"] == "erp-001"
    assert payload["run_kind"] == "erp"
    assert payload["summary"]["erp"]["condition_count"] == 2


def test_get_qc_summary_accepts_specific_run_id(tmp_path, monkeypatch):
    client, run_repository = _client(tmp_path, monkeypatch)
    preprocessing_manifest = _copy_fixture(tmp_path, "preprocessing")
    run_repository.save_preprocessing_run(
        PreprocessingRun(
            run_id="preprocess-001",
            dataset_id="dataset-001",
            config=PreprocessingConfig(),
            status=PreprocessingRunStatus.COMPLETED,
            finished_at_utc="2026-05-26T00:00:00+00:00",
            output_metadata={"artifact_manifest_path": str(preprocessing_manifest)},
        )
    )

    response = client.get(
        "/datasets/dataset-001/qc-summary",
        params={"run_id": "preprocess-001"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == "preprocess-001"
    assert payload["run_kind"] == "preprocessing"
    assert payload["summary"]["preprocessing"]["reference"]["status"] == "applied"


def test_get_qc_summary_includes_missing_artifact_diagnostics(tmp_path, monkeypatch):
    client, run_repository = _client(tmp_path, monkeypatch)
    epoch_directory = tmp_path / "artifacts" / "epoch"
    shutil.copytree(FIXTURE_ROOT / "epoch", epoch_directory)
    (epoch_directory / "drop_log.json").unlink()
    run_repository.save_epoch_run(
        EpochRun(
            run_id="epoch-001",
            dataset_id="dataset-001",
            config=EpochConfig(
                preprocessing_run_id="preprocess-001",
                condition_field="trial_type",
                tmin_seconds=-0.2,
                tmax_seconds=0.8,
            ),
            status=EpochRunStatus.COMPLETED,
            finished_at_utc="2026-05-26T00:00:00+00:00",
            output_metadata={
                "artifact_manifest_path": str(epoch_directory / "artifact_manifest.json")
            },
        )
    )

    response = client.get("/datasets/dataset-001/qc-summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["artifact_manifest"]["missing_artifacts"][0][
        "logical_name"
    ] == "drop_log"
    assert payload["summary"]["epoch"]["drop_log"] == {
        "summary": {},
        "entry_count": 0,
    }


def test_get_qc_summary_rejects_incomplete_run(tmp_path, monkeypatch):
    client, run_repository = _client(tmp_path, monkeypatch)
    run_repository.save_preprocessing_run(
        PreprocessingRun(
            run_id="preprocess-001",
            dataset_id="dataset-001",
            config=PreprocessingConfig(),
            status=PreprocessingRunStatus.PENDING,
        )
    )

    response = client.get(
        "/datasets/dataset-001/qc-summary",
        params={"run_id": "preprocess-001"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Run is not completed"


def test_get_qc_summary_requires_completed_run(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)

    response = client.get("/datasets/dataset-001/qc-summary")

    assert response.status_code == 404
    assert response.json()["detail"] == "Completed QC run not found"
