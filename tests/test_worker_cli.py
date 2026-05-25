import json
import os
import subprocess
import sys
from pathlib import Path

from eeg_core.domain import EpochConfig, EventLog, PreprocessingConfig
from eeg_processing import worker_cli
from eeg_processing.preprocessing import PreprocessingError


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_run_payload_completes_preprocessing(monkeypatch, tmp_path):
    input_path = tmp_path / "input.fif"
    output_path = tmp_path / "output.fif"
    metadata = {"channel_count": 2, "warnings": []}

    def fake_preprocess_raw_eeg(
        received_input: Path,
        received_output: Path,
        received_config: PreprocessingConfig,
    ):
        assert received_input == input_path
        assert received_output == output_path
        assert received_config == PreprocessingConfig(
            low_pass_hz=40.0,
            notch_hz=50.0,
            reference="average",
        )
        return metadata

    monkeypatch.setattr(
        worker_cli,
        "preprocess_raw_eeg",
        fake_preprocess_raw_eeg,
    )

    exit_code, result = worker_cli.run_payload(
        {
            "schema_version": 1,
            "job": "preprocessing",
            "run_id": "preprocess-001",
            "input_path": str(input_path),
            "output_path": str(output_path),
            "config": {
                "low_pass_hz": 40,
                "notch_hz": 50,
                "reference": "average",
            },
        }
    )

    assert exit_code == 0
    assert result == {
        "schema_version": 1,
        "job": "preprocessing",
        "run_id": "preprocess-001",
        "status": "completed",
        "metadata": metadata,
        "warnings": [],
        "error": None,
    }


def test_run_payload_returns_failed_result_for_preprocessing_error(monkeypatch, tmp_path):
    def fake_preprocess_raw_eeg(
        received_input: Path,
        received_output: Path,
        received_config: PreprocessingConfig,
    ):
        raise PreprocessingError("bad input", processing_warnings=["missing channel"])

    monkeypatch.setattr(
        worker_cli,
        "preprocess_raw_eeg",
        fake_preprocess_raw_eeg,
    )

    exit_code, result = worker_cli.run_payload(
        {
            "schema_version": 1,
            "job": "preprocessing",
            "run_id": "preprocess-002",
            "input_path": str(tmp_path / "input.fif"),
            "output_path": str(tmp_path / "output.fif"),
            "config": {},
        }
    )

    assert exit_code == 1
    assert result["status"] == "failed"
    assert result["metadata"] == {}
    assert result["warnings"] == ["missing channel"]
    assert result["error"] == "bad input"


def test_run_payload_rejects_unsupported_schema():
    exit_code, result = worker_cli.run_payload(
        {
            "schema_version": 2,
            "job": "preprocessing",
            "run_id": "preprocess-003",
        }
    )

    assert exit_code == 1
    assert result["status"] == "failed"
    assert result["error"] == "Unsupported worker payload schema_version: 2"


def test_run_payload_rejects_unsupported_job():
    exit_code, result = worker_cli.run_payload(
        {
            "schema_version": 1,
            "job": "unknown",
            "run_id": "unknown-001",
        }
    )

    assert exit_code == 1
    assert result["status"] == "failed"
    assert result["error"] == "Unsupported worker job: unknown"


def test_run_payload_accepts_epoching_job_routing():
    exit_code, result = worker_cli.run_payload(
        _epoching_payload(run_id="epoch-001")
    )

    assert exit_code == 1
    assert result["job"] == "epoching"
    assert result["run_id"] == "epoch-001"
    assert result["status"] == "failed"
    assert result["error"] == "Payload input_path must be a non-empty string."


def test_run_payload_completes_epoching(monkeypatch, tmp_path):
    expected_input_path = tmp_path / "raw_preprocessed_raw.fif"
    expected_output_path = tmp_path / "epochs-epo.fif"
    metadata = {"epoch_count": 3, "warnings": []}

    def fake_epoch_preprocessed_eeg(
        input_path: Path,
        output_path: Path,
        event_log: EventLog,
        config: EpochConfig,
        preprocessing_run_id: str,
    ):
        assert input_path == expected_input_path
        assert output_path == expected_output_path
        assert event_log.event_log_id == "event-log-001"
        assert event_log.events[0].trial_type == "target"
        assert config == EpochConfig(
            preprocessing_run_id="preprocess-001",
            condition_field="trial_type",
            tmin_seconds=-0.1,
            tmax_seconds=0.3,
        )
        assert preprocessing_run_id == "preprocess-001"
        return metadata

    monkeypatch.setattr(
        worker_cli,
        "epoch_preprocessed_eeg",
        fake_epoch_preprocessed_eeg,
    )

    exit_code, result = worker_cli.run_payload(
        _epoching_payload(
            run_id="epoch-002",
            input_path=str(expected_input_path),
            output_path=str(expected_output_path),
        )
    )

    assert exit_code == 0
    assert result == {
        "schema_version": 1,
        "job": "epoching",
        "run_id": "epoch-002",
        "status": "completed",
        "metadata": metadata,
        "warnings": [],
        "error": None,
    }


