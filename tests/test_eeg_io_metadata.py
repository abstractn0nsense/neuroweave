from pathlib import Path

import numpy as np

from eeg_io.datasets import find_eeg_file_by_id, list_eeg_files
from eeg_io.readers import read_eeg_metadata


def test_read_eeg_metadata_from_fif(tmp_path):
    import mne

    sample_path = tmp_path / "sample-001_raw.fif"
    channel_names = ["Fp1", "Fp2", "F3", "F4", "C3", "C4", "O1", "O2"]
    sampling_rate = 256
    data = np.zeros((len(channel_names), sampling_rate * 2))
    info = mne.create_info(channel_names, sfreq=sampling_rate, ch_types="eeg")
    raw = mne.io.RawArray(data, info)
    raw.save(sample_path, overwrite=True, verbose=False)

    metadata = read_eeg_metadata(sample_path, dataset_id="sample-001")

    assert metadata.dataset_id == "sample-001"
    assert metadata.file_format == "fif"
    assert metadata.channel_count == 8
    assert metadata.sampling_rate_hz == 256
    assert metadata.duration_seconds == 2
    assert metadata.channel_names == channel_names


def test_list_and_find_eeg_files(tmp_path):
    sample_path = tmp_path / "sample-001_raw.fif"
    sample_path.write_bytes(b"placeholder")
    (tmp_path / "notes.txt").write_text("not eeg")

    files = list_eeg_files(tmp_path)

    assert len(files) == 1
    assert files[0].dataset_id == "sample-001_raw"
    assert files[0].filename == "sample-001_raw.fif"
    assert files[0].file_format == "fif"
    assert find_eeg_file_by_id(tmp_path, "sample-001_raw") == files[0]


def test_committed_event_fixture_has_annotations():
    fixture_path = Path("tests/fixtures/eeg/sample_events_raw.fif")

    metadata = read_eeg_metadata(fixture_path, dataset_id="sample-events")
    raw = _read_fixture_raw(fixture_path)

    assert metadata.dataset_id == "sample-events"
    assert metadata.channel_count == 8
    assert len(raw.annotations) == 3
    assert list(raw.annotations.description) == [
        "stim/left",
        "stim/right",
        "response/button",
    ]


def _read_fixture_raw(path):
    import mne

    return mne.io.read_raw_fif(path, preload=False, verbose=False)
