import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from apps.api import main as api_main
from eeg_core.domain import ErpConfig, ErpRun, ErpRunStatus
from eeg_io.registry import JsonRegistryRepository, JsonRunRepository


def test_get_run_artifact_integrity_reports_ok_missing_and_mismatch(
    tmp_path,
    monkeypatch,
):
    client, run_repository = _client(tmp_path, monkeypatch)
    manifest_path = _write_integrity_manifest(tmp_path)
    run_repository.save_erp_run(
        ErpRun(
            run_id="erp-001",
            dataset_id="dataset-001",
            config=ErpConfig(epoch_run_id="epoch-001"),
            status=ErpRunStatus.COMPLETED,
            output_metadata={"artifact_manifest_path": str(manifest_path)},
        )
    )

    response = client.get("/runs/erp-001/artifact-integrity")

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == "erp-001"
    assert payload["dataset_id"] == "dataset-001"
    assert payload["run_kind"] == "erp"
    assert payload["integrity"]["status"] == "mismatch"
    assert payload["integrity"]["status_counts"] == {
        "ok": 1,
        "missing": 1,
        "mismatch": 1,
    }
    assert {
        item["logical_name"]: item["status"]
        for item in payload["integrity"]["artifacts"]
    } == {
        "ok": "ok",
        "missing": "missing",
        "mismatch": "mismatch",
    }


def test_get_run_artifact_integrity_rejects_manifest_path_escape(
    tmp_path,
    monkeypatch,
):
    client, run_repository = _client(tmp_path, monkeypatch)
    artifact_root = tmp_path / "run"
    artifact_root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("outside", encoding="utf-8")
    manifest_path = artifact_root / "artifact_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_root": str(artifact_root),
                "artifact_count": 1,
                "artifacts": [
                    {
                        "logical_name": "escaped",
                        "artifact_type": "diagnostic_json",
                        "path": str(outside),
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    run_repository.save_erp_run(
        ErpRun(
            run_id="erp-escaped",
            dataset_id="dataset-001",
            config=ErpConfig(epoch_run_id="epoch-001"),
            status=ErpRunStatus.COMPLETED,
            output_metadata={"artifact_manifest_path": str(manifest_path)},
        )
    )

    response = client.get("/runs/erp-escaped/artifact-integrity")

    assert response.status_code == 422
    assert "escapes artifact_root" in response.json()["detail"]


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


def _write_integrity_manifest(tmp_path: Path) -> Path:
    artifact_root = tmp_path / "run"
    artifact_root.mkdir()
    ok = artifact_root / "ok.json"
    mismatch = artifact_root / "mismatch.json"
    missing = artifact_root / "missing.json"
    ok.write_text("ok", encoding="utf-8")
    mismatch.write_text("changed", encoding="utf-8")
    manifest_path = artifact_root / "artifact_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_root": str(artifact_root),
                "artifact_count": 3,
                "artifacts": [
                    {
                        "logical_name": "ok",
                        "artifact_type": "diagnostic_json",
                        "path": str(ok),
                        "checksum_sha256": hashlib.sha256(b"ok").hexdigest(),
                    },
                    {
                        "logical_name": "missing",
                        "artifact_type": "diagnostic_json",
                        "path": str(missing),
                        "checksum_sha256": hashlib.sha256(b"missing").hexdigest(),
                    },
                    {
                        "logical_name": "mismatch",
                        "artifact_type": "diagnostic_json",
                        "path": str(mismatch),
                        "checksum_sha256": hashlib.sha256(b"original").hexdigest(),
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path
