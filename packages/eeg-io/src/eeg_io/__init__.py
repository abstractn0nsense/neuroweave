"""EEG file and dataset boundary adapters."""

from eeg_io.artifact_manifest import (
    ArtifactManifest,
    ArtifactManifestError,
    ArtifactReference,
    artifact_manifest_from_dict,
    load_artifact_manifest,
)

__all__ = [
    "ArtifactManifest",
    "ArtifactManifestError",
    "ArtifactReference",
    "artifact_manifest_from_dict",
    "load_artifact_manifest",
]
