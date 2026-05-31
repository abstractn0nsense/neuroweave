import json
from pathlib import Path

from eeg_core.domain import DiagnosticWarningSource


SCHEMA_PATH = Path("docs/schemas/artifact-action.schema.json")
DOC_PATH = Path("docs/advanced-artifact-workflow-contract.md")
FIXTURE_PATH = Path(
    "tests/fixtures/artifacts/artifact_action_manual_review_v1.json"
)


def test_artifact_action_schema_defines_manual_review_lifecycle():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["properties"]["schema_version"]["const"] == 1
    assert schema["properties"]["action_kind"]["enum"] == [
        "mark_bad_channels",
        "interpolate_bad_channels",
        "ica_exclude_components",
        "reject_artifact_annotations",
        "manual_review_note",
    ]
    assert "pending_manual_review" in schema["properties"]["status"]["enum"]
    assert schema["properties"]["review_state"]["properties"]["state"]["enum"] == [
        "not_required",
        "pending",
        "approved",
        "rejected",
    ]
    assert schema["properties"]["effects"]["properties"]["invalidates_downstream"][
        "items"
    ]["enum"] == [
        "preprocessing",
        "epoch",
        "erp",
        "comparison",
        "report",
        "export",
    ]
    assert schema["properties"]["export_report_policy"]["properties"][
        "block_export_when_pending"
    ]["const"] is False


def test_artifact_action_fixture_matches_required_shape_and_taxonomy():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    allowed_sources = {source.value for source in DiagnosticWarningSource}

    assert set(payload) == set(schema["required"])
    assert payload["schema_version"] == 1
    assert payload["action_kind"] == "ica_exclude_components"
    assert payload["status"] == "pending_manual_review"
    assert payload["review_state"] == {
        "required": True,
        "state": "pending",
        "reason": "ICA components require human confirmation before exclusion.",
        "reviewer": None,
        "reviewed_at_utc": None,
    }
    assert payload["targets"]["ica_components"] == [0, 2]
    assert payload["effects"]["mutates_signal"] is True
    assert payload["effects"]["requires_new_run"] is True
    assert "export" in payload["effects"]["invalidates_downstream"]
    assert payload["export_report_policy"]["block_export_when_pending"] is False
    assert payload["export_report_policy"]["include_in_analysis_report"] is True
    assert payload["export_report_policy"]["include_in_export_bundle"] is True

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


def test_artifact_action_doc_references_schema_fixture_and_outputs():
    text = DOC_PATH.read_text(encoding="utf-8")

    assert "docs/schemas/artifact-action.schema.json" in text
    assert "tests/fixtures/artifacts/artifact_action_manual_review_v1.json" in text
    assert "`analysis_report.json` should include an `artifact_actions` section" in text
    assert "`export_bundle_manifest.json` should include an `artifact_actions` section" in text
    assert "`artifact_manifest.json` should list action documents" in text
    assert "Pending manual review should not block ZIP creation" in text
    assert "Do not silently apply pending actions" in text
