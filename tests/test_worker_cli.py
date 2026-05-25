import json
import os
import subprocess
import sys
from pathlib import Path

from eeg_core.domain import PreprocessingConfig
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
        {
            "schema_version": 1,
            "job": "epoching",
            "run_id": "epoch-001",
        }
    )

    assert exit_code == 1
    assert result["job"] == "epoching"
    assert result["run_id"] == "epoch-001"
    assert result["status"] == "failed"
    assert result["error"] == "Worker job is not implemented yet: epoching"


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