def test_run_payload_returns_failed_result_for_epoching_error(monkeypatch, tmp_path):
    def fake_epoch_preprocessed_eeg(
        input_path: Path,
        output_path: Path,
        event_log: EventLog,
        config: EpochConfig,
        preprocessing_run_id: str,
    ):
        raise worker_cli.EpochingError(
            "epoch failed",
            processing_warnings=["event warning"],
        )

    monkeypatch.setattr(
        worker_cli,
        "epoch_preprocessed_eeg",
        fake_epoch_preprocessed_eeg,
    )

    exit_code, result = worker_cli.run_payload(
        _epoching_payload(
            run_id="epoch-003",
            input_path=str(tmp_path / "raw.fif"),
            output_path=str(tmp_path / "epochs-epo.fif"),
        )
    )

    assert exit_code == 1
    assert result["job"] == "epoching"
    assert result["run_id"] == "epoch-003"
    assert result["status"] == "failed"
    assert result["warnings"] == ["event warning"]
    assert result["error"] == "epoch failed"


def test_run_payload_accepts_erp_job_routing():
    exit_code, result = worker_cli.run_payload(
        {
            "schema_version": 1,
            "job": "erp",
            "run_id": "erp-001",
        }
    )

    assert exit_code == 1
    assert result["job"] == "erp"
    assert result["run_id"] == "erp-001"
    assert result["status"] == "failed"
    assert result["error"] == "Worker job is not implemented yet: erp"


def test_main_writes_result_json(monkeypatch, tmp_path):
    payload_path = tmp_path / "payload.json"
    result_path = tmp_path / "result.json"
    input_path = tmp_path / "input.fif"
    output_path = tmp_path / "output.fif"
    payload_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "job": "preprocessing",
                "run_id": "preprocess-004",
                "input_path": str(input_path),
                "output_path": str(output_path),
                "config": {},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        worker_cli,
        "preprocess_raw_eeg",
        lambda received_input, received_output, received_config: {"ok": True},
    )

    exit_code = worker_cli.main(
        [
            "preprocessing",
            "--payload",
            str(payload_path),
            "--result",
            str(result_path),
        ]
    )

    assert exit_code == 0
    assert json.loads(result_path.read_text(encoding="utf-8")) == {
        "schema_version": 1,
        "job": "preprocessing",
        "run_id": "preprocess-004",
        "status": "completed",
        "metadata": {"ok": True},
        "warnings": [],
        "error": None,
    }


def test_main_rejects_payload_job_mismatch(tmp_path):
    payload_path = tmp_path / "payload.json"
    result_path = tmp_path / "result.json"
    payload_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "job": "epoching",
                "run_id": "epoch-001",
            }
        ),
        encoding="utf-8",
    )

    exit_code = worker_cli.main(
        [
            "preprocessing",
            "--payload",
            str(payload_path),
            "--result",
            str(result_path),
        ]
    )

    assert exit_code == 1
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["status"] == "failed"
    assert result["job"] == "preprocessing"
    assert result["error"] == "CLI job 'preprocessing' does not match payload job 'epoching'."


def test_worker_cli_module_runs_preprocessing_in_subprocess(tmp_path):
    payload_path = tmp_path / "payload.json"
    result_path = tmp_path / "result.json"
    output_path = tmp_path / "sample_preprocessed_raw.fif"
    input_path = REPO_ROOT / "tests" / "fixtures" / "eeg" / "sample_resting_raw.fif"
    payload_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "job": "preprocessing",
                "run_id": "preprocess-subprocess-001",
                "input_path": str(input_path),
                "output_path": str(output_path),
                "config": {"reference": "average"},
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "eeg_processing.worker_cli",
            "preprocessing",
            "--payload",
            str(payload_path),
            "--result",
            str(result_path),
        ],
        cwd=REPO_ROOT,
        env=_subprocess_env(),
        text=True,
        capture_output=True,
        timeout=60,
    )

    assert completed.returncode == 0, completed.stderr
    assert output_path.exists()
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["schema_version"] == 1
    assert result["job"] == "preprocessing"
    assert result["run_id"] == "preprocess-subprocess-001"
    assert result["status"] == "completed"
    assert result["error"] is None
    assert result["metadata"]["file_format"] == "fif"


