import json

import mne
import numpy as np

from eeg_core.domain import (
    ArtifactHandlingConfig,
    BadChannelDetectionConfig,
    BadChannelInterpolationConfig,
    IcaConfig,
    PreprocessingConfig,
)
from eeg_processing.preprocessing import preprocess_raw_eeg


def test_preprocessing_applies_manual_bad_channels_without_interpolation(tmp_path):
    input_path = tmp_path / "input_raw.fif"
    output_path = tmp_path / "output_raw.fif"
    sampling_rate = 100.0
    times = np.arange(0, 1, 1 / sampling_rate)
    data = np.vstack(
        [
            np.sin(2 * np.pi * 8 * times) * 1e-6,
            np.sin(2 * np.pi * 9 * times) * 1e-6,
        ]
    )
    raw = mne.io.RawArray(
        data,
        mne.create_info(["Fz", "Cz"], sampling_rate, ch_types="eeg"),
        verbose=False,
    )
    raw.save(input_path, overwrite=True, verbose=False)

    metadata = preprocess_raw_eeg(
        input_path,
        output_path,
        PreprocessingConfig(manual_bad_channels=["Cz"]),
    )

    output_raw = mne.io.read_raw_fif(output_path, preload=False, verbose=False)
    artifact_summary = metadata["diagnostics"]["artifact_summary"]
    assert output_raw.info["bads"] == ["Cz"]
    assert artifact_summary["input"]["bad_channels"] == []
    assert artifact_summary["output"]["bad_channels"] == ["Cz"]
    assert artifact_summary["bad_channels"]["manual"] == {
        "channels": ["Cz"],
        "applied_channels": ["Cz"],
        "status": "applied",
    }
    assert artifact_summary["bad_channels"]["interpolation"]["status"] == (
        "not_requested"
    )


def test_preprocessing_interpolates_manual_bad_channels(tmp_path):
    input_path = tmp_path / "input_raw.fif"
    output_path = tmp_path / "output_raw.fif"
    sampling_rate = 100.0
    times = np.arange(0, 1, 1 / sampling_rate)
    channel_names = ["Fp1", "Fp2", "Fz", "Cz", "Pz", "Oz"]
    data = np.vstack(
        [
            np.sin(2 * np.pi * (8 + index) * times) * 1e-6
            for index in range(len(channel_names))
        ]
    )
    raw = mne.io.RawArray(
        data,
        mne.create_info(channel_names, sampling_rate, ch_types="eeg"),
        verbose=False,
    )
    raw.set_montage("standard_1020", verbose=False)
    raw.save(input_path, overwrite=True, verbose=False)

    metadata = preprocess_raw_eeg(
        input_path,
        output_path,
        PreprocessingConfig(
            manual_bad_channels=["Cz"],
            bad_channel_interpolation=BadChannelInterpolationConfig(enabled=True),
        ),
    )

    output_raw = mne.io.read_raw_fif(output_path, preload=False, verbose=False)
    artifact_summary = metadata["diagnostics"]["artifact_summary"]
    before_after = artifact_summary["qc"]["before_after"]
    interpolation = artifact_summary["bad_channels"]["interpolation"]
    assert output_raw.info["bads"] == []
    assert artifact_summary["output"]["bad_channels"] == []
    assert artifact_summary["qc"]["status"] == "completed"
    assert before_after["before"]["channel_status"]["bad_channel_count"] == 0
    assert before_after["after"]["channel_status"]["bad_channel_count"] == 0
    assert before_after["delta"]["bad_channel_count"] == 0
    assert before_after["before"]["variance"]["mean_uv2"] is not None
    assert before_after["after"]["variance"]["mean_uv2"] is not None
    assert before_after["before"]["psd"]["total_power_uv2"] is not None
    assert before_after["after"]["psd"]["total_power_uv2"] is not None
    assert interpolation["status"] == "applied"
    assert interpolation["before"] == {
        "bad_channels": ["Cz"],
        "bad_channel_count": 1,
    }
    assert interpolation["after"] == {
        "bad_channels": [],
        "bad_channel_count": 0,
    }
    assert interpolation["interpolated_channels"] == ["Cz"]
    assert interpolation["reset_bads"] is True


