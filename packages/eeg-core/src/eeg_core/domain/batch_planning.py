from collections.abc import Callable
from dataclasses import dataclass, field

from eeg_core.domain.ingestion import (
    BatchItemStatus,
    BatchRequest,
    BatchRunBindings,
    BatchRunPlan,
    BatchRunPlanValidation,
    BatchStatus,
    BatchSubjectRunPlan,
    Dataset,
    RunKind,
    WorkflowTemplate,
    WorkflowTemplateFieldPolicyEntry,
    WorkflowTemplateWorkflow,
    create_batch_template_snapshot,
    validate_batch_request,
    validate_batch_run_plan,
)


@dataclass(frozen=True)
class BatchApplyPreviewResult:
    target_dataset_id: str
    status: str
    configs: WorkflowTemplateWorkflow
    excluded_fields: list[WorkflowTemplateFieldPolicyEntry] = field(
        default_factory=list
    )
    review_required_fields: list[WorkflowTemplateFieldPolicyEntry] = field(
        default_factory=list
    )
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BatchDatasetPlanningResult:
    dataset_id: str
    item_id: str
    item_status: BatchItemStatus
    preview_status: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return self.item_status != BatchItemStatus.FAILED and not self.errors

    @property
    def requires_review(self) -> bool:
        return self.preview_status == "requires_review"


@dataclass(frozen=True)
class BatchPlanningResult:
    plan: BatchRunPlan
    validation: BatchRunPlanValidation
    datasets: list[BatchDatasetPlanningResult]


class BatchPlanningError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


DatasetResolver = Callable[[str], Dataset | None]
ApplyPreviewResolver = Callable[[WorkflowTemplate, Dataset], BatchApplyPreviewResult]
RunBindingsResolver = Callable[[str], BatchRunBindings]


def plan_batch_run(
    *,
    batch_id: str,
    request: BatchRequest,
    template: WorkflowTemplate,
    captured_at_utc: str,
    dataset_resolver: DatasetResolver,
    apply_preview_resolver: ApplyPreviewResolver,
    run_bindings_resolver: RunBindingsResolver,
) -> BatchPlanningResult:
    request_validation = validate_batch_request(request)
    if not request_validation.valid:
        raise BatchPlanningError(request_validation.errors)

    items: list[BatchSubjectRunPlan] = []
    dataset_results: list[BatchDatasetPlanningResult] = []
    for index, dataset_id in enumerate(request.dataset_selection.dataset_ids):
        item, dataset_result = _plan_subject_item(
            item_id=f"{batch_id}-item-{index + 1:03d}",
            dataset_id=dataset_id,
            request=request,
            template=template,
            dataset_resolver=dataset_resolver,
            apply_preview_resolver=apply_preview_resolver,
            run_bindings_resolver=run_bindings_resolver,
        )
        items.append(item)
        dataset_results.append(dataset_result)

    plan = BatchRunPlan(
        batch_id=batch_id,
        request=request,
        template_snapshot=create_batch_template_snapshot(
            template,
            captured_at_utc=captured_at_utc,
        ),
        items=items,
        created_at_utc=captured_at_utc,
        updated_at_utc=captured_at_utc,
        status=_initial_batch_status(items),
        warnings=request_validation.warnings,
    )
    validation = validate_batch_run_plan(plan)
    if not validation.valid:
        raise BatchPlanningError(validation.errors)
    return BatchPlanningResult(
        plan=plan,
        validation=validation,
        datasets=dataset_results,
    )


def _plan_subject_item(
    *,
    item_id: str,
    dataset_id: str,
    request: BatchRequest,
    template: WorkflowTemplate,
    dataset_resolver: DatasetResolver,
    apply_preview_resolver: ApplyPreviewResolver,
    run_bindings_resolver: RunBindingsResolver,
) -> tuple[BatchSubjectRunPlan, BatchDatasetPlanningResult]:
    dataset = dataset_resolver(dataset_id)
    if dataset is None:
        errors = [f"Dataset not found: {dataset_id}"]
        item = BatchSubjectRunPlan(
            item_id=item_id,
            dataset_id=dataset_id,
            status=BatchItemStatus.FAILED,
            errors=errors,
        )
        return item, BatchDatasetPlanningResult(
            dataset_id=dataset_id,
            item_id=item_id,
            item_status=item.status,
            errors=errors,
        )

    preview = apply_preview_resolver(template, dataset)
    item_status = (
        BatchItemStatus.FAILED
        if preview.status in {"invalid", "requires_review"}
        else BatchItemStatus.PENDING
    )
    warnings = list(preview.warnings)
    errors = list(preview.errors)
    if preview.status == "requires_review":
        errors.append("Template apply requires review before batch execution.")
    if request.dry_run:
        warnings.append("Batch request is dry_run; worker execution is disabled.")
    warnings = _unique_strings(warnings)
    errors = _unique_strings(errors)
    item = BatchSubjectRunPlan(
        item_id=item_id,
        dataset_id=dataset_id,
        status=item_status,
        configs=preview.configs,
        bindings=run_bindings_resolver(dataset_id),
        planned_steps=_planned_steps_from_workflow(preview.configs),
        excluded_fields=preview.excluded_fields,
        review_required_fields=preview.review_required_fields,
        warnings=warnings,
        errors=errors,
    )
    return item, BatchDatasetPlanningResult(
        dataset_id=dataset_id,
        item_id=item_id,
        item_status=item_status,
        preview_status=preview.status,
        errors=errors,
        warnings=warnings,
    )


def _planned_steps_from_workflow(workflow: WorkflowTemplateWorkflow) -> list[RunKind]:
    steps: list[RunKind] = []
    if workflow.preprocessing is not None:
        steps.append(RunKind.PREPROCESSING)
    if workflow.epoch is not None:
        steps.append(RunKind.EPOCH)
    if workflow.erp is not None:
        steps.append(RunKind.ERP)
    return steps


def _initial_batch_status(items: list[BatchSubjectRunPlan]) -> BatchStatus:
    if items and all(item.status == BatchItemStatus.FAILED for item in items):
        return BatchStatus.FAILED
    return BatchStatus.PENDING


def _unique_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
