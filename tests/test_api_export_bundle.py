import json
import shutil
import zipfile
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient

from apps.api import main as api_main
from eeg_core.domain import (
    BatchDatasetSelection,
    BatchItemStatus,
    BatchRequest,
    BatchRunPlan,
    BatchStatus,
    BatchSubjectRunPlan,
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
    RunKind,
    SourceFileMetadata,
    WorkflowTemplate,
    WorkflowTemplateWorkflow,
    create_batch_template_snapshot,
)
from eeg_core.domain.recording import RecordingMetadata
from eeg_io.registry import JsonBatchRepository, JsonRegistryRepository, JsonRunRepository


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "qc"


def test_get_dataset_export_bundle_downloads_latest_completed_run(
    tmp_path,
    monkeypatch,
):
    client, run_repository = _client(tmp_path, monkeypatch)
    manifest_path = _copy_erp_fixture_with_figure(tmp_path)
    run_repository.save_erp_run(
        ErpRun(
            run_id="erp-001",
            dataset_id="dataset-001",
            config=ErpConfig(epoch_run_id="epoch-001", conditions=["standard"]),
            status=ErpRunStatus.COMPLETED,
            finished_at_utc="2026-05-26T00:00:00+00:00",
            output_metadata={"artifact_manifest_path": str(manifest_path)},
        )
    )

    response = client.get("/datasets/dataset-001/export-bundle")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "neuroweave_dataset-001_erp-001_export_bundle.zip" in response.headers[
        "content-disposition"
    ]
    with zipfile.ZipFile(BytesIO(response.content)) as bundle:
        assert sorted(bundle.namelist()) == [
            "analysis_report.json",
            "artifact_manifest.json",
            "diagnostics/erp_metadata.json",
            "diagnostics/phase_d_metadata.json",
            "export_bundle_manifest.json",
            "figures/erp_standard_plot.png",
        ]
        analysis_report = json.loads(bundle.read("analysis_report.json"))
        phase_d_metadata = json.loads(bundle.read("diagnostics/phase_d_metadata.json"))
        bundle_manifest = json.loads(bundle.read("export_bundle_manifest.json"))

    assert analysis_report["dataset_id"] == "dataset-001"
    assert analysis_report["run_id"] == "erp-001"
    assert analysis_report["run_kind"] == "erp"
    assert analysis_report["config_snapshot"]["epoch_run_id"] == "epoch-001"
    assert phase_d_metadata["dataset"]["dataset_id"] == "dataset-001"
    assert bundle_manifest["analysis_report_included"] is True
    assert bundle_manifest["diagnostics"] == {"warnings": []}


def test_get_erp_run_export_bundle_accepts_direct_run_id(tmp_path, monkeypatch):
    client, run_repository = _client(tmp_path, monkeypatch)
    manifest_path = _copy_erp_fixture_with_figure(tmp_path)
    run_repository.save_erp_run(
        ErpRun(
            run_id="erp-001",
            dataset_id="dataset-001",
            config=ErpConfig(epoch_run_id="epoch-001"),
            status=ErpRunStatus.COMPLETED,
            finished_at_utc="2026-05-26T00:00:00+00:00",
            output_metadata={"artifact_manifest_path": str(manifest_path)},
        )
    )

    response = client.get("/erp-runs/erp-001/export-bundle")

    assert response.status_code == 200
    with zipfile.ZipFile(BytesIO(response.content)) as bundle:
        analysis_report = json.loads(bundle.read("analysis_report.json"))

    assert analysis_report["run_id"] == "erp-001"


