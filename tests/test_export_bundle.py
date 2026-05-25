import json
import zipfile

from eeg_io.export_bundle import EXPORT_BUNDLE_SCHEMA_VERSION, build_export_bundle


def test_build_export_bundle_collects_manifest_artifacts_report_and_figures(tmp_path):
    run_root = tmp_path / "run"
    run_root.mkdir()
    (run_root / "erp_metadata.json").write_text('{"condition_count": 1}\n')
    (run_root / "erp_config.json").write_text('{"plot_mode": "gfp"}\n')
    (run_root / "provenance.json").write_text('{"run_id": "erp-001"}\n')
    (run_root / "erp_standard.png").write_bytes(b"png")
    (run_root / "analysis_report.json").write_text('{"schema_version": 1}\n')
    manifest_path = run_root / "artifact_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_root": str(run_root),
                "artifact_count": 4,
                "artifacts": [
                    {
                        "logical_name": "erp_metadata",
                        "artifact_type": "diagnostic_json",
                        "path": str(run_root / "erp_metadata.json"),
                    },
                    {
                        "logical_name": "erp_config",
                        "artifact_type": "config_json",
                        "path": str(run_root / "erp_config.json"),
                    },
                    {
                        "logical_name": "provenance",
                        "artifact_type": "provenance_json",
                        "path": str(run_root / "provenance.json"),
                    },
                    {
                        "logical_name": "erp_standard_plot",
                        "artifact_type": "figure_png",
                        "path": str(run_root / "erp_standard.png"),
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = build_export_bundle(
        artifact_manifest_path=manifest_path,
        analysis_report_path=run_root / "analysis_report.json",
        output_zip_path=tmp_path / "export_bundle.zip",
    )

    assert result == {
        "schema_version": EXPORT_BUNDLE_SCHEMA_VERSION,
        "bundle_path": str((tmp_path / "export_bundle.zip").resolve()),
        "entry_count": 6,
        "diagnostics": {"warnings": []},
    }
    with zipfile.ZipFile(tmp_path / "export_bundle.zip") as bundle:
        assert sorted(bundle.namelist()) == [
            "analysis_report.json",
            "artifact_manifest.json",
            "configs/erp_config.json",
            "diagnostics/erp_metadata.json",
            "export_bundle_manifest.json",
            "figures/erp_standard_plot.png",
            "provenance/provenance.json",
        ]
        bundle_manifest = json.loads(
            bundle.read("export_bundle_manifest.json").decode("utf-8")
        )

    assert bundle_manifest["schema_version"] == EXPORT_BUNDLE_SCHEMA_VERSION
    assert bundle_manifest["analysis_report_included"] is True
    assert bundle_manifest["entry_count"] == 6
    assert bundle_manifest["diagnostics"] == {"warnings": []}
    assert {entry["archive_path"] for entry in bundle_manifest["entries"]} == {
        "artifact_manifest.json",
        "analysis_report.json",
        "configs/erp_config.json",
        "diagnostics/erp_metadata.json",
        "figures/erp_standard_plot.png",
        "provenance/provenance.json",
    }


def test_build_export_bundle_skips_missing_artifacts_with_structured_warning(tmp_path):
    run_root = tmp_path / "run"
    run_root.mkdir()
    (run_root / "erp_metadata.json").write_text('{"condition_count": 1}\n')
    manifest_path = run_root / "artifact_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_root": str(run_root),
                "artifact_count": 2,
                "artifacts": [
                    {
                        "logical_name": "erp_metadata",
                        "artifact_type": "diagnostic_json",
                        "path": str(run_root / "erp_metadata.json"),
                    },
                    {
                        "logical_name": "erp_standard_plot",
                        "artifact_type": "figure_png",
                        "path": str(run_root / "missing.png"),
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = build_export_bundle(
        artifact_manifest_path=manifest_path,
        output_zip_path=tmp_path / "export_bundle.zip",
    )

    assert result["entry_count"] == 2
    assert result["diagnostics"]["warnings"][0]["code"] == "artifact_missing"
    assert result["diagnostics"]["warnings"][0]["source"] == "export_bundle"
    assert "erp_standard_plot" in result["diagnostics"]["warnings"][0]["impact"]
    with zipfile.ZipFile(tmp_path / "export_bundle.zip") as bundle:
        assert sorted(bundle.namelist()) == [
            "artifact_manifest.json",
            "diagnostics/erp_metadata.json",
            "export_bundle_manifest.json",
        ]
        bundle_manifest = json.loads(
            bundle.read("export_bundle_manifest.json").decode("utf-8")
        )

    assert bundle_manifest["diagnostics"] == result["diagnostics"]


def test_build_export_bundle_warns_when_analysis_report_is_missing(tmp_path):
    run_root = tmp_path / "run"
    run_root.mkdir()
    manifest_path = run_root / "artifact_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_root": str(run_root),
                "artifact_count": 0,
                "artifacts": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = build_export_bundle(
        artifact_manifest_path=manifest_path,
        analysis_report_path=run_root / "analysis_report.json",
        output_zip_path=tmp_path / "export_bundle.zip",
    )

    assert result["entry_count"] == 1
    assert result["diagnostics"]["warnings"] == [
        {
            "code": "artifact_missing",
            "severity": "warning",
            "source": "export_bundle",
            "impact": (
                "Artifact 'analysis_report' was not included in the export bundle "
                f"because the file was not found: {run_root / 'analysis_report.json'}"
            ),
            "suggested_action": (
                "Regenerate the source run artifact or rebuild the artifact manifest."
            ),
        }
    ]
    with zipfile.ZipFile(tmp_path / "export_bundle.zip") as bundle:
        assert sorted(bundle.namelist()) == [
            "artifact_manifest.json",
            "export_bundle_manifest.json",
        ]
