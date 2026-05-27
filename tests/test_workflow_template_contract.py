from dataclasses import asdict
import json

import pytest

from eeg_core.domain import (
    IcaConfig,
    PreprocessingConfig,
    WorkflowTemplate,
    WorkflowTemplateEpochConfig,
    WorkflowTemplateErpConfig,
    WorkflowTemplateFieldPolicy,
    WorkflowTemplateFieldPolicyEntry,
    WorkflowTemplateWorkflow,
    validate_workflow_template,
)
from eeg_io.registry import JsonRegistryError, JsonWorkflowTemplateRepository


def _template(**overrides) -> WorkflowTemplate:
    values = {
        "template_id": "template-001",
        "name": "Oddball ERP",
        "created_at_utc": "2026-05-28T00:00:00Z",
        "updated_at_utc": "2026-05-28T00:00:00Z",
        "workflow": WorkflowTemplateWorkflow(
            preprocessing=PreprocessingConfig(
                high_pass_hz=1.0,
                low_pass_hz=40.0,
                reference="average",
            ),
            epoch=WorkflowTemplateEpochConfig(
                condition_field="trial_type",
                tmin_seconds=-0.2,
                tmax_seconds=0.8,
                baseline_start_seconds=-0.2,
                baseline_end_seconds=0.0,
            ),
            erp=WorkflowTemplateErpConfig(method="mean", plot_mode="gfp"),
        ),
    }
    values.update(overrides)
    return WorkflowTemplate(**values)


def test_workflow_template_is_plain_serializable_dataclass():
    template = _template()

    payload = asdict(template)
    validation = validate_workflow_template(template)

    assert validation.valid
    assert not validation.stale
    assert payload["schema_version"] == 1
    assert payload["template_kind"] == "workflow_template"
    assert payload["workflow"]["epoch"]["condition_field"] == "trial_type"
    assert "preprocessing_run_id" not in payload["workflow"]["epoch"]
    assert "epoch_run_id" not in payload["workflow"]["erp"]


def test_workflow_template_validation_rejects_subject_specific_fields():
    template = _template(
        workflow=WorkflowTemplateWorkflow(
            preprocessing=PreprocessingConfig(
                manual_bad_channels=["Fp1"],
                ica=IcaConfig(enabled=True, exclude_components=[0]),
            )
        )
    )

    validation = validate_workflow_template(template)

    assert not validation.valid
    assert validation.stale
    assert "subject_specific_manual_bad_channels" in validation.stale_reasons
    assert "subject_specific_ica_exclusions" in validation.stale_reasons
    assert any("manual_bad_channels" in error for error in validation.errors)
    assert any("ica.exclude_components" in error for error in validation.errors)


def test_workflow_template_validation_marks_channel_specific_fields_stale():
    template = _template(
        workflow=WorkflowTemplateWorkflow(
            preprocessing=PreprocessingConfig(
                ica=IcaConfig(enabled=True, eog_channels=["VEOG"]),
            )
        )
    )

    validation = validate_workflow_template(template)

    assert validation.valid
    assert validation.stale
    assert validation.stale_reasons == [
        "channel_specific_without_review:workflow.preprocessing.ica.eog_channels"
    ]


def test_workflow_template_validation_accepts_channel_review_policy():
    template = _template(
        workflow=WorkflowTemplateWorkflow(
            preprocessing=PreprocessingConfig(
                ica=IcaConfig(enabled=True, eog_channels=["VEOG"]),
            )
        ),
        field_policy=WorkflowTemplateFieldPolicy(
            review_required_fields=[
                WorkflowTemplateFieldPolicyEntry(
                    path="workflow.preprocessing.ica.eog_channels",
                    reason="channel_specific",
                    source_value=["VEOG"],
                    default_action="validate_against_target_channels",
                )
            ]
        ),
    )

    validation = validate_workflow_template(template)

    assert validation.valid
    assert not validation.stale
    assert validation.warnings == []


def test_workflow_template_repository_persists_lists_and_deletes_templates(tmp_path):
    repository = JsonWorkflowTemplateRepository(tmp_path / "templates")
    template = _template()

    repository.save_template(template)

    assert repository.get_template("template-001") == template
    assert repository.list_templates() == [template]
    assert repository.template_path("template-001").is_file()
    stored = json.loads(
        repository.template_path("template-001").read_text(encoding="utf-8")
    )
    assert stored["workflow"]["preprocessing"]["manual_bad_channels"] == []
    assert stored["workflow"]["preprocessing"]["ica"]["exclude_components"] == []
    assert repository.delete_template("template-001") is True
    assert repository.get_template("template-001") is None
    assert repository.delete_template("template-001") is False


