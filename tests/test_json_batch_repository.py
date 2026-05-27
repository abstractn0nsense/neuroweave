from dataclasses import replace

import pytest

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
    WorkflowTemplateWorkflow,
    create_batch_template_snapshot,
)
from eeg_io.registry import JsonBatchRepository, JsonRegistryError


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


def _batch_plan(**overrides) -> BatchRunPlan:
    request = BatchRequest(
        template_id="template-001",
        dataset_selection=BatchDatasetSelection(
            dataset_ids=["dataset-001", "dataset-002"]
        ),
    )
    template = _template()
    values = {
        "batch_id": "batch-001",
        "request": request,
        "template_snapshot": create_batch_template_snapshot(
            template,
            captured_at_utc="2026-05-28T00:15:00Z",
        ),
        "items": [
            BatchSubjectRunPlan(
                item_id="batch-001-item-001",
                dataset_id="dataset-001",
                configs=template.workflow,
                planned_steps=[RunKind.PREPROCESSING],
            ),
            BatchSubjectRunPlan(
                item_id="batch-001-item-002",
                dataset_id="dataset-002",
                status=BatchItemStatus.FAILED,
                attempt=2,
                configs=template.workflow,
                bindings=BatchRunBindings(preprocessing_run_id="preprocess-prev"),
                planned_steps=[RunKind.PREPROCESSING],
                run_ids={"preprocessing": "preprocess-retry"},
                previous_run_ids={"preprocessing": "preprocess-failed"},
                previous_error="Previous preprocessing failed.",
                errors=["Retry is pending manual restart."],
            ),
        ],
        "status": BatchStatus.PENDING,
        "created_at_utc": "2026-05-28T00:16:00Z",
        "updated_at_utc": "2026-05-28T00:17:00Z",
    }
    values.update(overrides)
    return BatchRunPlan(**values)


def test_json_batch_repository_persists_lists_and_gets_batches(tmp_path):
    repository = JsonBatchRepository(tmp_path / "batches")
    plan = _batch_plan()

    saved = repository.save_batch(plan)
    listed = repository.list_batches()
    loaded = repository.get_batch("batch-001")

    assert saved == plan
    assert listed == [plan]
    assert loaded == plan
    assert (tmp_path / "batches" / "batch-001" / "batch.json").is_file()
    assert loaded.items[1].attempt == 2
    assert loaded.items[1].run_ids == {"preprocessing": "preprocess-retry"}
    assert loaded.items[1].previous_run_ids == {
        "preprocessing": "preprocess-failed"
    }
    assert loaded.items[1].previous_error == "Previous preprocessing failed."


def test_json_batch_repository_rejects_mutated_template_snapshot_digest(tmp_path):
    repository = JsonBatchRepository(tmp_path / "batches")
    plan = _batch_plan()
    mutated_snapshot = replace(
        plan.template_snapshot,
        template_digest_sha256="not-the-real-digest",
    )

    with pytest.raises(JsonRegistryError, match="snapshot digest"):
        repository.save_batch(replace(plan, template_snapshot=mutated_snapshot))


def test_json_batch_repository_loads_legacy_batch_defaults(tmp_path):
    repository = JsonBatchRepository(tmp_path / "batches")
    path = repository.batch_path("batch-legacy")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """
{
  "batch_id": "batch-legacy",
  "request": {
    "template_id": "template-001",
    "dataset_selection": {"dataset_ids": ["dataset-001"]}
  },
  "template_snapshot": {
    "template": {
      "template_id": "template-001",
      "name": "Legacy template",
      "created_at_utc": "2026-05-28T00:00:00Z",
      "updated_at_utc": "2026-05-28T00:00:00Z",
      "workflow": {"preprocessing": {"reference": "average"}}
    },
    "captured_at_utc": "2026-05-28T00:01:00Z"
  },
  "items": [
    {
      "item_id": "batch-legacy-item-001",
      "dataset_id": "dataset-001",
      "configs": {"preprocessing": {"reference": "average"}},
      "planned_steps": ["preprocessing"]
    }
  ],
  "created_at_utc": "2026-05-28T00:02:00Z",
  "updated_at_utc": "2026-05-28T00:02:00Z"
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    loaded = repository.get_batch("batch-legacy")

    assert loaded is not None
    assert loaded.template_snapshot.template_name == "Legacy template"
    assert loaded.items[0].status == BatchItemStatus.PENDING
    assert loaded.items[0].attempt == 1
    assert loaded.items[0].previous_run_ids == {}
