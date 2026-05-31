import json
from pathlib import Path

from eeg_core.domain import DiagnosticWarningSource


SCHEMA_PATH = Path("docs/schemas/project-archive-manifest.schema.json")
DOC_PATH = Path("docs/collaboration-snapshot-contract.md")
FIXTURE_PATH = Path(
    "tests/fixtures/collaboration/project_archive_manifest_v1.json"
)


def test_project_archive_manifest_schema_defines_immutable_snapshot_contract():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["properties"]["schema_version"]["const"] == 1
    assert schema["properties"]["manifest_kind"]["const"] == (
        "project_archive_manifest"
    )
    immutability = schema["properties"]["immutability"]["properties"]
    assert immutability["snapshot"]["const"] is True
    assert immutability["content_addressed"]["const"] is True
    assert immutability["mutation_policy"]["enum"] == ["append_new_archive_only"]
    assert schema["properties"]["checksums"]["properties"]["algorithm"]["const"] == (
        "sha256"
    )
    assert schema["properties"]["included_data_policy"]["properties"][
        "include_reports"
    ]["const"] is True
    assert schema["properties"]["included_data_policy"]["properties"][
        "include_manifests"
    ]["const"] is True
    assert schema["properties"]["included_data_policy"]["properties"][
        "include_provenance"
    ]["const"] is True
    excluded = schema["properties"]["excluded_data_policy"]["properties"][
        "excluded_categories"
    ]["items"]["enum"]
    assert "secrets" in excluded
    assert "runtime_cache" in excluded


def test_project_archive_manifest_fixture_matches_policy_and_checksum_contract():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    allowed_sources = {source.value for source in DiagnosticWarningSource}

    assert set(payload) == set(schema["required"])
    assert payload["schema_version"] == 1
    assert payload["manifest_kind"] == "project_archive_manifest"
    assert payload["immutability"] == {
        "snapshot": True,
        "content_addressed": True,
        "mutation_policy": "append_new_archive_only",
        "manifest_digest_sha256": None,
    }
    assert payload["included_data_policy"] == {
        "include_raw_uploads": False,
        "include_derivatives": False,
        "include_reports": True,
        "include_manifests": True,
        "include_provenance": True,
    }
    assert "raw_eeg" in payload["excluded_data_policy"]["excluded_categories"]
    assert "secrets" in payload["excluded_data_policy"]["excluded_categories"]
    assert payload["excluded_data_policy"]["redaction_required"] is True
    assert payload["checksums"]["algorithm"] == "sha256"
    assert payload["checksums"]["entry_count"] == len(payload["entries"])
    assert len(payload["checksums"]["manifest_payload_digest_sha256"]) == 64
    assert payload["checksums"]["archive_digest_sha256"] is None

    for entry in payload["entries"]:
        assert not Path(entry["archive_path"]).is_absolute()
        assert ".." not in Path(entry["archive_path"]).parts
        assert len(entry["checksum_sha256"]) == 64
        assert entry["size_bytes"] >= 0

    for warning in payload["diagnostics"]["warnings"]:
        assert set(warning) == {
            "code",
            "severity",
            "source",
            "impact",
            "suggested_action",
        }
        assert warning["severity"] in {"warning", "error"}
        assert warning["source"] in allowed_sources


def test_collaboration_snapshot_doc_references_schema_fixture_and_policies():
    text = DOC_PATH.read_text(encoding="utf-8")

    assert "docs/schemas/project-archive-manifest.schema.json" in text
    assert "tests/fixtures/collaboration/project_archive_manifest_v1.json" in text
    assert "`project_archive_manifest.json` is the root descriptor" in text
    assert "Preview snapshots default to reviewable metadata" in text
    assert "Archives must never include `secrets`" in text
    assert "`checksums.algorithm`: `sha256`" in text
    assert "Existing manifests must not be rewritten" in text
