import json
from pathlib import Path

from eeg_core.domain import DiagnosticWarningSource


SCHEMA_PATH = Path("docs/schemas/erp-comparison-statistics.schema.json")
DOC_PATH = Path("docs/statistics-contract.md")
FIXTURE_ROOT = Path("tests/fixtures/statistics")


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def test_statistics_contract_schema_defines_phase_e_mvp_scope():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["properties"]["schema_version"]["const"] == 1
    assert schema["properties"]["method"]["enum"] == ["paired_t_test"]
    assert schema["properties"]["design"]["enum"] == ["within_subject"]
    assert schema["properties"]["input_metric"]["enum"] == ["mean_amplitude_uv"]
    assert schema["properties"]["observation_level"]["enum"] == ["subject"]
    assert schema["properties"]["result"]["oneOf"][1]["properties"]["p_value_kind"][
        "enum"
    ] == ["uncorrected"]
    effect_size = schema["properties"]["result"]["oneOf"][1]["properties"][
        "effect_size"
    ]
    assert effect_size["properties"]["name"]["enum"] == ["cohens_dz"]
    assert schema["properties"]["result"]["oneOf"][1]["properties"][
        "confidence_interval"
    ]["properties"]["implemented"]["const"] is False
    assert schema["properties"]["result"]["oneOf"][1]["properties"][
        "multiple_comparison"
    ]["properties"]["applied"]["const"] is False


def test_statistics_contract_fixtures_match_required_shape_and_taxonomy():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    required = set(schema["required"])
    allowed_statuses = set(schema["properties"]["status"]["enum"])
    allowed_sources = {source.value for source in DiagnosticWarningSource}

    fixture_paths = sorted(FIXTURE_ROOT.glob("erp_comparison_statistics_*_v1.json"))
    assert {path.name for path in fixture_paths} == {
        "erp_comparison_statistics_paired_t_test_v1.json",
        "erp_comparison_statistics_unavailable_v1.json",
    }

    for path in fixture_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert set(payload) == required
        assert payload["schema_version"] == 1
        assert payload["status"] in allowed_statuses
        assert payload["method"] == "paired_t_test"
        assert payload["design"] == "within_subject"
        assert payload["input_metric"] == "mean_amplitude_uv"
        assert payload["observation_level"] == "subject"
        assert payload["sample"]["unit"] == "subject"
        assert payload["sample"]["paired"] is True
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


def test_statistics_contract_implemented_fixture_uses_paired_t_result():
    payload = _load_fixture("erp_comparison_statistics_paired_t_test_v1.json")

    assert payload["status"] == "implemented"
    assert payload["implemented"] is True
    assert payload["sample"]["n"] == 12
    assert payload["result"]["statistic_name"] == "t"
    assert payload["result"]["degrees_of_freedom"] == payload["sample"]["n"] - 1
    assert 0 <= payload["result"]["p_value"] <= 1
    assert payload["result"]["effect_size"]["name"] == "cohens_dz"
    assert payload["result"]["confidence_interval"]["implemented"] is False
    assert payload["result"]["multiple_comparison"]["applied"] is False


def test_statistics_contract_unavailable_fixture_does_not_invent_result():
    payload = _load_fixture("erp_comparison_statistics_unavailable_v1.json")

    assert payload["status"] == "unavailable"
    assert payload["implemented"] is False
    assert payload["sample"]["n"] == 1
    assert payload["result"] is None
    assert payload["diagnostics"]["warnings"][0]["code"] == (
        "insufficient_observations"
    )


def test_statistics_contract_doc_references_schema_and_fixtures():
    text = DOC_PATH.read_text(encoding="utf-8")

    assert "docs/schemas/erp-comparison-statistics.schema.json" in text
    assert "tests/fixtures/statistics/erp_comparison_statistics_paired_t_test_v1.json" in text
    assert "tests/fixtures/statistics/erp_comparison_statistics_unavailable_v1.json" in text
    assert "single-subject inference from only two evoked averages" in text
