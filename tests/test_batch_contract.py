from dataclasses import asdict
import json

from eeg_core.domain import (
    BatchDatasetSelection,
    BatchItemStatus,
    BatchRequest,
    BatchRunBindings,
    BatchRunPlan,
    BatchStatus,
    BatchSubjectRunPlan,
    PreprocessingConfig,
    RunKind,
    WorkflowTemplate,
    WorkflowTemplateFieldPolicyEntry,
    WorkflowTemplateWorkflow,
    create_batch_template_snapshot,
    validate_batch_request,
    validate_batch_run_plan,
    workflow_template_digest_sha256,
)


def _template(**overrides) -> WorkflowTemplate:
    values = {
        "template_id": "template-001",
        "name": "Oddball ERP",
        "created_at_utc": "2026-05-28T00:00:00Z",
        "updated_at_utc": "2026-05-28T00:10:00Z",
        "workflow": WorkflowTemplateWorkflow(
            preprocessing=PreprocessingConfig(reference="average")
        ),
    }
    values.update(overrides)
    return WorkflowTemplate(**values)


def _batch_request(dataset_ids: list[str] | None = None) -> BatchRequest:
    return BatchRequest(
        template_id="template-001",
        dataset_selection=BatchDatasetSelection(
            dataset_ids=(
                ["dataset-001", "dataset-002"] if dataset_ids is None else dataset_ids
            ),
            project_id="project-001",
            experiment_id="experiment-001",
        ),
    )


def _batch_plan(
    *,
    status: BatchStatus = BatchStatus.PENDING,
    item_statuses: list[BatchItemStatus] | None = None,
) -> BatchRunPlan:
    request = _batch_request()
    template = _template()
    snapshot = create_batch_template_snapshot(
        template,
        captured_at_utc="2026-05-28T00:15:00Z",
    )
    statuses = item_statuses or [BatchItemStatus.PENDING, BatchItemStatus.PENDING]
    items = [
        BatchSubjectRunPlan(
            item_id=f"batch-001-item-{index + 1:03d}",
            dataset_id=dataset_id,
            status=statuses[index],
            configs=template.workflow,
            bindings=BatchRunBindings(),
            planned_steps=[RunKind.PREPROCESSING],
            excluded_fields=[
                WorkflowTemplateFieldPolicyEntry(
                    path="workflow.preprocessing.manual_bad_channels",
                    reason="subject_specific",
                    default_action="omit",
                )
            ],
            review_required_fields=[
                WorkflowTemplateFieldPolicyEntry(
                    path="workflow.preprocessing.ica.eog_channels",
                    reason="channel_specific",
                    default_action="validate_against_target_channels",
                )
            ],
        )
        for index, dataset_id in enumerate(request.dataset_selection.dataset_ids)
    ]
    return BatchRunPlan(
        batch_id="batch-001",
        request=request,
        template_snapshot=snapshot,
        items=items,
        status=status,
        created_at_utc="2026-05-28T00:16:00Z",
        updated_at_utc="2026-05-28T00:16:00Z",
    )


def test_batch_status_enum_values_are_contract():
    assert [status.value for status in BatchStatus] == [
        "pending",
        "running",
        "partial",
        "completed",
        "failed",
        "cancelling",
        "cancelled",
    ]


def test_batch_request_schema_validates_multi_dataset_selection():
    request = _batch_request(["dataset-001", "dataset-002"])

    validation = validate_batch_request(request)

    assert validation.valid
    payload = json.loads(json.dumps(asdict(request)))
    assert payload == {
        "template_id": "template-001",
        "dataset_selection": {
            "dataset_ids": ["dataset-001", "dataset-002"],
            "project_id": "project-001",
            "experiment_id": "experiment-001",
        },
        "requested_by": None,
        "continue_on_error": True,
        "dry_run": False,
        "metadata": {},
    }


def test_batch_request_rejects_empty_and_duplicate_dataset_selection():
    empty_validation = validate_batch_request(_batch_request([]))
    duplicate_validation = validate_batch_request(
        _batch_request(["dataset-001", "dataset-001"])
    )

    assert not empty_validation.valid
    assert "dataset_selection.dataset_ids must not be empty" in (
        empty_validation.errors[0]
    )
    assert not duplicate_validation.valid
    assert "dataset_selection.dataset_ids must be unique" in (
        duplicate_validation.errors[0]
    )


def test_batch_template_snapshot_embeds_template_and_digest():
    template = _template()

    snapshot = create_batch_template_snapshot(
        template,
        captured_at_utc="2026-05-28T00:15:00Z",
    )

    assert snapshot.template_id == "template-001"
    assert snapshot.template_updated_at_utc == template.updated_at_utc
    assert snapshot.template == template
    assert snapshot.template_digest_sha256 == workflow_template_digest_sha256(
        template
    )
    changed_template = _template(name="Changed")
    assert snapshot.template_digest_sha256 != workflow_template_digest_sha256(
        changed_template
    )


def test_batch_run_plan_serializes_per_subject_items():
    plan = _batch_plan()

    validation = validate_batch_run_plan(plan)
    payload = json.loads(json.dumps(asdict(plan)))

    assert validation.valid
    assert payload["schema_version"] == 1
    assert payload["status"] == "pending"
    assert payload["template_snapshot"]["template_id"] == "template-001"
    assert payload["items"][0]["dataset_id"] == "dataset-001"
    assert payload["items"][0]["status"] == "pending"
    assert payload["items"][0]["planned_steps"] == ["preprocessing"]
    assert payload["items"][0]["configs"]["preprocessing"]["reference"] == "average"
    assert payload["items"][0]["configs"]["epoch"] is None
    assert payload["items"][0]["configs"]["erp"] is None
    assert payload["items"][0]["excluded_fields"][0]["path"] == (
        "workflow.preprocessing.manual_bad_channels"
    )
    assert payload["items"][0]["review_required_fields"][0]["path"] == (
        "workflow.preprocessing.ica.eog_channels"
    )


def test_batch_run_plan_requires_items_to_match_selection_order():
    plan = _batch_plan()
    reordered_plan = BatchRunPlan(
        **{
            **asdict(plan),
            "request": plan.request,
            "template_snapshot": plan.template_snapshot,
            "items": list(reversed(plan.items)),
        }
    )

    validation = validate_batch_run_plan(reordered_plan)

    assert not validation.valid
    assert "items must match dataset_selection.dataset_ids order" in (
        validation.errors[0]
    )


def test_batch_partial_status_requires_completed_and_failed_items():
    valid_partial = _batch_plan(
        status=BatchStatus.PARTIAL,
        item_statuses=[BatchItemStatus.COMPLETED, BatchItemStatus.FAILED],
    )
    invalid_partial = _batch_plan(
        status=BatchStatus.PARTIAL,
        item_statuses=[BatchItemStatus.FAILED, BatchItemStatus.FAILED],
    )

    assert validate_batch_run_plan(valid_partial).valid
    invalid_validation = validate_batch_run_plan(invalid_partial)
    assert not invalid_validation.valid
    assert "partial status requires" in invalid_validation.errors[0]
