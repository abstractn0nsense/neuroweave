from fastapi.testclient import TestClient

from apps.api import main as api_main
from eeg_io.registry import JsonWorkflowTemplateRepository


def _client_with_template_repository(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setattr(
        api_main,
        "template_repository",
        JsonWorkflowTemplateRepository(tmp_path / "templates"),
    )
    return TestClient(api_main.app)


def _template_payload(**overrides) -> dict:
    payload = {
        "template_id": "template-001",
        "name": "Oddball ERP",
        "description": "Reusable ERP workflow",
        "created_from": {
            "dataset_id": "dataset-001",
            "preprocessing_run_id": "preprocess-001",
            "epoch_run_id": "epoch-001",
            "erp_run_id": "erp-001",
        },
        "workflow": {
            "preprocessing": {
                "high_pass_hz": 1.0,
                "low_pass_hz": 40.0,
                "reference": "average",
                "ica": {
                    "enabled": True,
                    "method": "fastica",
                    "n_components": 2,
                    "random_state": 97,
                    "max_iter": "auto",
                    "exclude_components": [],
                    "eog_channels": [],
                    "ecg_channels": [],
                },
            },
            "epoch": {
                "condition_field": "trial_type",
                "tmin_seconds": -0.2,
                "tmax_seconds": 0.8,
                "baseline_start_seconds": -0.2,
                "baseline_end_seconds": 0.0,
            },
            "erp": {
                "conditions": ["standard", "target"],
                "method": "mean",
                "plot_mode": "gfp",
            },
        },
        "field_policy": {
            "excluded_fields": [
                {
                    "path": "workflow.preprocessing.manual_bad_channels",
                    "reason": "subject_specific",
                    "source_value_summary": "1 channel omitted by default",
                    "default_action": "omit",
                }
            ],
            "review_required_fields": [],
            "channel_specific_fields": [],
        },
        "notes": ["Created from completed ERP run."],
        "extra": {"source": "api-test"},
    }
    payload.update(overrides)
    return payload


def test_workflow_template_api_saves_lists_gets_and_deletes_template(
    tmp_path,
    monkeypatch,
):
    client = _client_with_template_repository(tmp_path, monkeypatch)

    create_response = client.post("/workflow-templates", json=_template_payload())
    list_response = client.get("/workflow-templates")
    get_response = client.get("/workflow-templates/template-001")

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["schema_version"] == 1
    assert created["template_kind"] == "workflow_template"
    assert created["template_id"] == "template-001"
    assert created["validation"] == {
        "valid": True,
        "stale": False,
        "errors": [],
        "warnings": [],
        "stale_reasons": [],
    }
    assert created["workflow"]["preprocessing"]["manual_bad_channels"] == []
    assert created["workflow"]["preprocessing"]["ica"]["exclude_components"] == []
    assert created["workflow"]["epoch"]["condition_field"] == "trial_type"
    assert "preprocessing_run_id" not in created["workflow"]["epoch"]
    assert "epoch_run_id" not in created["workflow"]["erp"]

    assert list_response.status_code == 200
    assert list_response.json()["templates"] == [created]
    assert get_response.status_code == 200
    assert get_response.json() == created
    assert (
        tmp_path / "templates" / "template-001" / "template.json"
    ).is_file()
    delete_response = client.delete("/workflow-templates/template-001")
    missing_response = client.get("/workflow-templates/template-001")
    assert delete_response.status_code == 204
    assert missing_response.status_code == 404


def test_workflow_template_api_generates_id_and_persists_created_at_on_update(
    tmp_path,
    monkeypatch,
):
    client = _client_with_template_repository(tmp_path, monkeypatch)
    create_payload = _template_payload(template_id=None, name="Initial")

    create_response = client.post("/workflow-templates", json=create_payload)
    created = create_response.json()
    update_response = client.post(
        "/workflow-templates",
        json=_template_payload(
            template_id=created["template_id"],
            name="Updated",
            description="Updated description",
        ),
    )
    updated = update_response.json()

    assert create_response.status_code == 201
    assert created["template_id"].startswith("template-")
    assert update_response.status_code == 201
    assert updated["template_id"] == created["template_id"]
    assert updated["created_at_utc"] == created["created_at_utc"]
    assert updated["updated_at_utc"] >= created["updated_at_utc"]
    assert updated["name"] == "Updated"


def test_workflow_template_api_rejects_subject_specific_fields(
    tmp_path,
    monkeypatch,
):
    client = _client_with_template_repository(tmp_path, monkeypatch)
    payload = _template_payload()
    payload["workflow"]["preprocessing"]["manual_bad_channels"] = ["Fp1"]
    payload["workflow"]["preprocessing"]["ica"]["exclude_components"] = [0]

    response = client.post("/workflow-templates", json=payload)

    assert response.status_code == 422
    assert any("manual_bad_channels" in error for error in response.json()["detail"])
    assert any("ica.exclude_components" in error for error in response.json()["detail"])


def test_workflow_template_api_returns_stale_validation_for_channel_specific_fields(
    tmp_path,
    monkeypatch,
):
    client = _client_with_template_repository(tmp_path, monkeypatch)
    payload = _template_payload()
    payload["workflow"]["preprocessing"]["ica"]["eog_channels"] = ["VEOG"]

    response = client.post("/workflow-templates", json=payload)

    assert response.status_code == 201
    validation = response.json()["validation"]
    assert validation["valid"] is True
    assert validation["stale"] is True
    assert validation["stale_reasons"] == [
        "channel_specific_without_review:workflow.preprocessing.ica.eog_channels"
    ]


def test_workflow_template_api_accepts_review_policy_for_channel_specific_fields(
    tmp_path,
    monkeypatch,
):
    client = _client_with_template_repository(tmp_path, monkeypatch)
    payload = _template_payload()
    payload["workflow"]["preprocessing"]["ica"]["eog_channels"] = ["VEOG"]
    payload["field_policy"]["review_required_fields"] = [
        {
            "path": "workflow.preprocessing.ica.eog_channels",
            "reason": "channel_specific",
            "source_value": ["VEOG"],
            "default_action": "validate_against_target_channels",
        }
    ]

    response = client.post("/workflow-templates", json=payload)

    assert response.status_code == 201
    assert response.json()["validation"]["stale"] is False
    assert response.json()["field_policy"]["review_required_fields"][0][
        "source_value"
    ] == ["VEOG"]


def test_workflow_template_api_returns_404_for_missing_delete(tmp_path, monkeypatch):
    client = _client_with_template_repository(tmp_path, monkeypatch)

    response = client.delete("/workflow-templates/missing-template")

    assert response.status_code == 404
    assert response.json()["detail"] == "Workflow template not found"
