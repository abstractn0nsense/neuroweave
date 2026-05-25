from eeg_io.provenance import PROVENANCE_SCHEMA_VERSION, build_provenance_payload


def test_build_provenance_payload_uses_common_shape():
    payload = build_provenance_payload(
        run_id="preprocess-001",
        dataset_id="dataset-001",
        run_kind="preprocessing",
        config_snapshot={"reference": "average"},
        sources=[
            {
                "role": "eeg_file",
                "file_id": "file-001",
                "path": "data/raw/uploads/sample.fif",
            }
        ],
        artifacts=[
            {
                "logical_name": "raw_preprocessed",
                "artifact_type": "primary_fif",
                "path": "data/processed/raw_preprocessed_raw.fif",
            }
        ],
        software_versions={"python": "3.13.0", "mne": "1.7.0"},
        created_at_utc="2026-05-26T00:00:00+00:00",
    )

    assert payload["schema_version"] == PROVENANCE_SCHEMA_VERSION
    assert payload["run"] == {
        "run_id": "preprocess-001",
        "dataset_id": "dataset-001",
        "run_kind": "preprocessing",
    }
    assert payload["sources"][0]["role"] == "eeg_file"
    assert payload["config_snapshot"] == {"reference": "average"}
    assert payload["software_versions"]["mne"] == "1.7.0"
    assert payload["artifacts"][0]["logical_name"] == "raw_preprocessed"
