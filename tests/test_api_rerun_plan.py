import hashlib
import json
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
    RecordingMetadata,
    SourceFileMetadata,
)
from eeg_io.registry import JsonRegistryRepository, JsonRunRepository


def test_get_run_rerun_plan_reports_ready_erp_chain(tmp_path, monkeypatch):
    client, registry_repository, run_repository = _client(tmp_path, monkeypatch)
    _save_recording_with_sources(registry_repository, tmp_path)
    _save_event_log_with_source(registry_repository, tmp_path)
    preprocessing_manifest = _write_manifest(tmp_path, "preprocessing")
    epoch_manifest = _write_manifest(tmp_path, "epoch")
    erp_manifest = _write_manifest(tmp_path, "erp")
    run_repository.save_preprocessing_run(
        PreprocessingRun(
            run_id="preprocess-001",
            dataset_id="dataset-001",
            config=PreprocessingConfig(reference="average"),
            status=PreprocessingRunStatus.COMPLETED,
            output_metadata={"artifact_manifest_path": str(preprocessing_manifest)},
        )
    )
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
            output_metadata={
                "artifact_manifest_path": str(epoch_manifest),
                "input_preprocessing_run_id": "preprocess-001",
            },
        )
    )
    erp_run = ErpRun(
        run_id="erp-001",
        dataset_id="dataset-001",
        config=ErpConfig(epoch_run_id="epoch-001", conditions=["target"]),
        status=ErpRunStatus.COMPLETED,
        output_metadata={
            "artifact_manifest_path": str(erp_manifest),
            "input_epoch_run_id": "epoch-001",
            "input_preprocessing_run_id": "preprocess-001",
        },
    )
    run_repository.save_erp_run(erp_run)

    response = client.get("/runs/erp-001/rerun-plan")

    assert response.status_code == 200
    payload = response.json()
    plan = payload["plan"]
    assert plan["status"] == "ready"
    assert plan["can_rerun"] is True
    assert plan["would_execute"] is False
    assert plan["blockers"] == []
    assert plan["warnings"] == []
    assert [item["run_kind"] for item in plan["chain"]] == [
        "preprocessing",
        "epoch",
        "erp",
    ]
    assert run_repository.get_erp_run("erp-001") == erp_run


def test_get_run_rerun_plan_blocks_on_missing_inputs_and_config_mismatch(
    tmp_path,
    monkeypatch,
):
    client, registry_repository, run_repository = _client(tmp_path, monkeypatch)
    missing_source = tmp_path / "missing" / "sub-001.set"
    registry_repository.save_recording(
        Recording(
            recording_id="recording-001",
            dataset_id="dataset-001",
            file_id="eeg-file-001",
            metadata=_recording_metadata(
                source_files=[
                    SourceFileMetadata(
                        role="eeg",
                        original_filename="sub-001.set",
                        stored_path=str(missing_source),
                    )
                ]
            ),
        )
    )
    epoch_manifest = _write_manifest(tmp_path, "epoch")
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
            output_metadata={
                "artifact_manifest_path": str(epoch_manifest),
                "input_preprocessing_run_id": "preprocess-other",
            },
        )
    )
    run_repository.save_erp_run(
        ErpRun(
            run_id="erp-001",
            dataset_id="dataset-001",
            config=ErpConfig(epoch_run_id="epoch-001"),
            status=ErpRunStatus.COMPLETED,
            output_metadata={
                "artifact_manifest_path": str(tmp_path / "erp" / "missing.json"),
                "input_epoch_run_id": "epoch-other",
            },
        )
    )

    response = client.get("/runs/erp-001/rerun-plan")

    assert response.status_code == 200
    plan = response.json()["plan"]
    codes = {diagnostic["code"] for diagnostic in plan["blockers"]}
    assert plan["status"] == "blocked"
    assert plan["can_rerun"] is False
    assert "source_file_missing" in codes
    assert "event_log_missing" in codes
    assert "parent_run_missing" in codes
    assert "artifact_manifest_missing" in codes
    assert "config_parent_mismatch" in codes
    assert plan["diagnostics"]["warnings"] == plan["warnings"]
    assert plan["diagnostics"]["blockers"] == plan["blockers"]


