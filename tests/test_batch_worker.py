from dataclasses import replace
import json

from apps.api import main as api_main
from eeg_core.domain import (
    BatchDatasetSelection,
    BatchItemStatus,
    BatchRequest,
    BatchRunBindings,
    BatchStatus,
    Dataset,
    DatasetStatus,
    EventColumnMapping,
    EventLog,
    NormalizedEvent,
    PreprocessingConfig,
    PreprocessingRun,
    PreprocessingRunStatus,
    Recording,
    RecordingMetadata,
    UploadedFile,
    UploadedFileKind,
    WorkflowTemplate,
    WorkflowTemplateWorkflow,
    BatchApplyPreviewResult,
    plan_batch_run,
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


def _configure_repositories(tmp_path, monkeypatch) -> None:
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


def _seed_dataset(tmp_path, dataset_id: str) -> None:
    eeg_path = tmp_path / "uploads" / f"{dataset_id}.fif"
    eeg_path.parent.mkdir(parents=True, exist_ok=True)
    eeg_path.write_bytes(b"placeholder")
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
    api_main.registry_repository.save_uploaded_file(
        UploadedFile(
            file_id=f"file-eeg-{dataset_id}",
            dataset_id=dataset_id,
            kind=UploadedFileKind.EEG,
            original_filename=f"{dataset_id}.fif",
            stored_path=str(eeg_path),
            size_bytes=11,
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


def _template() -> WorkflowTemplate:
    return WorkflowTemplate(
        template_id="template-001",
        name="Batch preprocessing",
        created_at_utc="2026-05-28T00:00:00Z",
        updated_at_utc="2026-05-28T00:10:00Z",
        workflow=WorkflowTemplateWorkflow(
            preprocessing=PreprocessingConfig(reference="average")
        ),
    )


def _save_batch_plan(dataset_ids: list[str]) -> None:
    template = _template()
    plan = plan_batch_run(
        batch_id="batch-001",
        request=BatchRequest(
            template_id=template.template_id,
            dataset_selection=BatchDatasetSelection(dataset_ids=dataset_ids),
        ),
        template=template,
        captured_at_utc="2026-05-28T00:15:00Z",
        dataset_resolver=api_main.registry_repository.get_dataset,
        apply_preview_resolver=lambda resolved_template, dataset: (
            BatchApplyPreviewResult(
                target_dataset_id=dataset.dataset_id,
                status="ready",
                configs=resolved_template.workflow,
            )
        ),
        run_bindings_resolver=lambda _: BatchRunBindings(),
    ).plan
    api_main.batch_repository.save_batch(plan)


def test_batch_worker_runs_preprocessing_sequentially_and_allows_partial(
    tmp_path,
    monkeypatch,
):
    _configure_repositories(tmp_path, monkeypatch)
    _seed_dataset(tmp_path, "dataset-001")
    _seed_dataset(tmp_path, "dataset-002")
    _save_batch_plan(["dataset-001", "dataset-002"])
    calls: list[str] = []

    def fake_execute_preprocessing(run_id: str) -> None:
        run = api_main.run_repository.get_preprocessing_run(run_id)
        assert run is not None
        calls.append(run.dataset_id)
        if run.dataset_id == "dataset-001":
            api_main.run_repository.save_preprocessing_run(
                replace(
                    run,
                    status=PreprocessingRunStatus.COMPLETED,
                    finished_at_utc="2026-05-28T00:16:00Z",
                    warnings=["Completed with warning."],
                )
            )
            return
        api_main.run_repository.save_preprocessing_run(
            replace(
                run,
                status=PreprocessingRunStatus.FAILED,
                finished_at_utc="2026-05-28T00:17:00Z",
                errors=["Synthetic preprocessing failure."],
            )
        )

    monkeypatch.setattr(
        api_main,
        "_execute_preprocessing_run",
        fake_execute_preprocessing,
    )

    api_main._execute_batch_run("batch-001")

    batch = api_main.batch_repository.get_batch("batch-001")
    assert batch is not None
    assert calls == ["dataset-001", "dataset-002"]
    assert batch.status == BatchStatus.PARTIAL
    assert [item.status for item in batch.items] == [
        BatchItemStatus.COMPLETED,
        BatchItemStatus.FAILED,
    ]
    assert batch.items[0].run_ids["preprocessing"].startswith("preprocess-")
    assert batch.items[0].warnings == ["Completed with warning."]
    assert batch.items[1].errors == ["Synthetic preprocessing failure."]
    summary_path = api_main._batch_summary_artifact_path("batch-001")
    assert summary_path.is_file()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["batch_id"] == "batch-001"
    assert summary["status"] == "partial"
    assert summary["item_counts"] == {
        "total": 2,
        "pending": 0,
        "running": 0,
        "completed": 1,
        "failed": 1,
        "cancelling": 0,
        "cancelled": 0,
    }
    assert summary["items"][0]["artifact_manifests"]["preprocessing"]["run_id"] == (
        batch.items[0].run_ids["preprocessing"]
    )


def test_batch_worker_cancel_checkpoint_cancels_pending_items(tmp_path, monkeypatch):
    _configure_repositories(tmp_path, monkeypatch)
    _seed_dataset(tmp_path, "dataset-001")
    _seed_dataset(tmp_path, "dataset-002")
    _save_batch_plan(["dataset-001", "dataset-002"])
    batch = api_main.batch_repository.get_batch("batch-001")
    assert batch is not None
    api_main.batch_repository.save_batch(
        replace(batch, status=BatchStatus.CANCELLING)
    )

    api_main._execute_batch_run("batch-001")

    cancelled = api_main.batch_repository.get_batch("batch-001")
    assert cancelled is not None
    assert cancelled.status == BatchStatus.CANCELLED
    assert [item.status for item in cancelled.items] == [
        BatchItemStatus.CANCELLED,
        BatchItemStatus.CANCELLED,
    ]
    assert api_main.run_repository.list_preprocessing_runs() == []


def test_cancel_batch_marks_active_preprocessing_run_cancelling(tmp_path, monkeypatch):
    _configure_repositories(tmp_path, monkeypatch)
    _seed_dataset(tmp_path, "dataset-001")
    _save_batch_plan(["dataset-001"])
    batch = api_main.batch_repository.get_batch("batch-001")
    assert batch is not None
    run = PreprocessingRun(
        run_id="preprocess-001",
        dataset_id="dataset-001",
        config=PreprocessingConfig(reference="average"),
        status=PreprocessingRunStatus.RUNNING,
    )
    api_main.run_repository.save_preprocessing_run(run)
    running_item = replace(
        batch.items[0],
        status=BatchItemStatus.RUNNING,
        run_ids={"preprocessing": "preprocess-001"},
    )
    api_main.batch_repository.save_batch(
        replace(batch, status=BatchStatus.RUNNING, items=[running_item])
    )

    cancelled_response = api_main.cancel_batch("batch-001")

    updated_run = api_main.run_repository.get_preprocessing_run("preprocess-001")
    assert updated_run is not None
    assert updated_run.status == PreprocessingRunStatus.CANCELLING
    assert cancelled_response.status == "cancelling"


def test_failed_batch_item_retry_keeps_snapshot_and_creates_new_run_id(
    tmp_path,
    monkeypatch,
):
    _configure_repositories(tmp_path, monkeypatch)
    monkeypatch.setattr(api_main, "batch_worker", _NoopBatchWorker())
    _seed_dataset(tmp_path, "dataset-001")
    _save_batch_plan(["dataset-001"])
    batch = api_main.batch_repository.get_batch("batch-001")
    assert batch is not None
    original_snapshot = batch.template_snapshot
    failed_item = replace(
        batch.items[0],
        status=BatchItemStatus.FAILED,
        run_ids={"preprocessing": "preprocess-failed"},
        errors=["Synthetic preprocessing failure."],
    )
    api_main.batch_repository.save_batch(
        replace(batch, status=BatchStatus.FAILED, items=[failed_item])
    )

    retry_response = api_main.retry_batch_item("batch-001", failed_item.item_id)
    retry_batch = api_main.batch_repository.get_batch("batch-001")
    assert retry_batch is not None
    assert retry_response.status == "pending"
    assert retry_batch.template_snapshot == original_snapshot
    assert retry_batch.items[0].status == BatchItemStatus.PENDING
    assert retry_batch.items[0].attempt == 2
    assert retry_batch.items[0].run_ids == {}
    assert retry_batch.items[0].previous_run_ids == {
        "preprocessing": "preprocess-failed"
    }
    assert retry_batch.items[0].previous_error == "Synthetic preprocessing failure."

    def fake_execute_preprocessing(run_id: str) -> None:
        assert run_id != "preprocess-failed"
        run = api_main.run_repository.get_preprocessing_run(run_id)
        assert run is not None
        api_main.run_repository.save_preprocessing_run(
            replace(
                run,
                status=PreprocessingRunStatus.COMPLETED,
                finished_at_utc="2026-05-28T00:20:00Z",
            )
        )

    monkeypatch.setattr(
        api_main,
        "_execute_preprocessing_run",
        fake_execute_preprocessing,
    )

    api_main._execute_batch_run("batch-001")

    completed = api_main.batch_repository.get_batch("batch-001")
    assert completed is not None
    assert completed.status == BatchStatus.COMPLETED
    assert completed.template_snapshot == original_snapshot
    assert completed.items[0].status == BatchItemStatus.COMPLETED
    assert completed.items[0].attempt == 2
    assert completed.items[0].run_ids["preprocessing"] != "preprocess-failed"
    assert completed.items[0].previous_run_ids == {
        "preprocessing": "preprocess-failed"
    }
    assert completed.items[0].previous_error == "Synthetic preprocessing failure."
