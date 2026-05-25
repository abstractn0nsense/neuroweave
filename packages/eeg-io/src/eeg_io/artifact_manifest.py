from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib
import json


class ArtifactManifestError(Exception):
    pass


@dataclass(frozen=True)
class ArtifactReference:
    logical_name: str
    artifact_type: str
    path: Path
    size_bytes: int | None = None
    checksum_sha256: str | None = None
    created_at_utc: str | None = None
    exists: bool = True


@dataclass(frozen=True)
class ArtifactManifest:
    schema_version: int
    artifact_root: Path
    artifact_count: int
    artifacts: list[ArtifactReference]
    missing_artifacts: list[ArtifactReference]


def check_artifact_integrity(path: Path) -> dict[str, Any]:
    manifest = load_artifact_manifest(path)
    items = [_integrity_item(artifact) for artifact in manifest.artifacts]
    status_counts = {
        "ok": sum(1 for item in items if item["status"] == "ok"),
        "missing": sum(1 for item in items if item["status"] == "missing"),
        "mismatch": sum(1 for item in items if item["status"] == "mismatch"),
    }
    overall_status = "ok"
    if status_counts["missing"] > 0:
        overall_status = "missing"
    if status_counts["mismatch"] > 0:
        overall_status = "mismatch"

    return {
        "schema_version": 1,
        "manifest_path": str(path.resolve()),
        "artifact_root": str(manifest.artifact_root),
        "artifact_count": manifest.artifact_count,
        "status": overall_status,
        "status_counts": status_counts,
        "artifacts": items,
    }


def load_artifact_manifest(path: Path) -> ArtifactManifest:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ArtifactManifestError(f"Artifact manifest not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ArtifactManifestError(f"Invalid artifact manifest JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ArtifactManifestError("Artifact manifest must be a JSON object.")

    return artifact_manifest_from_dict(payload, manifest_path=path)


def artifact_manifest_from_dict(
    payload: dict[str, Any],
    *,
    manifest_path: Path,
) -> ArtifactManifest:
    schema_version = payload.get("schema_version")
    if schema_version != 1:
        raise ArtifactManifestError(
            f"Unsupported artifact manifest schema_version: {schema_version!r}"
        )

    artifact_root_value = payload.get("artifact_root")
    if not isinstance(artifact_root_value, str) or not artifact_root_value.strip():
        raise ArtifactManifestError("Artifact manifest artifact_root must be a string.")

    artifact_root = _resolve_manifest_path(
        artifact_root_value,
        base_directory=manifest_path.parent,
    )
    artifact_entries = payload.get("artifacts")
    if not isinstance(artifact_entries, list):
        raise ArtifactManifestError("Artifact manifest artifacts must be a list.")

    artifact_count = payload.get("artifact_count")
    if not isinstance(artifact_count, int) or isinstance(artifact_count, bool):
        raise ArtifactManifestError("Artifact manifest artifact_count must be an integer.")
    if artifact_count != len(artifact_entries):
        raise ArtifactManifestError(
            "Artifact manifest artifact_count does not match artifacts length."
        )

    artifacts: list[ArtifactReference] = []
    missing_artifacts: list[ArtifactReference] = []
    for index, entry in enumerate(artifact_entries):
        reference = _artifact_reference_from_dict(
            entry,
            index=index,
            artifact_root=artifact_root,
            manifest_path=manifest_path,
        )
        artifacts.append(reference)
        if not reference.exists:
            missing_artifacts.append(reference)

    return ArtifactManifest(
        schema_version=schema_version,
        artifact_root=artifact_root,
        artifact_count=artifact_count,
        artifacts=artifacts,
        missing_artifacts=missing_artifacts,
    )


def _integrity_item(artifact: ArtifactReference) -> dict[str, Any]:
    if not artifact.exists:
        return {
            **_integrity_base(artifact),
            "status": "missing",
            "actual_size_bytes": None,
            "actual_checksum_sha256": None,
        }

    actual_checksum = _sha256_file(artifact.path)
    actual_size = artifact.path.stat().st_size
    expected_checksum = artifact.checksum_sha256
    checksum_matches = (
        expected_checksum is None
        or expected_checksum.lower() == actual_checksum.lower()
    )
    size_matches = artifact.size_bytes is None or artifact.size_bytes == actual_size
    status = "ok" if checksum_matches and size_matches else "mismatch"

    return {
        **_integrity_base(artifact),
        "status": status,
        "actual_size_bytes": actual_size,
        "actual_checksum_sha256": actual_checksum,
    }


def _integrity_base(artifact: ArtifactReference) -> dict[str, Any]:
    return {
        "logical_name": artifact.logical_name,
        "artifact_type": artifact.artifact_type,
        "path": str(artifact.path),
        "expected_size_bytes": artifact.size_bytes,
        "expected_checksum_sha256": artifact.checksum_sha256,
    }


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _artifact_reference_from_dict(
    value: Any,
    *,
    index: int,
    artifact_root: Path,
    manifest_path: Path,
) -> ArtifactReference:
    if not isinstance(value, dict):
        raise ArtifactManifestError(
            f"Artifact manifest entry {index} must be a JSON object."
        )

    logical_name = _required_string(value, "logical_name", index)
    artifact_type = _required_string(value, "artifact_type", index)
    path_value = _required_string(value, "path", index)
    artifact_path = _resolve_manifest_path(
        path_value,
        base_directory=manifest_path.parent,
    )
    if not artifact_path.is_relative_to(artifact_root):
        raise ArtifactManifestError(
            f"Artifact manifest entry {index} path escapes artifact_root: {path_value}"
        )

    return ArtifactReference(
        logical_name=logical_name,
        artifact_type=artifact_type,
        path=artifact_path,
        size_bytes=_optional_int(value.get("size_bytes"), "size_bytes", index),
        checksum_sha256=_optional_string(value.get("checksum_sha256")),
        created_at_utc=_optional_string(value.get("created_at_utc")),
        exists=artifact_path.is_file(),
    )


def _resolve_manifest_path(value: str, *, base_directory: Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = base_directory / path
    return path.resolve()


def _required_string(value: dict[str, Any], field_name: str, index: int) -> str:
    item = value.get(field_name)
    if not isinstance(item, str) or not item.strip():
        raise ArtifactManifestError(
            f"Artifact manifest entry {index} {field_name} must be a string."
        )
    return item


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_int(value: Any, field_name: str, index: int) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise ArtifactManifestError(
            f"Artifact manifest entry {index} {field_name} must be an integer."
        )
    return value