def test_preprocessing_reports_flat_bad_channel_candidate(tmp_path):
    input_path = tmp_path / "input_raw.fif"
    output_path = tmp_path / "output_raw.fif"
    sampling_rate = 100.0
    times = np.arange(0, 2, 1 / sampling_rate)
    data = np.vstack(
        [
            np.sin(2 * np.pi * 8 * times) * 1e-6,
            np.sin(2 * np.pi * 9 * times) * 1e-6,
            np.zeros_like(times),
            np.sin(2 * np.pi * 10 * times) * 1e-6,
        ]
    )
    raw = mne.io.RawArray(
        data,
        mne.create_info(["Fz", "Cz", "Pz", "Oz"], sampling_rate, ch_types="eeg"),
        verbose=False,
    )
    raw.save(input_path, overwrite=True, verbose=False)

    metadata = preprocess_raw_eeg(
        input_path,
        output_path,
        PreprocessingConfig(
            bad_channel_detection=BadChannelDetectionConfig(
                enabled=True,
                method="flat",
            )
        ),
    )

    artifact_summary = metadata["diagnostics"]["artifact_summary"]
    detection = artifact_summary["bad_channels"]["detection"]
    assert output_path.is_file()
    output_raw = mne.io.read_raw_fif(output_path, preload=False, verbose=False)
    assert output_raw.info["bads"] == []
    assert detection["status"] == "completed"
    assert detection["candidate_count"] == 1
    assert detection["candidates"][0]["channel"] == "Pz"
    assert detection["candidates"][0]["reasons"] == ["flat"]
    assert detection["candidates"][0]["metrics"]["peak_to_peak_uv"] == 0.0


def test_preprocessing_reports_deviation_bad_channel_candidate(tmp_path):
    input_path = tmp_path / "input_raw.fif"
    output_path = tmp_path / "output_raw.fif"
    sampling_rate = 100.0
    times = np.arange(0, 2, 1 / sampling_rate)
    base = np.sin(2 * np.pi * 8 * times) * 1e-6
    data = np.vstack(
        [
            base,
            base * 1.1,
            base * 0.9,
            base * 25,
        ]
    )
    raw = mne.io.RawArray(
        data,
        mne.create_info(["Fz", "Cz", "Pz", "Oz"], sampling_rate, ch_types="eeg"),
        verbose=False,
    )
    raw.save(input_path, overwrite=True, verbose=False)

    metadata = preprocess_raw_eeg(
        input_path,
        output_path,
        PreprocessingConfig(
            bad_channel_detection=BadChannelDetectionConfig(
                enabled=True,
                method="deviation",
                zscore_threshold=1.0,
            )
        ),
    )

    candidates = metadata["diagnostics"]["artifact_summary"]["bad_channels"][
        "detection"
    ]["candidates"]
    channels = [candidate["channel"] for candidate in candidates]
    assert "Oz" in channels
    oz_candidate = candidates[channels.index("Oz")]
    assert oz_candidate["reasons"] == ["variance_deviation"]