def test_get_export_bundle_includes_batch_summary_and_report_context(
    tmp_path,
    monkeypatch,
):
    client, run_repository = _client(tmp_path, monkeypatch)
    manifest_path = _copy_fixture(tmp_path, "preprocessing")
    run_repository.save_preprocessing_run(
        PreprocessingRun(
            run_id="preprocess-001",
            dataset_id="dataset-001",
            config=PreprocessingConfig(reference="average"),
            status=PreprocessingRunStatus.COMPLETED,
            finished_at_utc="2026-05-26T00:00:00+00:00",
            output_metadata={
                "artifact_manifest_path": str(manifest_path),
                "batch_id": "batch-001",
                "batch_item_id": "batch-001-item-001",
            },
        )
    )
    _save_completed_batch_for_run("preprocess-001")

    response = client.get(
        "/datasets/dataset-001/export-bundle",
        params={"run_id": "preprocess-001"},
    )

    assert response.status_code == 200
    with zipfile.ZipFile(BytesIO(response.content)) as bundle:
        assert "batch/batch_summary.json" in bundle.namelist()
        analysis_report = json.loads(bundle.read("analysis_report.json"))
        batch_summary = json.loads(bundle.read("batch/batch_summary.json"))
        bundle_manifest = json.loads(bundle.read("export_bundle_manifest.json"))

    assert analysis_report["batch"]["batch_id"] == "batch-001"
    assert analysis_report["batch"]["subject_manifest"][
        "artifact_manifest_path"
    ] == str(manifest_path)
    assert batch_summary["items"][0]["artifact_manifests"]["preprocessing"][
        "artifact_manifest_url"
    ] == "/artifacts/preprocess-001/artifact_manifest.json"
    assert any(
        entry["logical_name"] == "batch_summary"
        and entry["archive_path"] == "batch/batch_summary.json"
        for entry in bundle_manifest["entries"]
    )


