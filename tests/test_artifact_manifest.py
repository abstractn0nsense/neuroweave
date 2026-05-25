import json
import hashlib

import pytest

from eeg_io.artifact_manifest import (
    ArtifactManifestError,
    artifact_manifest_from_dict,
    check_artifact_integrity,
    load_artifact_manifest,
)


def test_load_artifact_manifest_resolves_and_validates_artifacts(tmp_path):
    artifact_root = tmp_path / "run"
    artifact_root.mkdir()
    primary = artifact_root / "raw_preprocessed_raw.fif"
    primary.write_bytes(b"fif")
    manifest_path = artifact_root / "artifact_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_root": str(artifact_root),
                "artifact_count": 1,
                "artifacts": [
                    {
                        "logical_name": "raw_preprocessed",
                        "artifact_type": "primary_fif",
                        "path": str(primary),
                        "size_bytes": 3,
                        "checksum_sha256": "abc123",
                        "created_at_utc": "2026-05-26T00:00:00+00:00",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    manifest = load_artifact_manifest(manifest_path)

    assert manifest.schema_version == 1
    assert manifest.artifact_root == artifact_root.resolve()
    assert manifest.artifact_count == 1
    assert manifest.missing_artifacts == []
    assert manifest.artifacts[0].logical_name == "raw_preprocessed"
    assert manifest.artifacts[0].artifact_type == "primary_fif"
    assert manifest.artifacts[0].path == primary.resolve()
    assert manifest.artifacts[0].exists is True


def test_load_artifact_manifest_collects_missing_artifacts(tmp_path):
    artifact_root = tmp_path / "run"
    artifact_root.mkdir()
    missing = artifact_root / "missing.json"
    manifest_path = artifact_root / "artifact_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_root": str(artifact_root),
                "artifact_count": 1,
                "artifacts": [
                    {
                        "logical_name": "drop_log",
                        "artifact_type": "diagnostic_json",
                        "path": str(missing),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    manifest = load_artifact_manifest(manifest_path)

    assert len(manifest.artifacts) == 1
    assert manifest.artifacts[0].exists is False
    assert manifest.missing_artifacts == [manifest.artifacts[0]]


def test_artifact_manifest_rejects_path_escape(tmp_path):
    artifact_root = tmp_path / "run"
    artifact_root.mkdir()
    escaped = tmp_path / "outside.txt"
    escaped.write_text("outside", encoding="utf-8")

    with pytest.raises(ArtifactManifestError, match="escapes artifact_root"):
        artifact_manifest_from_dict(
            {
                "schema_version": 1,
                "artifact_root": str(artifact_root),
                "artifact_count": 1,
                "artifacts": [
                    {
                        "logical_name": "outside",
                        "artifact_type": "text",
                        "path": str(escaped),
                    }
                ],
            },
            manifest_path=artifact_root / "artifact_manifest.json",
        )


def test_check_artifact_integrity_reports_ok_missing_and_mismatch(tmp_path):
    artifact_root = tmp_path / "run"
    artifact_root.mkdir()
    ok = artifact_root / "ok.json"
    mismatch = artifact_root / "mismatch.json"
    missing = artifact_root / "missing.json"
    ok.write_text("ok", encoding="utf-8")
    mismatch.write_text("changed", encoding="utf-8")
    manifest_path = artifact_root / "artifact_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_root": str(artifact_root),
                "artifact_count": 3,
                "artifacts": [
                    {
                        "logical_name": "ok",
                        "artifact_type": "diagnostic_json",
                        "path": str(ok),
                        "size_bytes": 2,
                        "checksum_sha256": hashlib.sha256(b"ok").hexdigest(),
                    },
                    {
                        "logical_name": "mismatch",
                        "artifact_type": "diagnostic_json",
                        "path": str(mismatch),
                        "checksum_sha256": hashlib.sha256(b"original").hexdigest(),
                    },
                    {
                        "logical_name": "missing",
                        "artifact_type": "diagnostic_json",
                        "path": str(missing),
                        "checksum_sha256": hashlib.sha256(b"missing").hexdigest(),
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = check_artifact_integrity(manifest_path)

    assert result["status"] == "mismatch"
    assert result["status_counts"] == {"ok": 1, "missing": 1, "mismatch": 1}
    assert {
        item["logical_name"]: item["status"]
        for item in result["artifacts"]
    } == {
        "ok": "ok",
        "mismatch": "mismatch",
        "missing": "missing",
    }
    assert result["artifacts"][0]["actual_checksum_sha256"] == hashlib.sha256(
        b"ok"
    ).hexdigest()


def test_artifact_manifest_rejects_count_mismatch(tmp_path):
    artifact_root = tmp_path / "run"
    artifact_root.mkdir()

    with pytest.raises(ArtifactManifestError, match="artifact_count"):
        artifact_manifest_from_dict(
            {
                "schema_version": 1,
                "artifact_root": str(artifact_root),
                "artifact_count": 2,
                "artifacts": [],
            },
            manifest_path=artifact_root / "artifact_manifest.json",
        )


def test_artifact_manifest_rejects_malformed_entries(tmp_path):
    artifact_root = tmp_path / "run"
    artifact_root.mkdir()

    with pytest.raises(ArtifactManifestError, match="logical_name"):
        artifact_manifest_from_dict(
            {
                "schema_version": 1,
                "artifact_root": str(artifact_root),
                "artifact_count": 1,
                "artifacts": [
                    {
                        "artifact_type": "diagnostic_json",
                        "path": str(artifact_root / "summary.json"),
                    }
                ],
            },
            manifest_path=artifact_root / "artifact_manifest.json",
        )
