"""EEG file and dataset boundary adapters."""

from eeg_io.artifact_manifest import (
    ArtifactManifest,
    ArtifactManifestError,
    ArtifactReference,
    artifact_manifest_from_dict,
    load_artifact_manifest,
)
from eeg_io.bids_sidecars import (
    BidsChannel,
    BidsEegSidecar,
    BidsSidecarError,
    read_channels_tsv,
    read_eeg_json,
)
from eeg_io.provenance import (
    PROVENANCE_SCHEMA_VERSION,
    build_event_log_provenance_payload,
    build_provenance_payload,
)

__all__ = [
    "ArtifactManifest",
    "ArtifactManifestError",
    "ArtifactReference",
    "BidsChannel",
    "BidsEegSidecar",
    "BidsSidecarError",
    "PROVENANCE_SCHEMA_VERSION",
    "artifact_manifest_from_dict",
    "build_provenance_payload",
    "build_event_log_provenance_payload",
    "load_artifact_manifest",
    "read_channels_tsv",
    "read_eeg_json",
]