def test_create_erp_analysis_report_writes_report_and_manifest_entry(
    tmp_path,
    monkeypatch,
):
    client, run_repository = _client(tmp_path, monkeypatch)
    registry_repository = api_main.registry_repository
    manifest_path = _copy_erp_fixture_with_figure(tmp_path)
    comparison_path = manifest_path.parent / "comparison_summary.json"
    comparison_path.write_text(
        json.dumps(
            {
                "metric": "mean_amplitude_uv",
                "conditions": {
                    "a": {"label": "target", "mean_amplitude_uv": 1.7},
                    "b": {"label": "standard", "mean_amplitude_uv": 0.5},
                },
                "difference": {"mean_amplitude_uv": 1.2},
                "statistics": {
                    "schema_version": 1,
                    "status": "implemented",
                    "implemented": True,
                    "phase": "Phase E",
                    "method": "paired_t_test",
                    "design": "within_subject",
                    "input_metric": "mean_amplitude_uv",
                    "observation_level": "subject",
                    "condition_pair": {"a": "target", "b": "standard"},
                    "sample": {
                        "unit": "subject",
                        "paired": True,
                        "n": 4,
                        "missing_pairs": 0,
                    },
                    "result": {
                        "statistic_name": "t",
                        "statistic": 2.8,
                        "degrees_of_freedom": 3,
                        "p_value": 0.067,
                        "p_value_kind": "uncorrected",
                        "effect_size": {
                            "name": "cohens_dz",
                            "value": 1.4,
                            "interpretation": None,
                        },
                        "confidence_interval": {
                            "implemented": False,
                            "level": None,
                            "lower": None,
                            "upper": None,
                            "unit": "microvolt",
                        },
                        "multiple_comparison": {
                            "applied": False,
                            "method": None,
                            "family": None,
                            "adjusted_p_value": None,
                        },
                    },
                    "assumptions": [
                        {
                            "name": "paired_observations",
                            "status": "met",
                            "detail": "Each row has both condition metrics.",
                        }
                    ],
                    "diagnostics": {"warnings": []},
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    registry_repository.save_recording(
        Recording(
            recording_id="recording-001",
            dataset_id="dataset-001",
            file_id="file-001",
            metadata=RecordingMetadata(
                dataset_id="dataset-001",
                file_format="fif",
                channel_count=2,
                sampling_rate_hz=100.0,
                duration_seconds=6.0,
                channel_names=["Cz", "Pz"],
                source_files=[
                    SourceFileMetadata(
                        role="eeg",
                        original_filename="sample.fif",
                        stored_path="data/raw/uploads/sample.fif",
                        size_bytes=512,
                        checksum_sha256="abc123",
                    )
                ],
                sidecar_discovery={
                    "schema_version": 1,
                    "candidates": [{"sidecar_type": "eeg_json", "status": "valid"}],
                },
            ),
        )
    )
    registry_repository.save_event_log(
        EventLog(
            event_log_id="events-001",
            dataset_id="dataset-001",
            file_id="events-file-001",
            mapping=EventColumnMapping(
                onset_seconds="onset",
                duration_seconds="duration",
                trial_type="trial_type",
            ),
            row_count=3,
            provenance={"sources": [{"role": "event_file"}]},
            events=[
                NormalizedEvent(1.0, 1, trial_type="standard"),
                NormalizedEvent(2.0, 2, trial_type="target"),
                NormalizedEvent(3.0, 3, trial_type="target"),
            ],
        )
    )
    run_repository.save_preprocessing_run(
        PreprocessingRun(
            run_id="pre-001",
            dataset_id="dataset-001",
            config=PreprocessingConfig(high_pass_hz=1.0, low_pass_hz=40.0),
            status=PreprocessingRunStatus.COMPLETED,
            warnings=["pre warning"],
        )
    )
    run_repository.save_epoch_run(
        EpochRun(
            run_id="epoch-001",
            dataset_id="dataset-001",
            config=EpochConfig(
                preprocessing_run_id="pre-001",
                condition_field="trial_type",
                tmin_seconds=-0.2,
                tmax_seconds=0.8,
            ),
            status=EpochRunStatus.COMPLETED,
            output_metadata={"input_preprocessing_run_id": "pre-001"},
        )
    )
    run_repository.save_erp_run(
        ErpRun(
            run_id="erp-001",
            dataset_id="dataset-001",
            config=ErpConfig(epoch_run_id="epoch-001", conditions=["standard", "target"]),
            status=ErpRunStatus.COMPLETED,
            output_path=str(manifest_path.parent / "erp_metadata.json"),
            output_metadata={
                "artifact_manifest_path": str(manifest_path),
                "artifact_root": str(manifest_path.parent),
                "input_preprocessing_run_id": "pre-001",
                "preview_plot_url": "/artifacts/erp-001/erp_standard.png",
                "comparison_summary_path": str(comparison_path),
            },
            warnings=["erp warning"],
        )
    )

    response = client.post("/erp-runs/erp-001/analysis-report")

    assert response.status_code == 200
    payload = response.json()
    report = payload["report"]
    assert report["dataset_metadata"]["participant_label"] == "sub-001"
    assert report["dataset_metadata"]["recording"]["sampling_rate_hz"] == 100.0
    assert report["dataset_metadata"]["recording"]["source_files"][0][
        "original_filename"
    ] == "sample.fif"
    assert report["dataset_metadata"]["recording"]["sidecar_discovery"][
        "candidates"
    ][0]["sidecar_type"] == "eeg_json"
    assert report["event_summary"]["condition_counts"] == {
        "standard": 1,
        "target": 2,
    }
    assert report["event_summary"]["provenance"]["sources"][0]["role"] == "event_file"
    assert report["phase_d_metadata"]["recording"]["source_files"][0][
        "original_filename"
    ] == "sample.fif"
    assert report["preprocessing_config"]["high_pass_hz"] == 1.0
    assert report["epoch_config"]["condition_field"] == "trial_type"
    assert report["erp_config"]["conditions"] == ["standard", "target"]
    assert report["warnings"]["preprocessing"]["warnings"] == ["pre warning"]
    assert report["warnings"]["erp"]["warnings"] == ["erp warning"]
    assert report["preview_plot"]["url"] == "/artifacts/erp-001/erp_standard.png"
    assert report["comparison_summary"]["metric"] == "mean_amplitude_uv"
    assert report["comparison_statistics"]["available"] is True
    assert report["comparison_statistics"]["status"] == "implemented"
    assert report["comparison_statistics"]["method"] == "paired_t_test"
    assert report["comparison_statistics"]["result"]["p_value"] == 0.067
    assert payload["report_url"] == "/artifacts/erp-001/analysis_report.json"
    assert payload["erp_run"]["output_metadata"]["analysis_report_available"] is True

    report_path = manifest_path.parent / "analysis_report.json"
    assert report_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert any(
        artifact["logical_name"] == "analysis_report"
        for artifact in manifest["artifacts"]
    )


def test_export_bundle_manifest_includes_comparison_statistics(
    tmp_path,
    monkeypatch,
):
    client, run_repository = _client(tmp_path, monkeypatch)
    manifest_path = _copy_erp_fixture_with_figure(tmp_path)
    comparison_path = manifest_path.parent / "comparison_summary.json"
    comparison_path.write_text(
        json.dumps(
            {
                "metric": "mean_amplitude_uv",
                "target": {"type": "gfp", "channel": None},
                "window": {"start_seconds": -0.05, "end_seconds": 0.2},
                "conditions": {
                    "a": {"label": "target", "mean_amplitude_uv": 1.7},
                    "b": {"label": "standard", "mean_amplitude_uv": 0.5},
                },
                "difference": {"mean_amplitude_uv": 1.2},
                "statistics": {
                    "schema_version": 1,
                    "status": "unavailable",
                    "implemented": False,
                    "phase": "Phase E",
                    "method": "paired_t_test",
                    "design": "within_subject",
                    "input_metric": "mean_amplitude_uv",
                    "observation_level": "subject",
                    "condition_pair": {"a": "target", "b": "standard"},
                    "sample": {
                        "unit": "subject",
                        "paired": True,
                        "n": 1,
                        "missing_pairs": 0,
                    },
                    "result": None,
                    "assumptions": [],
                    "diagnostics": {
                        "warnings": [
                            {
                                "code": "insufficient_observations",
                                "severity": "warning",
                                "source": "artifact",
                                "impact": (
                                    "Paired t-test requires at least two paired "
                                    "observations."
                                ),
                                "suggested_action": (
                                    "Run the comparison from a multi-subject "
                                    "observation table."
                                ),
                            }
                        ]
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    run_repository.save_erp_run(
        ErpRun(
            run_id="erp-001",
            dataset_id="dataset-001",
            config=ErpConfig(epoch_run_id="epoch-001"),
            status=ErpRunStatus.COMPLETED,
            finished_at_utc="2026-05-26T00:00:00+00:00",
            output_metadata={
                "artifact_manifest_path": str(manifest_path),
                "comparison_summary_path": str(comparison_path),
            },
        )
    )

    response = client.get("/erp-runs/erp-001/export-bundle")

    assert response.status_code == 200
    with zipfile.ZipFile(BytesIO(response.content)) as bundle:
        analysis_report = json.loads(bundle.read("analysis_report.json"))
        bundle_manifest = json.loads(bundle.read("export_bundle_manifest.json"))

    assert analysis_report["comparison_statistics"]["status"] == "unavailable"
    assert bundle_manifest["comparison_summary"]["available"] is True
    assert bundle_manifest["comparison_summary"]["condition_a"] == "target"
    assert bundle_manifest["comparison_statistics"]["status"] == "unavailable"
    warning_codes = {
        warning["code"]
        for warning in bundle_manifest["diagnostics"]["warnings"]
    }
    assert "insufficient_observations" in warning_codes


def test_get_export_bundle_includes_missing_artifact_warning(tmp_path, monkeypatch):
    client, run_repository = _client(tmp_path, monkeypatch)
    manifest_path = _copy_erp_fixture_with_figure(tmp_path)
    (manifest_path.parent / "erp_standard.png").unlink()
    run_repository.save_erp_run(
        ErpRun(
            run_id="erp-001",
            dataset_id="dataset-001",
            config=ErpConfig(epoch_run_id="epoch-001"),
            status=ErpRunStatus.COMPLETED,
            finished_at_utc="2026-05-26T00:00:00+00:00",
            output_metadata={"artifact_manifest_path": str(manifest_path)},
        )
    )

    response = client.get("/datasets/dataset-001/export-bundle")

    assert response.status_code == 200
    with zipfile.ZipFile(BytesIO(response.content)) as bundle:
        assert "figures/erp_standard_plot.png" not in bundle.namelist()
        bundle_manifest = json.loads(bundle.read("export_bundle_manifest.json"))

    assert bundle_manifest["diagnostics"]["warnings"][0]["code"] == (
        "artifact_missing"
    )
    assert bundle_manifest["diagnostics"]["warnings"][0]["source"] == "export_bundle"
    assert "erp_standard_plot" in bundle_manifest["diagnostics"]["warnings"][0][
        "impact"
    ]


def test_get_export_bundle_warns_for_missing_phase_d_optional_metadata(
    tmp_path,
    monkeypatch,
):
    client, run_repository = _client(tmp_path, monkeypatch)
    registry_repository = api_main.registry_repository
    manifest_path = _copy_erp_fixture_with_figure(tmp_path)
    registry_repository.save_recording(
        Recording(
            recording_id="recording-001",
            dataset_id="dataset-001",
            file_id="file-001",
            metadata=RecordingMetadata(
                dataset_id="dataset-001",
                file_format="fif",
                channel_count=2,
                sampling_rate_hz=100.0,
                duration_seconds=6.0,
                channel_names=["Cz", "Pz"],
            ),
        )
    )
    registry_repository.save_event_log(
        EventLog(
            event_log_id="events-001",
            dataset_id="dataset-001",
            file_id="events-file-001",
            mapping=EventColumnMapping(onset_seconds="onset"),
            row_count=1,
            events=[NormalizedEvent(1.0, 1)],
        )
    )
    run_repository.save_erp_run(
        ErpRun(
            run_id="erp-001",
            dataset_id="dataset-001",
            config=ErpConfig(epoch_run_id="epoch-001"),
            status=ErpRunStatus.COMPLETED,
            finished_at_utc="2026-05-26T00:00:00+00:00",
            output_metadata={"artifact_manifest_path": str(manifest_path)},
        )
    )

    response = client.get("/datasets/dataset-001/export-bundle")

    assert response.status_code == 200
    with zipfile.ZipFile(BytesIO(response.content)) as bundle:
        phase_d_metadata = json.loads(bundle.read("diagnostics/phase_d_metadata.json"))
        bundle_manifest = json.loads(bundle.read("export_bundle_manifest.json"))

    warning_codes = {
        warning["code"]
        for warning in bundle_manifest["diagnostics"]["warnings"]
    }
    assert warning_codes == {
        "event_provenance_missing",
        "recording_source_files_missing",
        "sidecar_discovery_missing",
    }
    assert phase_d_metadata["diagnostics"]["warnings"] == (
        bundle_manifest["diagnostics"]["warnings"]
    )


def test_get_export_bundle_rejects_incomplete_run(tmp_path, monkeypatch):
    client, run_repository = _client(tmp_path, monkeypatch)
    run_repository.save_erp_run(
        ErpRun(
            run_id="erp-001",
            dataset_id="dataset-001",
            config=ErpConfig(epoch_run_id="epoch-001"),
            status=ErpRunStatus.PENDING,
        )
    )

    response = client.get("/erp-runs/erp-001/export-bundle")

    assert response.status_code == 409
    assert response.json()["detail"] == "Run is not completed"


def _client(tmp_path, monkeypatch):
    registry_repository = JsonRegistryRepository(tmp_path / "uploads")
    run_repository = JsonRunRepository(tmp_path / "runs")
    batch_repository = JsonBatchRepository(tmp_path / "batches")
    monkeypatch.setattr(api_main, "registry_repository", registry_repository)
    monkeypatch.setattr(api_main, "run_repository", run_repository)
    monkeypatch.setattr(api_main, "batch_repository", batch_repository)
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
    return client, run_repository


def _copy_fixture(tmp_path: Path, name: str) -> Path:
    destination = tmp_path / "artifacts" / name
    shutil.copytree(FIXTURE_ROOT / name, destination)
    return destination / "artifact_manifest.json"


def _save_completed_batch_for_run(run_id: str) -> None:
    template = WorkflowTemplate(
        template_id="template-001",
        name="Batch preprocessing",
        created_at_utc="2026-05-28T00:00:00Z",
        updated_at_utc="2026-05-28T00:10:00Z",
        workflow=WorkflowTemplateWorkflow(
            preprocessing=PreprocessingConfig(reference="average")
        ),
    )
    api_main.batch_repository.save_batch(
        BatchRunPlan(
            batch_id="batch-001",
            request=BatchRequest(
                template_id=template.template_id,
                dataset_selection=BatchDatasetSelection(dataset_ids=["dataset-001"]),
            ),
            template_snapshot=create_batch_template_snapshot(
                template,
                captured_at_utc="2026-05-28T00:15:00Z",
            ),
            items=[
                BatchSubjectRunPlan(
                    item_id="batch-001-item-001",
                    dataset_id="dataset-001",
                    status=BatchItemStatus.COMPLETED,
                    configs=template.workflow,
                    planned_steps=[RunKind.PREPROCESSING],
                    run_ids={"preprocessing": run_id},
                )
            ],
            status=BatchStatus.COMPLETED,
            created_at_utc="2026-05-28T00:16:00Z",
            updated_at_utc="2026-05-28T00:17:00Z",
        )
    )


def _copy_erp_fixture_with_figure(tmp_path: Path) -> Path:
    run_root = tmp_path / "artifacts" / "erp"
    shutil.copytree(FIXTURE_ROOT / "erp", run_root)
    (run_root / "erp_standard.png").write_bytes(b"png")
    manifest_path = run_root / "artifact_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"].append(
        {
            "logical_name": "erp_standard_plot",
            "artifact_type": "figure_png",
            "path": "erp_standard.png",
        }
    )
    manifest["artifact_count"] = len(manifest["artifacts"])
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest_path
