import json
from pathlib import Path

from eeg_core.domain import DiagnosticWarningSource


FIXTURE_ROOT = Path("tests/fixtures/public_smoke")
DOCS = [
    Path("docs/public-data-smoke-fixtures.md"),
    Path("docs/public-demo-physionet-eegmmi.md"),
    Path("docs/public-demo-openneuro-bids.md"),
]


def test_public_smoke_expected_warning_snapshots_use_d4_taxonomy():
    allowed_sources = {source.value for source in DiagnosticWarningSource}
    fixture_paths = sorted(FIXTURE_ROOT.glob("*_expected_warnings.json"))

    assert {path.name for path in fixture_paths} == {
        "openneuro_bids_style_expected_warnings.json",
        "physionet_eegmmi_s001r03_expected_warnings.json",
    }

    for path in fixture_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["schema_version"] == 1
        assert payload["profile_id"]
        for warning in [
            *payload.get("expected_warnings", []),
            *payload.get("allowed_warnings", []),
        ]:
            assert set(warning) >= {
                "code",
                "severity",
                "source",
                "suggested_action",
            }
            assert warning["severity"] in {"warning", "error"}
            assert warning["source"] in allowed_sources


def test_public_smoke_docs_pin_ignored_data_paths_and_full_workflow():
    for path in DOCS:
        text = path.read_text(encoding="utf-8")
        assert "data/raw/public-samples" in text

    overview = Path("docs/public-data-smoke-fixtures.md").read_text(encoding="utf-8")
    for stage in [
        "Ingest the EEG recording",
        "Save event mapping",
        "Validate the dataset",
        "Run preprocessing",
        "Run epoching",
        "Run ERP generation",
        "Run descriptive comparison summary",
    ]:
        assert stage in overview


def test_public_smoke_docs_reference_expected_warning_snapshots():
    for path in DOCS:
        text = path.read_text(encoding="utf-8")
        assert "tests/fixtures/public_smoke/" in text


def test_public_data_root_is_git_ignored():
    gitignore = Path(".gitignore").read_text(encoding="utf-8")

    assert "data/" in gitignore.splitlines()
