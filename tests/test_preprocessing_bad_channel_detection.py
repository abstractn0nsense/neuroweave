import json

import mne
import numpy as np

from eeg_core.domain import BadChannelDetectionConfig, PreprocessingConfig
from eeg_processing.preprocessing import preprocess_raw_eeg


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
