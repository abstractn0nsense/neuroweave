from pathlib import Path

import pytest

from eeg_io.bids_sidecars import (
    BidsChannel,
    BidsEegSidecar,
    BidsSidecarError,
    read_channels_tsv,
    read_eeg_json,
)


FIXTURE_ROOT = Path("tests/fixtures/bids")


def test_read_channels_tsv_parses_bids_channel_metadata():
    channels = read_channels_tsv(
        FIXTURE_ROOT / "sub-001_task-oddball_channels.tsv"
    )

    assert channels == [
        BidsChannel(
            name="Fp1",
            type="EEG",
            units="uV",
            status="good",
            status_description=None,
        ),
        BidsChannel(
            name="Fp2",
            type="EEG",
            units="uV",
            status="bad",
            status_description="noisy electrode",
        ),
        BidsChannel(
            name="EOG1",
            type="EOG",
            units=None,
            status=None,
            status_description=None,
        ),
    ]


def test_read_eeg_json_parses_line_frequency_and_reference():
    sidecar = read_eeg_json(FIXTURE_ROOT / "sub-001_task-oddball_eeg.json")

    assert sidecar == BidsEegSidecar(
        line_frequency_hz=60.0,
        reference="Cz",
    )


def test_read_eeg_json_treats_na_and_empty_values_as_null(tmp_path):
    path = tmp_path / "sub-001_task-rest_eeg.json"
    path.write_text(
        '{"PowerLineFrequency": "n/a", "EEGReference": ""}',
        encoding="utf-8",
    )

    assert read_eeg_json(path) == BidsEegSidecar(
        line_frequency_hz=None,
        reference=None,
    )


def test_read_channels_tsv_requires_name_column(tmp_path):
    path = tmp_path / "sub-001_task-rest_channels.tsv"
    path.write_text("type\tunits\nEEG\tuV\n", encoding="utf-8")

    with pytest.raises(BidsSidecarError, match="required column: name"):
        read_channels_tsv(path)


def test_read_channels_tsv_requires_non_null_channel_name(tmp_path):
    path = tmp_path / "sub-001_task-rest_channels.tsv"
    path.write_text("name\ttype\nn/a\tEEG\n", encoding="utf-8")

    with pytest.raises(BidsSidecarError, match="missing required name"):
        read_channels_tsv(path)


def test_read_eeg_json_rejects_invalid_line_frequency(tmp_path):
    path = tmp_path / "sub-001_task-rest_eeg.json"
    path.write_text('{"PowerLineFrequency": "sixty"}', encoding="utf-8")

    with pytest.raises(BidsSidecarError, match="PowerLineFrequency"):
        read_eeg_json(path)
