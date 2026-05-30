"""EEG file and dataset boundary adapters."""

from eeg_io.artifact_manifest import (
    ArtifactManifest,
    ArtifactManifestError,
    ArtifactReference,
    artifact_manifest_from_dict,
    check_artifact_integrity,
    load_artifact_manifest,
)
from eeg_io.analysis_report import (
    ANALYSIS_REPORT_SCHEMA_VERSION,
    AnalysisReportError,
    build_analysis_report,
    write_analysis_report,
)
from eeg_io.bids_sidecars import (
    BidsChannel,
    BidsEegSidecar,
    BidsSidecarCandidate,
    BidsSidecarDiagnostic,
    BidsSidecarDiscovery,
    BidsSidecarError,
    bids_basename_from_path,
    discover_bids_sidecars,
    read_channels_tsv,
    read_eeg_json,
)
from eeg_io.export_bundle import (
    EXPORT_BUNDLE_SCHEMA_VERSION,
    ExportBundleError,
    build_export_bundle,
)
from eeg_io.provenance import (
    PROVENANCE_SCHEMA_VERSION,
    build_event_log_provenance_payload,
    build_provenance_payload,
)
from eeg_io.qc_summary import QC_SUMMARY_SCHEMA_VERSION, QcSummaryError, build_qc_summary

__all__ = [
    "ArtifactManifest",
    "ArtifactManifestError",
    "ArtifactReference",
    "ANALYSIS_REPORT_SCHEMA_VERSION",
    "AnalysisReportError",
    "BidsChannel",
    "BidsEegSidecar",
    "BidsSidecarCandidate",
    "BidsSidecarDiagnostic",
    "BidsSidecarDiscovery",
    "BidsSidecarError",
    "EXPORT_BUNDLE_SCHEMA_VERSION",
    "ExportBundleError",
    "PROVENANCE_SCHEMA_VERSION",
    "QC_SUMMARY_SCHEMA_VERSION",
    "QcSummaryError",
    "artifact_manifest_from_dict",
    "build_analysis_report",
    "build_export_bundle",
    "build_provenance_payload",
    "build_event_log_provenance_payload",
    "build_qc_summary",
    "bids_basename_from_path",
    "check_artifact_integrity",
    "discover_bids_sidecars",
    "load_artifact_manifest",
    "read_channels_tsv",
    "read_eeg_json",
    "write_analysis_report",
]
