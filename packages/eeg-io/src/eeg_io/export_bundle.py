from pathlib import Path
from typing import Any
import json
import zipfile

from eeg_io.artifact_manifest import ArtifactReference, load_artifact_manifest


EXPORT_BUNDLE_SCHEMA_VERSION = 1
_FIGURE_EXTENSIONS = {".png", ".svg", ".jpg", ".jpeg", ".webp", ".pdf"}


class ExportBundleError(Exception):
    pass


def build_export_bundle(
    *,
    artifact_manifest_path: Path,
    output_zip_path: Path,
    analysis_report_path: Path | None = None,
    extra_artifacts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    manifest = load_artifact_manifest(artifact_manifest_path)
    diagnostics = {"warnings": _missing_artifact_warnings(manifest.missing_artifacts)}
    entries: list[dict[str, Any]] = []

    output_zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        output_zip_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as bundle:
        _write_file_entry(
            bundle,
            source_path=artifact_manifest_path,
            archive_path="artifact_manifest.json",
            logical_name="artifact_manifest",
            artifact_type="artifact_manifest_json",
            entries=entries,
        )

        if analysis_report_path is not None:
            if not analysis_report_path.is_file():
                diagnostics["warnings"].append(
                    _missing_warning(
                        logical_name="analysis_report",
                        path=analysis_report_path,
                    )
                )
            else:
                _write_file_entry(
                    bundle,
                    source_path=analysis_report_path,
                    archive_path="analysis_report.json",
                    logical_name="analysis_report",
                    artifact_type="analysis_report_json",
                    entries=entries,
                )

        used_archive_paths = {entry["archive_path"] for entry in entries}
        for artifact in extra_artifacts or []:
            source_path = Path(str(artifact.get("path", "")))
            logical_name = str(artifact.get("logical_name", "extra_artifact"))
            artifact_type = str(artifact.get("artifact_type", "extra_artifact"))
            archive_path = str(
                artifact.get("archive_path")
                or f"artifacts/{_safe_filename(source_path.name)}"
            )
            if not source_path.is_file():
                diagnostics["warnings"].append(
                    _missing_warning(logical_name=logical_name, path=source_path)
                )
                continue
            archive_path = _dedupe_archive_path(archive_path, used_archive_paths)
            used_archive_paths.add(archive_path)
            _write_file_entry(
                bundle,
                source_path=source_path,
                archive_path=archive_path,
                logical_name=logical_name,
                artifact_type=artifact_type,
                entries=entries,
            )

        for artifact in manifest.artifacts:
            if artifact.logical_name == "analysis_report":
                continue
            if not artifact.exists:
                continue
            archive_path = _artifact_archive_path(artifact)
            archive_path = _dedupe_archive_path(archive_path, used_archive_paths)
            used_archive_paths.add(archive_path)
            _write_file_entry(
                bundle,
                source_path=artifact.path,
                archive_path=archive_path,
                logical_name=artifact.logical_name,
                artifact_type=artifact.artifact_type,
                entries=entries,
            )

        bundle_manifest = {
            "schema_version": EXPORT_BUNDLE_SCHEMA_VERSION,
            "artifact_manifest_path": str(artifact_manifest_path.resolve()),
            "analysis_report_included": analysis_report_path is not None
            and analysis_report_path.is_file(),
            "entry_count": len(entries),
            "entries": entries,
            "diagnostics": diagnostics,
        }
        bundle.writestr(
            "export_bundle_manifest.json",
            json.dumps(bundle_manifest, indent=2, sort_keys=True) + "\n",
        )

    return {
        "schema_version": EXPORT_BUNDLE_SCHEMA_VERSION,
        "bundle_path": str(output_zip_path.resolve()),
        "entry_count": len(entries),
        "diagnostics": diagnostics,
    }


def _write_file_entry(
    bundle: zipfile.ZipFile,
    *,
    source_path: Path,
    archive_path: str,
    logical_name: str,
    artifact_type: str,
    entries: list[dict[str, Any]],
) -> None:
    resolved_path = source_path.resolve()
    bundle.write(resolved_path, archive_path)
    entries.append(
        {
            "logical_name": logical_name,
            "artifact_type": artifact_type,
            "archive_path": archive_path,
            "source_path": str(resolved_path),
            "size_bytes": resolved_path.stat().st_size,
        }
    )


def _artifact_archive_path(artifact: ArtifactReference) -> str:
    directory = _artifact_archive_directory(artifact)
    filename = _safe_filename(
        f"{artifact.logical_name}{artifact.path.suffix.lower()}"
    )
    return f"{directory}/{filename}"


def _artifact_archive_directory(artifact: ArtifactReference) -> str:
    if _is_figure_artifact(artifact):
        return "figures"
    if _is_config_artifact(artifact):
        return "configs"
    if _is_provenance_artifact(artifact):
        return "provenance"
    if _is_diagnostic_artifact(artifact):
        return "diagnostics"
    return "artifacts"


def _is_figure_artifact(artifact: ArtifactReference) -> bool:
    artifact_type = artifact.artifact_type.lower()
    return (
        "figure" in artifact_type
        or "plot" in artifact_type
        or artifact.path.suffix.lower() in _FIGURE_EXTENSIONS
    )


def _is_config_artifact(artifact: ArtifactReference) -> bool:
    name = artifact.logical_name.lower()
    artifact_type = artifact.artifact_type.lower()
    return "config" in name or "config" in artifact_type


def _is_provenance_artifact(artifact: ArtifactReference) -> bool:
    name = artifact.logical_name.lower()
    artifact_type = artifact.artifact_type.lower()
    return "provenance" in name or "provenance" in artifact_type


def _is_diagnostic_artifact(artifact: ArtifactReference) -> bool:
    name = artifact.logical_name.lower()
    artifact_type = artifact.artifact_type.lower()
    return (
        "diagnostic" in name
        or "diagnostic" in artifact_type
        or "metadata" in name
        or "metadata" in artifact_type
        or name.endswith("summary")
        or name.endswith("report")
    )


def _safe_filename(value: str) -> str:
    safe = "".join(
        character
        if character.isalnum() or character in {"-", "_", "."}
        else "_"
        for character in value
    )
    return safe.strip("._") or "artifact"


def _dedupe_archive_path(value: str, used_archive_paths: set[str]) -> str:
    if value not in used_archive_paths:
        return value
    path = Path(value)
    index = 2
    while True:
        candidate = str(path.with_name(f"{path.stem}_{index}{path.suffix}")).replace(
            "\\",
            "/",
        )
        if candidate not in used_archive_paths:
            return candidate
        index += 1


def _missing_artifact_warnings(
    missing_artifacts: list[ArtifactReference],
) -> list[dict[str, Any]]:
    return [
        _missing_warning(logical_name=artifact.logical_name, path=artifact.path)
        for artifact in missing_artifacts
    ]


def _missing_warning(*, logical_name: str, path: Path) -> dict[str, Any]:
    return {
        "code": "artifact_missing",
        "severity": "warning",
        "source": "export_bundle",
        "impact": (
            f"Artifact {logical_name!r} was not included in the export bundle "
            f"because the file was not found: {path}"
        ),
        "suggested_action": (
            "Regenerate the source run artifact or rebuild the artifact manifest."
        ),
    }
