import json
from pathlib import Path

from eeg_core.domain import DiagnosticWarningSource


DOC_PATH = Path("docs/reproducibility-graph-contract.md")
SCHEMA_PATH = Path("docs/schemas/reproducibility-graph.schema.json")
FIXTURE_PATH = Path(
    "tests/fixtures/reproducibility/reproducibility_graph_erp_comparison_v1.json"
)


def test_reproducibility_graph_schema_defines_v1_shape():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["properties"]["schema_version"]["const"] == 1
    assert schema["properties"]["graph_kind"]["const"] == "reproducibility_graph"
    assert set(schema["required"]) == {
        "schema_version",
        "graph_kind",
        "created_at_utc",
        "dataset_id",
        "root_node_id",
        "terminal_node_id",
        "nodes",
        "edges",
        "diagnostics",
    }
    assert schema["$defs"]["node"]["properties"]["kind"]["enum"] == [
        "dataset",
        "preprocessing_run",
        "epoch_run",
        "erp_run",
        "comparison",
    ]
    assert schema["$defs"]["edge"]["properties"]["relation"]["enum"] == [
        "contains",
        "produced",
        "derived_from",
        "compares",
    ]


def test_reproducibility_graph_fixture_pins_main_lineage():
    graph = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    nodes = {node["node_id"]: node for node in graph["nodes"]}
    edges = [
        (edge["source"], edge["target"], edge["relation"])
        for edge in graph["edges"]
    ]

    assert graph["schema_version"] == 1
    assert graph["graph_kind"] == "reproducibility_graph"
    assert graph["root_node_id"] == "dataset:dataset-001"
    assert graph["terminal_node_id"] == "comparison:erp-001:comparison_summary"
    assert set(nodes) == {
        "dataset:dataset-001",
        "run:preprocessing:preprocess-001",
        "run:epoch:epoch-001",
        "run:erp:erp-001",
        "comparison:erp-001:comparison_summary",
    }
    assert edges == [
        (
            "dataset:dataset-001",
            "run:preprocessing:preprocess-001",
            "produced",
        ),
        (
            "run:preprocessing:preprocess-001",
            "run:epoch:epoch-001",
            "derived_from",
        ),
        ("run:epoch:epoch-001", "run:erp:erp-001", "derived_from"),
        (
            "run:erp:erp-001",
            "comparison:erp-001:comparison_summary",
            "compares",
        ),
    ]


def test_reproducibility_graph_fixture_contains_rerun_inputs():
    graph = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    nodes = {node["node_id"]: node for node in graph["nodes"]}

    for node_id in [
        "run:preprocessing:preprocess-001",
        "run:epoch:epoch-001",
        "run:erp:erp-001",
    ]:
        node = nodes[node_id]
        assert node["status"] == "completed"
        assert node["config_snapshot"]
        assert node["config_digest_sha256"].startswith("sha256:")
        assert len(node["config_digest_sha256"]) == len("sha256:") + 64
        assert node["artifact_manifest"]["path"].endswith("artifact_manifest.json")
        assert node["artifacts"]
        assert node["worker"]["schema_version"] == 1
        assert node["worker"]["exit_code"] == 0
        assert node["provenance"]["schema_version"] == 1

    dataset_node = nodes["dataset:dataset-001"]
    assert dataset_node["phase_d"]["recording_source_files"][0]["role"] == "eeg"
    assert dataset_node["phase_d"]["sidecar_discovery"]["candidates"][0][
        "sidecar_type"
    ] == "eeg_json"
    assert dataset_node["phase_d"]["event_provenance"]["sources"][0]["role"] == (
        "event_file"
    )


def test_reproducibility_graph_fixture_covers_batch_and_statistics_context():
    graph = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    nodes = {node["node_id"]: node for node in graph["nodes"]}

    preprocessing = nodes["run:preprocessing:preprocess-001"]
    comparison = nodes["comparison:erp-001:comparison_summary"]

    assert preprocessing["batch"] == {
        "batch_id": "batch-001",
        "batch_item_id": "batch-001-item-001",
        "template_id": "template-001",
        "template_digest_sha256": (
            "sha256:2222222222222222222222222222222222222222222222222222222222222222"
        ),
        "attempt": 1,
    }
    assert comparison["metric"] == "mean_amplitude_uv"
    assert comparison["condition_pair"] == {"a": "target", "b": "standard"}
    assert comparison["statistics"]["status"] == "implemented"
    assert comparison["statistics"]["method"] == "paired_t_test"
    assert comparison["statistics"]["result"]["p_value"] == 0.067


def test_reproducibility_graph_diagnostics_use_phase_d_taxonomy():
    graph = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    allowed_sources = {source.value for source in DiagnosticWarningSource}

    warnings = [
        *graph["diagnostics"]["warnings"],
        *[
            warning
            for node in graph["nodes"]
            for warning in node["diagnostics"]["warnings"]
        ],
    ]
    for warning in warnings:
        assert set(warning) == {
            "code",
            "severity",
            "source",
            "impact",
            "suggested_action",
        }
        assert warning["severity"] in {"warning", "error"}
        assert warning["source"] in allowed_sources


def test_reproducibility_graph_doc_references_schema_and_fixture():
    text = DOC_PATH.read_text(encoding="utf-8")

    assert "docs/schemas/reproducibility-graph.schema.json" in text
    assert (
        "tests/fixtures/reproducibility/reproducibility_graph_erp_comparison_v1.json"
        in text
    )
    assert "dataset -> preprocessing -> epoch -> ERP -> comparison" in text
