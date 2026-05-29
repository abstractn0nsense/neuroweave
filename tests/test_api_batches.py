from dataclasses import replace

from fastapi.testclient import TestClient

from apps.api import main as api_main
from eeg_core.domain import (
    BatchItemStatus,
    BatchStatus,
    Dataset,
    DatasetStatus,
    EventColumnMapping,
    EventLog,
    NormalizedEvent,
    Recording,
    RecordingMetadata,
)
from eeg_io.registry import (
    JsonBatchRepository,
    JsonRegistryRepository,
    JsonRunRepository,
    JsonWorkflowTemplateRepository,
)


class _NoopBatchWorker:
    def enqueue(self, batch_id: str) -> None:
        return None


def _client_with_repositories(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setattr(
        api_main,
        "registry_repository",
        JsonRegistryRepository(tmp_path / "uploads"),
    )
    monkeypatch.setattr(
        api_main,
        "run_repository",
        JsonRunRepository(tmp_path / "runs"),
    )
    monkeypatch.setattr(
        api_main,
        "template_repository",
        JsonWorkflowTemplateRepository(tmp_path / "templates"),
    )
    monkeypatch.setattr(
        api_main,
        "batch_repository",
        JsonBatchRepository(tmp_path / "batches"),
    )
    monkeypatch.setattr(api_main, "batch_worker", _NoopBatchWorker())
    return TestClient(api_main.app)


def _seed_dataset(dataset_id: str) -> None:
    api_main.registry_repository.save_dataset(
        Dataset(
            dataset_id=dataset_id,
            project_id="project-001",
            experiment_id="experiment-001",
            participant_id=f"participant-{dataset_id}",
            session_id=f"session-{dataset_id}",
            status=DatasetStatus.VALID,
            recording_id=f"recording-{dataset_id}",
            event_log_id=f"event-log-{dataset_id}",
        )
    )
    api_main.registry_repository.save_recording(
        Recording(
            recording_id=f"recording-{dataset_id}",
            dataset_id=dataset_id,
            file_id=f"file-eeg-{dataset_id}",
            metadata=RecordingMetadata(
                dataset_id=dataset_id,
                file_format="fif",
                channel_count=3,
                sampling_rate_hz=256.0,
                duration_seconds=4.0,
                channel_names=["Fp1", "Fp2", "Cz"],
            ),
        )
    )
    api_main.registry_repository.save_event_log(
        EventLog(
            event_log_id=f"event-log-{dataset_id}",
            dataset_id=dataset_id,
            file_id=f"file-events-{dataset_id}",
            mapping=EventColumnMapping(onset_seconds="onset", trial_type="trial_type"),
            row_count=1,
            events=[
                NormalizedEvent(
                    onset_seconds=1.0,
                    source_row=1,
                    trial_type="target",
                )
            ],
        )
    )


def _template_payload(**overrides) -> dict:
    payload = {
        "template_id": "template-001",
        "name": "Oddball preprocessing",
        "workflow": {
            "preprocessing": {
                "high_pass_hz": 1.0,
                "low_pass_hz": 40.0,
                "reference": "average",
            },
            "epoch": None,
            "erp": None,
        },
        "field_policy": {
            "excluded_fields": [],
            "review_required_fields": [],
            "channel_specific_fields": [],
        },
    }
    payload.update(overrides)
    return payload


def test_batch_api_creates_lists_gets_cancels_and_freezes_template_snapshot(
    tmp_path,
    monkeypatch,
):
    client = _client_with_repositories(tmp_path, monkeypatch)
    _seed_dataset("dataset-001")
    _seed_dataset("dataset-002")
    create_template_response = client.post(
        "/workflow-templates",
        json=_template_payload(),
    )
    assert create_template_response.status_code == 201

    create_response = client.post(
        "/batches",
        json={
            "template_id": "template-001",
            "dataset_selection": {
                "dataset_ids": ["dataset-001", "dataset-002"],
                "project_id": "project-001",
                "experiment_id": "experiment-001",
            },
            "requested_by": "analyst@example.com",
            "metadata": {"purpose": "smoke"},
        },
    )
    created = create_response.json()

    assert create_response.status_code == 201
    assert created["batch_id"].startswith("batch-")
    assert created["status"] == "pending"
    assert created["request"]["template_id"] == "template-001"
    assert created["template_snapshot"]["template_name"] == "Oddball preprocessing"
    assert created["template_snapshot"]["template"]["workflow"]["preprocessing"][
        "high_pass_hz"
    ] == 1.0
    assert [item["dataset_id"] for item in created["items"]] == [
        "dataset-001",
        "dataset-002",
    ]
    assert [item["status"] for item in created["items"]] == ["pending", "pending"]
    assert created["items"][0]["attempt"] == 1
    assert created["items"][0]["planned_steps"] == ["preprocessing"]

    list_response = client.get("/batches")
    detail_response = client.get(f"/batches/{created['batch_id']}")
    assert list_response.status_code == 200
    assert list_response.json()["batches"] == [created]
    assert detail_response.status_code == 200
    assert detail_response.json() == created

    update_template_response = client.post(
        "/workflow-templates",
        json=_template_payload(
            name="Changed template",
            workflow={
                "preprocessing": {
                    "high_pass_hz": 2.0,
                    "low_pass_hz": 30.0,
                    "reference": "average",
                },
                "epoch": None,
                "erp": None,
            },
        ),
    )
    assert update_template_response.status_code == 201
    frozen_response = client.get(f"/batches/{created['batch_id']}")
    frozen = frozen_response.json()
    assert frozen["template_snapshot"]["template_name"] == "Oddball preprocessing"
    assert frozen["template_snapshot"]["template"]["workflow"]["preprocessing"][
        "high_pass_hz"
    ] == 1.0
    assert frozen["template_snapshot"]["template_digest_sha256"] == created[
        "template_snapshot"
    ]["template_digest_sha256"]

    cancel_response = client.post(f"/batches/{created['batch_id']}/cancel")
    cancelled = cancel_response.json()
    assert cancel_response.status_code == 200
    assert cancelled["status"] == "cancelled"
    assert [item["status"] for item in cancelled["items"]] == [
        "cancelled",
        "cancelled",
    ]
    assert client.get(f"/batches/{created['batch_id']}").json() == cancelled


def test_batch_api_retries_failed_item_with_same_template_snapshot(
    tmp_path,
    monkeypatch,
):
    client = _client_with_repositories(tmp_path, monkeypatch)
    _seed_dataset("dataset-001")
    create_template_response = client.post(
        "/workflow-templates",
        json=_template_payload(),
    )
    assert create_template_response.status_code == 201
    create_response = client.post(
        "/batches",
        json={
            "template_id": "template-001",
            "dataset_selection": {"dataset_ids": ["dataset-001"]},
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    batch = api_main.batch_repository.get_batch(created["batch_id"])
    assert batch is not None
    failed_item = replace(
        batch.items[0],
        status=BatchItemStatus.FAILED,
        run_ids={"preprocessing": "preprocess-failed"},
        errors=["Synthetic preprocessing failure."],
    )
    api_main.batch_repository.save_batch(
        replace(batch, status=BatchStatus.FAILED, items=[failed_item])
    )

    retry_response = client.post(
        f"/batches/{created['batch_id']}/items/{failed_item.item_id}/retry"
    )

    assert retry_response.status_code == 200
    retried = retry_response.json()
    assert retried["status"] == "pending"
    assert retried["template_snapshot"] == created["template_snapshot"]
    assert retried["items"][0]["status"] == "pending"
    assert retried["items"][0]["attempt"] == 2
    assert retried["items"][0]["run_ids"] == {}
    assert retried["items"][0]["previous_run_ids"] == {
        "preprocessing": "preprocess-failed"
    }
    assert (
        retried["items"][0]["previous_error"]
        == "Synthetic preprocessing failure."
    )


def test_batch_api_rejects_invalid_request_and_missing_template(
    tmp_path,
    monkeypatch,
):
    client = _client_with_repositories(tmp_path, monkeypatch)

    invalid_response = client.post(
        "/batches",
        json={
            "template_id": "template-001",
            "dataset_selection": {"dataset_ids": ["dataset-001", "dataset-001"]},
        },
    )
    missing_template_response = client.post(
        "/batches",
        json={
            "template_id": "missing-template",
            "dataset_selection": {"dataset_ids": ["dataset-001"]},
        },
    )

    assert invalid_response.status_code == 422
    assert "dataset_selection.dataset_ids must be unique" in invalid_response.json()[
        "detail"
    ][0]
    assert missing_template_response.status_code == 404
    assert missing_template_response.json()["detail"] == "Workflow template not found"


def test_batch_api_persists_failed_item_for_missing_dataset(tmp_path, monkeypatch):
    client = _client_with_repositories(tmp_path, monkeypatch)
    create_template_response = client.post(
        "/workflow-templates",
        json=_template_payload(),
    )
    assert create_template_response.status_code == 201

    response = client.post(
        "/batches",
        json={
            "template_id": "template-001",
            "dataset_selection": {"dataset_ids": ["missing-dataset"]},
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["items"][0]["status"] == "failed"
    assert payload["items"][0]["errors"] == ["Dataset not found: missing-dataset"]


def test_batch_api_reports_per_dataset_apply_validation_errors(
    tmp_path,
    monkeypatch,
):
    client = _client_with_repositories(tmp_path, monkeypatch)
    _seed_dataset("dataset-ready")
    api_main.registry_repository.save_dataset(
        Dataset(
            dataset_id="dataset-without-recording",
            project_id="project-001",
            experiment_id="experiment-001",
            participant_id="participant-missing-recording",
            session_id="session-missing-recording",
            status=DatasetStatus.VALID,
            recording_id="missing-recording",
            event_log_id="event-log-missing-recording",
        )
    )
    create_template_response = client.post(
        "/workflow-templates",
        json=_template_payload(),
    )
    assert create_template_response.status_code == 201

    response = client.post(
        "/batches",
        json={
            "template_id": "template-001",
            "dataset_selection": {
                "dataset_ids": ["dataset-ready", "dataset-without-recording"]
            },
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "pending"
    assert payload["items"][0]["status"] == "pending"
    assert payload["items"][0]["errors"] == []
    assert payload["items"][1]["status"] == "failed"
    assert payload["items"][1]["errors"] == [
        "Recording metadata is required before preprocessing."
    ]