def test_preprocessing_reports_eog_ecg_candidates_without_raw_mutation(tmp_path):
    input_path = tmp_path / "input_raw.fif"
    output_path = tmp_path / "output_raw.fif"
    sampling_rate = 100.0
    times = np.arange(0, 10, 1 / sampling_rate)
    eeg = np.sin(2 * np.pi * 8 * times) * 1e-6
    eog = np.zeros_like(times)
    ecg = np.zeros_like(times)
    eog[[200, 650]] = [150e-6, -140e-6]
    ecg[[120, 220, 320, 420, 520, 620, 720, 820]] = 90e-6
    raw = mne.io.RawArray(
        np.vstack([eeg, eog, ecg]),
        mne.create_info(
            ["Fz", "VEOG", "ECG"],
            sampling_rate,
            ch_types=["eeg", "eog", "ecg"],
        ),
        verbose=False,
    )
    raw.save(input_path, overwrite=True, verbose=False)

    metadata = preprocess_raw_eeg(
        input_path,
        output_path,
        PreprocessingConfig(
            artifact_handling=ArtifactHandlingConfig(
                eog_enabled=True,
                ecg_enabled=True,
            )
        ),
    )

    output_raw = mne.io.read_raw_fif(output_path, preload=False, verbose=False)
    artifact_rejection = metadata["diagnostics"]["artifact_summary"][
        "artifact_rejection"
    ]
    assert len(output_raw.annotations) == 0
    assert artifact_rejection["status"] == "completed"
    assert artifact_rejection["mode"] == "report_only"
    assert artifact_rejection["annotations_created"] is False
    assert artifact_rejection["eog"]["channel_source"] == "channel_type"
    assert artifact_rejection["eog"]["channels"] == ["VEOG"]
    assert artifact_rejection["eog"]["candidate_count"] >= 1
    assert artifact_rejection["eog"]["candidates"][0]["type"] == "blink"
    assert artifact_rejection["ecg"]["channel_source"] == "channel_type"
    assert artifact_rejection["ecg"]["channels"] == ["ECG"]
    assert artifact_rejection["ecg"]["candidate_count"] >= 1
    assert artifact_rejection["ecg"]["candidates"][0]["type"] == "heartbeat"


def test_preprocessing_fits_and_applies_ica_exclusions(tmp_path):
    input_path = tmp_path / "input_raw.fif"
    output_path = tmp_path / "output_raw.fif"
    sampling_rate = 100.0
    times = np.arange(0, 6, 1 / sampling_rate)
    source_a = np.sin(2 * np.pi * 8 * times) * 1e-6
    source_b = np.sign(np.sin(2 * np.pi * 2 * times)) * 0.5e-6
    data = np.vstack(
        [
            source_a + source_b,
            0.6 * source_a - source_b,
            -0.4 * source_a + 0.8 * source_b,
            0.3 * source_a + 0.2 * source_b,
        ]
    )
    raw = mne.io.RawArray(
        data,
        mne.create_info(["Fz", "Cz", "Pz", "Oz"], sampling_rate, ch_types="eeg"),
        verbose=False,
    )
    raw.save(input_path, overwrite=True, verbose=False)

    metadata = preprocess_raw_eeg(
        input_path,
        output_path,
        PreprocessingConfig(
            ica=IcaConfig(
                enabled=True,
                n_components=2,
                random_state=97,
                max_iter=200,
                exclude_components=[0],
            )
        ),
    )

    output_raw = mne.io.read_raw_fif(output_path, preload=True, verbose=False)
    ica = metadata["diagnostics"]["artifact_summary"]["ica"]
    assert ica["status"] == "applied"
    assert ica["component_count"] == 2
    assert ica["fit_channels"] == ["Fz", "Cz", "Pz", "Oz"]
    assert ica["excluded_components_requested"] == [0]
    assert ica["excluded_components_applied"] == [0]
    assert ica["apply_performed"] is True
    assert ica["component_metadata"][0]["excluded"] is True
    assert not np.allclose(output_raw.get_data(), data)


def test_preprocessing_report_is_json_serializable(tmp_path):
    input_path = tmp_path / "input_raw.fif"
    output_path = tmp_path / "output_raw.fif"
    raw = mne.io.RawArray(
        np.zeros((1, 10)),
        mne.create_info(["Fz"], 10.0, ch_types="eeg"),
        verbose=False,
    )
    raw.save(input_path, overwrite=True, verbose=False)

    metadata = preprocess_raw_eeg(
        input_path,
        output_path,
        PreprocessingConfig(
            bad_channel_detection=BadChannelDetectionConfig(
                enabled=True,
                method="flat",
            )
        ),
    )

    json.dumps(metadata["diagnostics"]["artifact_summary"])