def test_get_run_rerun_plan_reports_partially_recoverable_warnings(
    tmp_path,
    monkeypatch,
):
    client, registry_repository, run_repository = _client(tmp_path, monkeypatch)
    registry_repository.save_recording(
        Recording(
            recording_id="recording-001",
            dataset_id="dataset-001",
            file_id="eeg-file-001",
            metadata=_recording_metadata(source_files=[]),
        )
    )
    manifest_path = _write_manifest(tmp_path, "preprocessing")
    run_repository.save_preprocessing_run(
        PreprocessingRun(
            run_id="preprocess-001",
            dataset_id="dataset-001",
            config=PreprocessingConfig(reference="average"),
            status=PreprocessingRunStatus.COMPLETED,
            output_metadata={"artifact_manifest_path": str(manifest_path)},
        )
    )

    response = client.get("/runs/preprocess-001/rerun-plan")

    assert response.status_code == 200
    plan = response.json()["plan"]
    assert plan["status"] == "partially_recoverable"
    assert plan["can_rerun"] is True
    assert plan["blockers"] == []
    assert [warning["code"] for warning in plan["warnings"]] == [
        "recording_source_files_missing"
    ]


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
    return client, registry_repository, run_repository


def _save_recording_with_sources(
    registry_repository: JsonRegistryRepository,
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "sources" / "sub-001.set"
    source_path.parent.mkdir(parents=True)
    source_path.write_text("eeg", encoding="utf-8")
    registry_repository.save_recording(
        Recording(
            recording_id="recording-001",
            dataset_id="dataset-001",
            file_id="eeg-file-001",
            metadata=_recording_metadata(
                source_files=[
                    SourceFileMetadata(
                        role="eeg",
                        original_filename="sub-001.set",
                        stored_path=str(source_path),
                    )
                ]
            ),
        )
    )


def _save_event_log_with_source(
    registry_repository: JsonRegistryRepository,
    tmp_path: Path,
) -> None:
    event_path = tmp_path / "sources" / "events.tsv"
    event_path.parent.mkdir(parents=True, exist_ok=True)
    event_path.write_text("onset\ttrial_type\n0.1\ttarget\n", encoding="utf-8")
    registry_repository.save_event_log(
        EventLog(
            event_log_id="events-001",
            dataset_id="dataset-001",
            file_id="events-file-001",
            mapping=EventColumnMapping(onset_seconds="onset"),
            row_count=1,
            condition_column="trial_type",
            provenance={
                "sources": [
                    {
                        "role": "event_file",
                        "original_filename": "events.tsv",
                        "stored_path": str(event_path),
                    }
                ]
            },
            events=[NormalizedEvent(onset_seconds=0.1, source_row=1)],
        )
    )


def _recording_metadata(
    *,
    source_files: list[SourceFileMetadata],
) -> RecordingMetadata:
    return RecordingMetadata(
        dataset_id="dataset-001",
        file_format="set",
        channel_count=2,
        sampling_rate_hz=250.0,
        duration_seconds=10.0,
        channel_names=["Cz", "Pz"],
        source_files=source_files,
        sidecar_discovery={"schema_version": 1},
    )


def _write_manifest(tmp_path: Path, name: str) -> Path:
    artifact_root = tmp_path / "artifacts" / name
    artifact_root.mkdir(parents=True)
    artifact_path = artifact_root / f"{name}.json"
    artifact_path.write_text(f'{{"name": "{name}"}}\n', encoding="utf-8")
    manifest_path = artifact_root / "artifact_manifest.json"
    content = artifact_path.read_bytes()
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_root": str(artifact_root),
                "artifact_count": 1,
                "artifacts": [
                    {
                        "logical_name": name,
                        "artifact_type": "diagnostic_json",
                        "path": str(artifact_path),
                        "size_bytes": len(content),
                        "checksum_sha256": hashlib.sha256(content).hexdigest(),
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path