def test_workflow_template_repository_rejects_invalid_template(tmp_path):
    repository = JsonWorkflowTemplateRepository(tmp_path / "templates")
    template = _template(
        workflow=WorkflowTemplateWorkflow(
            preprocessing=PreprocessingConfig(manual_bad_channels=["Fp1"])
        )
    )

    with pytest.raises(JsonRegistryError, match="manual_bad_channels"):
        repository.save_template(template)


def test_workflow_template_repository_loads_legacy_template_defaults(tmp_path):
    repository = JsonWorkflowTemplateRepository(tmp_path / "templates")
    path = repository.template_path("legacy-template")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "id": "legacy-template",
                "name": "Legacy oddball",
                "created_at_utc": "2026-05-28T00:00:00Z",
                "preprocessing": {
                    "high_pass_hz": 1.0,
                    "ica": {"enabled": True, "method": "fastica"},
                },
                "epoch": {
                    "preprocessing_run_id": "preprocess-source",
                    "condition_field": "trial_type",
                    "tmin_seconds": -0.1,
                    "tmax_seconds": 0.6,
                },
                "erp": {
                    "epoch_run_id": "epoch-source",
                    "plot_mode": "gfp",
                },
                "future_top_level": {"kept": True},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    template = repository.get_template("legacy-template")

    assert template is not None
    assert template.schema_version == 1
    assert template.template_kind == "workflow_template"
    assert template.template_id == "legacy-template"
    assert template.updated_at_utc == "2026-05-28T00:00:00Z"
    assert template.workflow.preprocessing == PreprocessingConfig(
        high_pass_hz=1.0,
        ica=IcaConfig(enabled=True, method="fastica"),
    )
    assert template.workflow.epoch == WorkflowTemplateEpochConfig(
        condition_field="trial_type",
        tmin_seconds=-0.1,
        tmax_seconds=0.6,
    )
    assert template.workflow.erp == WorkflowTemplateErpConfig(plot_mode="gfp")
    assert template.field_policy == WorkflowTemplateFieldPolicy()
    assert template.extra["future_top_level"] == {"kept": True}
    assert validate_workflow_template(template).valid

    repository.save_template(template)
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["extra"]["future_top_level"] == {"kept": True}


def test_workflow_template_repository_imports_ica_exclusions_as_review_only(
    tmp_path,
):
    repository = JsonWorkflowTemplateRepository(tmp_path / "templates")
    path = repository.template_path("legacy-ica-template")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "template_id": "legacy-ica-template",
                "name": "Legacy ICA review",
                "created_at_utc": "2026-05-28T00:00:00Z",
                "workflow": {
                    "preprocessing": {
                        "bad_channel_detection": {
                            "enabled": True,
                            "method": "deviation",
                            "zscore_threshold": 4.5,
                        },
                        "ica": {
                            "enabled": True,
                            "method": "picard",
                            "n_components": 0.95,
                            "random_state": 13,
                            "max_iter": 250,
                            "exclude_components": [0, 2],
                        },
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    template = repository.get_template("legacy-ica-template")

    assert template is not None
    assert template.workflow.preprocessing is not None
    preprocessing = template.workflow.preprocessing
    assert preprocessing.ica.enabled is True
    assert preprocessing.ica.method == "picard"
    assert preprocessing.ica.n_components == 0.95
    assert preprocessing.ica.random_state == 13
    assert preprocessing.ica.max_iter == 250
    assert preprocessing.ica.exclude_components == []
    assert preprocessing.bad_channel_detection.enabled is True
    assert preprocessing.bad_channel_detection.method == "deviation"
    assert preprocessing.bad_channel_detection.zscore_threshold == 4.5
    assert validate_workflow_template(template).valid
    review_entry = template.field_policy.review_required_fields[0]
    assert review_entry.path == "workflow.preprocessing.ica.exclude_components"
    assert review_entry.source_value == [0, 2]
    assert review_entry.default_action == "requires_review"

    repository.save_template(template)
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["workflow"]["preprocessing"]["ica"]["exclude_components"] == []
    assert stored["field_policy"]["review_required_fields"][0]["source_value"] == [
        0,
        2,
    ]


def test_workflow_template_validation_flags_unsupported_schema_as_stale():
    template = _template(schema_version=99)

    validation = validate_workflow_template(template)

    assert not validation.valid
    assert validation.stale
    assert validation.stale_reasons == ["unsupported_schema_version"]
