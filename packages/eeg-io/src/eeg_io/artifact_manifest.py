from dataclasses import dataclass
from pathlib import Path
from typing import Any
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