def test_worker_cli_module_writes_failed_result_in_subprocess(tmp_path):
    payload_path = tmp_path / "payload.json"
    result_path = tmp_path / "result.json"
    payload_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "job": "preprocessing",
                "run_id": "preprocess-subprocess-002",
                "input_path": str(tmp_path / "missing.fif"),
                "output_path": str(tmp_path / "output.fif"),
                "config": {"high_pass_hz": True},
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "eeg_processing.worker_cli",
            "preprocessing",
            "--payload",
            str(payload_path),
            "--result",
            str(result_path),
        ],
        cwd=REPO_ROOT,
        env=_subprocess_env(),
        text=True,
        capture_output=True,
        timeout=60,
    )

    assert completed.returncode == 1
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["schema_version"] == 1
    assert result["job"] == "preprocessing"
    assert result["run_id"] == "preprocess-subprocess-002"
    assert result["status"] == "failed"
    assert result["metadata"] == {}
    assert result["error"] == "Payload config high_pass_hz must be a number or null."


def test_worker_cli_module_runs_epoching_in_subprocess(tmp_path):
    payload_path = tmp_path / "payload.json"
    result_path = tmp_path / "result.json"
    output_path = tmp_path / "epochs-epo.fif"
    input_path = REPO_ROOT / "tests" / "fixtures" / "eeg" / "sample_resting_raw.fif"
    payload_path.write_text(
        json.dumps(
            _epoching_payload(
                run_id="epoch-subprocess-001",
                input_path=str(input_path),
                output_path=str(output_path),
            )
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "eeg_processing.worker_cli",
            "epoching",
            "--payload",
            str(payload_path),
            "--result",
            str(result_path),
        ],
        cwd=REPO_ROOT,
        env=_subprocess_env(),
        text=True,
        capture_output=True,
        timeout=60,
    )

    assert completed.returncode == 0, completed.stderr
    assert output_path.exists()
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["schema_version"] == 1
    assert result["job"] == "epoching"
    assert result["run_id"] == "epoch-subprocess-001"
    assert result["status"] == "completed"
    assert result["error"] is None
    assert result["metadata"]["input_preprocessing_run_id"] == "preprocess-001"
    assert result["metadata"]["epoch_count"] == 3


def test_worker_cli_module_writes_failed_epoching_result_in_subprocess(tmp_path):
    payload_path = tmp_path / "payload.json"
    result_path = tmp_path / "result.json"
    payload_path.write_text(
        json.dumps(
            _epoching_payload(
                run_id="epoch-subprocess-002",
                input_path=str(tmp_path / "missing.fif"),
                output_path=str(tmp_path / "epochs-epo.fif"),
                config_overrides={"tmin_seconds": True},
            )
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "eeg_processing.worker_cli",
            "epoching",
            "--payload",
            str(payload_path),
            "--result",
            str(result_path),
        ],
        cwd=REPO_ROOT,
        env=_subprocess_env(),
        text=True,
        capture_output=True,
        timeout=60,
    )

    assert completed.returncode == 1
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["schema_version"] == 1
    assert result["job"] == "epoching"
    assert result["run_id"] == "epoch-subprocess-002"
    assert result["status"] == "failed"
    assert result["metadata"] == {}
    assert result["error"] == "Payload tmin_seconds must be a number."


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    package_paths = [
        str(REPO_ROOT / "packages" / "eeg-core" / "src"),
        str(REPO_ROOT / "packages" / "eeg-processing" / "src"),
    ]
    existing_pythonpath = env.get("PYTHONPATH")
    if existing_pythonpath:
        package_paths.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(package_paths)
    return env


def _epoching_payload(
    *,
    run_id: str,
    input_path: str | None = None,
    output_path: str | None = None,
    config_overrides: dict | None = None,
) -> dict:
    config = {
        "preprocessing_run_id": "preprocess-001",
        "condition_field": "trial_type",
        "tmin_seconds": -0.1,
        "tmax_seconds": 0.3,
        "baseline_start_seconds": None,
        "baseline_end_seconds": None,
        "reject_eeg_uv": None,
    }
    if config_overrides:
        config.update(config_overrides)

    payload = {
        "schema_version": 1,
        "job": "epoching",
        "run_id": run_id,
        "event_log": {
            "event_log_id": "event-log-001",
            "dataset_id": "dataset-001",
            "file_id": "file-002",
            "mapping": {
                "onset_seconds": "onset",
                "trial_type": "trial_type",
            },
            "row_count": 3,
            "events": [
                {
                    "onset_seconds": 1.0,
                    "source_row": 1,
                    "trial_type": "target",
                },
                {
                    "onset_seconds": 2.0,
                    "source_row": 2,
                    "trial_type": "standard",
                },
                {
                    "onset_seconds": 3.0,
                    "source_row": 3,
                    "trial_type": "target",
                },
            ],
        },
        "config": config,
    }
    if input_path is not None:
        payload["input_path"] = input_path
    if output_path is not None:
        payload["output_path"] = output_path
    return payload
