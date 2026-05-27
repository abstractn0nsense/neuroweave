from fastapi.testclient import TestClient

from apps.api import main as api_main
from eeg_core.domain import (
    BadChannelDetectionConfig,
    Dataset,
    DatasetStatus,
    EpochConfig,
    EpochRun,
    EpochRunStatus,
    ErpConfig,
    ErpRun,
    ErpRunStatus,
    EventColumnMapping,
    EventLog,
    IcaConfig,
    NormalizedEvent,
    PreprocessingConfig,
    PreprocessingRun,
    PreprocessingRunStatus,
    Recording,
    RecordingMetadata,
)
from eeg_io.registry import (
    JsonRegistryRepository,
    JsonRunRepository,
    JsonWorkflowTemplateRepository,
)


def _client_with_template_repository(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setattr(
        api_main,
        "template_repository",
        JsonWorkflowTemplateRepository(tmp_path / "templates"),
    )
    return TestClient(api_main.app)


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


def _seed_dataset(
    dataset_id: str = "dataset-001",
    *,
    status: DatasetStatus = DatasetStatus.VALID,
    channel_names: list[str] | None = None,
) -> None:
    channels = channel_names or ["Fp1", "Fp2", "VEOG", "Cz"]
    api_main.registry_repository.save_dataset(
        Dataset(
            dataset_id=dataset_id,
            project_id="project-001",
            experiment_id="experiment-001",
            participant_id="participant-001",
            session_id="session-001",
            status=status,
            recording_id="recording-001",
            event_log_id="event-log-001",
        )
    )
    api_main.registry_repository.save_recording(
        Recording(
            recording_id="recording-001",
            dataset_id=dataset_id,
            file_id="file-001",
            metadata=RecordingMetadata(
                dataset_id=dataset_id,
                file_format="fif",
                channel_count=len(channels),
                sampling_rate_hz=256.0,
                duration_seconds=4.0,
                channel_names=channels,
            ),
        )
    )
    api_main.registry_repository.save_event_log(
        EventLog(
            event_log_id="event-log-001",
            dataset_id=dataset_id,
            file_id="file-002",
            mapping=EventColumnMapping(onset_seconds="onset", trial_type="trial_type"),
            row_count=2,
            events=[
                NormalizedEvent(
                    onset_seconds=1.0,
                    source_row=1,
                    trial_type="standard",
                ),
                NormalizedEvent(
                    onset_seconds=2.0,
                    source_row=2,
                    trial_type="target",
                ),
            ],
        )
    )


def _seed_completed_run_chain(tmp_path, dataset_id: str = "dataset-001") -> None:
    output_path = (
        tmp_path
        / "processed"
        / dataset_id
        / "preprocess-001"
        / "raw_preprocessed_raw.fif"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"placeholder")
    api_main.run_repository.save_preprocessing_run(
        PreprocessingRun(
            run_id="preprocess-001",
            dataset_id=dataset_id,
            config=PreprocessingConfig(
                high_pass_hz=1.0,
                low_pass_hz=40.0,
                reference="average",
                manual_bad_channels=["Fp1"],
                bad_channel_detection=BadChannelDetectionConfig(
                    enabled=True,
                    method="deviation",
                    zscore_threshold=4.5,
                ),
                ica=IcaConfig(
                    enabled=True,
                    method="picard",
                    n_components=2,
                    random_state=13,
                    max_iter=250,
                    exclude_components=[0],
                    eog_channels=["VEOG"],
                ),
            ),
            status=PreprocessingRunStatus.COMPLETED,
            finished_at_utc="2026-05-28T00:01:00Z",
            output_path=str(output_path),
            output_metadata={
                "output_sampling_rate_hz": 256.0,
                "output_duration_seconds": 4.0,
            },
        )
    )
    epoch_output = tmp_path / "epochs" / dataset_id / "epoch-001" / "epochs-epo.fif"
    epoch_output.parent.mkdir(parents=True, exist_ok=True)
    epoch_output.write_bytes(b"placeholder")
    api_main.run_repository.save_epoch_run(
        EpochRun(
            run_id="epoch-001",
            dataset_id=dataset_id,
            config=EpochConfig(
                preprocessing_run_id="preprocess-001",
                condition_field="trial_type",
                tmin_seconds=-0.2,
                tmax_seconds=0.8,
                baseline_start_seconds=-0.2,
                baseline_end_seconds=0.0,
            ),
            status=EpochRunStatus.COMPLETED,
            finished_at_utc="2026-05-28T00:02:00Z",
            output_path=str(epoch_output),
        )
    )
    api_main.run_repository.save_erp_run(
        ErpRun(
            run_id="erp-001",
            dataset_id=dataset_id,
            config=ErpConfig(
                epoch_run_id="epoch-001",
                conditions=["standard", "target"],
                picks=["Fp1", "Fp2"],
                plot_mode="channel",
                plot_channel="Fp1",
            ),
            status=ErpRunStatus.COMPLETED,
            finished_at_utc="2026-05-28T00:03:00Z",
        )
    )


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


def test_workflow_template_from_completed_erp_run_builds_reusable_template(
    tmp_path,
    monkeypatch,
):
    client = _client_with_repositories(tmp_path, monkeypatch)
    _seed_dataset()
    _seed_completed_run_chain(tmp_path)

    response = client.post(
        "/workflow-templates/from-run",
        json={
            "template_id": "template-from-erp",
            "name": "From completed ERP",
            "erp_run_id": "erp-001",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["created_from"] == {
        "dataset_id": "dataset-001",
        "preprocessing_run_id": "preprocess-001",
        "epoch_run_id": "epoch-001",
        "erp_run_id": "erp-001",
    }
    preprocessing = payload["workflow"]["preprocessing"]
    assert preprocessing["manual_bad_channels"] == []
    assert preprocessing["bad_channel_detection"]["enabled"] is True
    assert preprocessing["bad_channel_detection"]["method"] == "deviation"
    assert preprocessing["bad_channel_detection"]["zscore_threshold"] == 4.5
    assert preprocessing["ica"]["enabled"] is True
    assert preprocessing["ica"]["method"] == "picard"
    assert preprocessing["ica"]["n_components"] == 2
    assert preprocessing["ica"]["random_state"] == 13
    assert preprocessing["ica"]["max_iter"] == 250
    assert preprocessing["ica"]["exclude_components"] == []
    assert preprocessing["ica"]["eog_channels"] == ["VEOG"]
    assert payload["workflow"]["epoch"]["condition_field"] == "trial_type"
    assert "preprocessing_run_id" not in payload["workflow"]["epoch"]
    assert payload["workflow"]["erp"]["plot_channel"] == "Fp1"
    assert "epoch_run_id" not in payload["workflow"]["erp"]
    excluded_paths = {
        entry["path"] for entry in payload["field_policy"]["excluded_fields"]
    }
    assert "workflow.preprocessing.manual_bad_channels" in excluded_paths
    assert "workflow.preprocessing.ica.exclude_components" in excluded_paths
    assert "workflow.epoch.preprocessing_run_id" in excluded_paths
    assert "workflow.erp.epoch_run_id" in excluded_paths
    review_paths = {
        entry["path"] for entry in payload["field_policy"]["review_required_fields"]
    }
    assert "workflow.preprocessing.ica.eog_channels" in review_paths
    assert "workflow.erp.plot_channel" in review_paths
    assert payload["validation"]["valid"] is True


def test_workflow_template_from_run_rejects_incomplete_source_run(
    tmp_path,
    monkeypatch,
):
    client = _client_with_repositories(tmp_path, monkeypatch)
    api_main.run_repository.save_preprocessing_run(
        PreprocessingRun(
            run_id="preprocess-pending",
            dataset_id="dataset-001",
            config=PreprocessingConfig(reference="average"),
            status=PreprocessingRunStatus.PENDING,
        )
    )

    response = client.post(
        "/workflow-templates/from-run",
        json={
            "template_id": "template-pending",
            "name": "Pending",
            "preprocessing_run_id": "preprocess-pending",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Preprocessing run must be completed before template creation."
    )


def test_workflow_template_apply_preview_returns_ready_config_with_overrides(
    tmp_path,
    monkeypatch,
):
    client = _client_with_repositories(tmp_path, monkeypatch)
    _seed_dataset()
    create_response = client.post(
        "/workflow-templates",
        json=_template_payload(template_id="template-apply"),
    )
    assert create_response.status_code == 201

    response = client.post(
        "/workflow-templates/template-apply/apply-preview",
        json={
            "target_dataset_id": "dataset-001",
            "subject_overrides": {
                "manual_bad_channels": ["Fp1"],
                "ica_exclude_components": [1],
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    preprocessing = payload["configs"]["preprocessing"]
    assert preprocessing["manual_bad_channels"] == ["Fp1"]
    assert preprocessing["ica"]["exclude_components"] == [1]
    assert payload["errors"] == []


def test_workflow_template_apply_preview_does_not_auto_apply_imported_ica_exclusions(
    tmp_path,
    monkeypatch,
):
    client = _client_with_repositories(tmp_path, monkeypatch)
    _seed_dataset()
    template_path = (
        api_main.template_repository.template_path("template-imported-ica")
    )
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(
        """
{
  "template_id": "template-imported-ica",
  "name": "Imported ICA review",
  "created_at_utc": "2026-05-28T00:00:00Z",
  "workflow": {
    "preprocessing": {
      "high_pass_hz": 1.0,
      "low_pass_hz": 40.0,
      "ica": {
        "enabled": true,
        "method": "fastica",
        "exclude_components": [0, 1]
      }
    }
  }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    response = client.post(
        "/workflow-templates/template-imported-ica/apply-preview",
        json={"target_dataset_id": "dataset-001"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "requires_review"
    assert payload["configs"]["preprocessing"]["ica"]["exclude_components"] == []
    assert payload["review_required_fields"] == [
        {
            "path": "workflow.preprocessing.ica.exclude_components",
            "reason": "subject_specific_review_decision",
            "source_value": [0, 1],
            "source_value_summary": "2 component(s) imported as review-only",
            "default_action": "requires_review",
        }
    ]
    assert payload["errors"] == []


def test_workflow_template_apply_preview_rejects_invalid_subject_override(
    tmp_path,
    monkeypatch,
):
    client = _client_with_repositories(tmp_path, monkeypatch)
    _seed_dataset()
    create_response = client.post(
        "/workflow-templates",
        json=_template_payload(template_id="template-invalid-override"),
    )
    assert create_response.status_code == 201

    response = client.post(
        "/workflow-templates/template-invalid-override/apply-preview",
        json={
            "target_dataset_id": "dataset-001",
            "subject_overrides": {"manual_bad_channels": ["MissingChannel"]},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "invalid"
    assert payload["errors"] == [
        "manual_bad_channels contains unknown channels: MissingChannel"
    ]


def test_workflow_template_apply_preview_requires_review_for_channel_specific_fields(
    tmp_path,
    monkeypatch,
):
    client = _client_with_repositories(tmp_path, monkeypatch)
    _seed_dataset()
    create_response = client.post(
        "/workflow-templates",
        json=_template_payload(
            template_id="template-review",
            workflow={
                **_template_payload()["workflow"],
                "preprocessing": {
                    **_template_payload()["workflow"]["preprocessing"],
                    "ica": {
                        **_template_payload()["workflow"]["preprocessing"]["ica"],
                        "eog_channels": ["VEOG"],
                    },
                },
            },
            field_policy={
                "excluded_fields": [],
                "review_required_fields": [
                    {
                        "path": "workflow.preprocessing.ica.eog_channels",
                        "reason": "channel_specific",
                        "source_value": ["VEOG"],
                        "default_action": "validate_against_target_channels",
                    }
                ],
                "channel_specific_fields": [
                    "workflow.preprocessing.ica.eog_channels"
                ],
            },
        ),
    )
    assert create_response.status_code == 201

    response = client.post(
        "/workflow-templates/template-review/apply-preview",
        json={"target_dataset_id": "dataset-001"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "requires_review"
    assert payload["review_required_fields"][0]["path"] == (
        "workflow.preprocessing.ica.eog_channels"
    )
    assert payload["errors"] == []
