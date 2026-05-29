import pytest

from eeg_core.domain import (
    BatchApplyPreviewResult,
    BatchDatasetSelection,
    BatchItemStatus,
    BatchPlanningError,
    BatchRequest,
    BatchRunBindings,
    Dataset,
    DatasetStatus,
    PreprocessingConfig,
    WorkflowTemplate,
    WorkflowTemplateFieldPolicyEntry,
    WorkflowTemplateWorkflow,
    plan_batch_run,
    workflow_template_digest_sha256,
)


def _dataset(dataset_id: str) -> Dataset:
    return Dataset(
        dataset_id=dataset_id,
        project_id="project-001",
        experiment_id="experiment-001",
        participant_id=f"participant-{dataset_id}",
        session_id=f"session-{dataset_id}",
        status=DatasetStatus.VALID,
        recording_id=f"recording-{dataset_id}",
        event_log_id=f"event-log-{dataset_id}",
    )


def _template() -> WorkflowTemplate:
    return WorkflowTemplate(
        template_id="template-001",
        name="Oddball preprocessing",
        created_at_utc="2026-05-28T00:00:00Z",
        updated_at_utc="2026-05-28T00:10:00Z",
        workflow=WorkflowTemplateWorkflow(
            preprocessing=PreprocessingConfig(reference="average")
        ),
    )


def _request(dataset_ids: list[str], *, dry_run: bool = False) -> BatchRequest:
    return BatchRequest(
        template_id="template-001",
        dataset_selection=BatchDatasetSelection(dataset_ids=dataset_ids),
        dry_run=dry_run,
    )


def test_batch_planning_service_runs_preview_for_each_selected_dataset():
    template = _template()
    datasets = {
        dataset_id: _dataset(dataset_id)
        for dataset_id in ("dataset-ready", "dataset-review", "dataset-invalid")
    }
    preview_calls: list[str] = []

    def preview_resolver(
        resolved_template: WorkflowTemplate,
        dataset: Dataset,
    ) -> BatchApplyPreviewResult:
        assert resolved_template == template
        preview_calls.append(dataset.dataset_id)
        if dataset.dataset_id == "dataset-review":
            return BatchApplyPreviewResult(
                target_dataset_id=dataset.dataset_id,
                status="requires_review",
                configs=template.workflow,
                review_required_fields=[
                    WorkflowTemplateFieldPolicyEntry(
                        path="workflow.preprocessing.ica.eog_channels",
                        reason="channel_specific",
                        default_action="validate_against_target_channels",
                    )
                ],
                warnings=["Channel-specific fields require review."],
            )
        if dataset.dataset_id == "dataset-invalid":
            return BatchApplyPreviewResult(
                target_dataset_id=dataset.dataset_id,
                status="invalid",
                configs=template.workflow,
                errors=["Recording metadata is required before preprocessing."],
            )
        return BatchApplyPreviewResult(
            target_dataset_id=dataset.dataset_id,
            status="ready",
            configs=template.workflow,
        )

    result = plan_batch_run(
        batch_id="batch-001",
        request=_request(
            [
                "dataset-ready",
                "dataset-review",
                "dataset-invalid",
                "dataset-missing",
            ]
        ),
        template=template,
        captured_at_utc="2026-05-28T00:15:00Z",
        dataset_resolver=datasets.get,
        apply_preview_resolver=preview_resolver,
        run_bindings_resolver=lambda dataset_id: BatchRunBindings(
            preprocessing_run_id=f"preprocess-{dataset_id}"
        ),
    )

    assert preview_calls == ["dataset-ready", "dataset-review", "dataset-invalid"]
    assert result.validation.valid
    assert result.plan.status.value == "pending"
    assert result.plan.template_snapshot.template_digest_sha256 == (
        workflow_template_digest_sha256(template)
    )
    assert [item.dataset_id for item in result.plan.items] == [
        "dataset-ready",
        "dataset-review",
        "dataset-invalid",
        "dataset-missing",
    ]
    assert [item.status for item in result.plan.items] == [
        BatchItemStatus.PENDING,
        BatchItemStatus.FAILED,
        BatchItemStatus.FAILED,
        BatchItemStatus.FAILED,
    ]
    assert [step.value for step in result.plan.items[0].planned_steps] == [
        "preprocessing"
    ]
    assert result.plan.items[0].bindings.preprocessing_run_id == (
        "preprocess-dataset-ready"
    )
    assert result.plan.items[1].review_required_fields[0].path == (
        "workflow.preprocessing.ica.eog_channels"
    )
    assert result.plan.items[1].warnings == [
        "Channel-specific fields require review.",
    ]
    assert result.plan.items[1].errors == [
        "Template apply requires review before batch execution.",
    ]
    assert result.plan.items[2].errors == [
        "Recording metadata is required before preprocessing."
    ]
    assert result.plan.items[3].errors == ["Dataset not found: dataset-missing"]
    assert [dataset.valid for dataset in result.datasets] == [
        True,
        False,
        False,
        False,
    ]


def test_batch_planning_service_marks_dry_run_items_before_execution():
    template = _template()
    result = plan_batch_run(
        batch_id="batch-001",
        request=_request(["dataset-001"], dry_run=True),
        template=template,
        captured_at_utc="2026-05-28T00:15:00Z",
        dataset_resolver=lambda dataset_id: _dataset(dataset_id),
        apply_preview_resolver=lambda _, dataset: BatchApplyPreviewResult(
            target_dataset_id=dataset.dataset_id,
            status="ready",
            configs=template.workflow,
        ),
        run_bindings_resolver=lambda _: BatchRunBindings(),
    )

    assert result.plan.warnings == [
        "BatchRequest dry_run does not create runnable batch items."
    ]
    assert result.plan.items[0].warnings == [
        "Batch request is dry_run; worker execution is disabled."
    ]


def test_batch_planning_service_rejects_invalid_request_before_preview():
    preview_calls: list[str] = []

    with pytest.raises(BatchPlanningError) as exc_info:
        plan_batch_run(
            batch_id="batch-001",
            request=_request(["dataset-001", "dataset-001"]),
            template=_template(),
            captured_at_utc="2026-05-28T00:15:00Z",
            dataset_resolver=lambda dataset_id: _dataset(dataset_id),
            apply_preview_resolver=lambda template, dataset: preview_calls.append(
                dataset.dataset_id
            ),
            run_bindings_resolver=lambda _: BatchRunBindings(),
        )

    assert preview_calls == []
    assert "dataset_selection.dataset_ids must be unique" in exc_info.value.errors[0]
