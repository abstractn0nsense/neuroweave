from pathlib import Path

import pytest

from eeg_io.bids_sidecars import (
    BidsChannel,
    BidsEegSidecar,
    BidsSidecarError,
    bids_basename_from_path,
    discover_bids_sidecars,
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


def test_bids_basename_from_eeg_and_events_paths():
    assert (
        bids_basename_from_path(Path("sub-001_task-oddball_eeg.set"))
        == "sub-001_task-oddball"
    )
    assert (
        bids_basename_from_path(Path("sub-001_task-oddball_events.tsv"))
        == "sub-001_task-oddball"
    )


def test_discover_bids_sidecars_finds_known_adjacent_files(tmp_path):
    reference = tmp_path / "sub-001_task-oddball_eeg.fif"
    reference.write_bytes(b"placeholder")
    (tmp_path / "sub-001_task-oddball_eeg.json").write_text(
        '{"PowerLineFrequency": 60, "EEGReference": "Cz"}',
        encoding="utf-8",
    )
    (tmp_path / "sub-001_task-oddball_channels.tsv").write_text(
        "name\ttype\tunits\tstatus\nFp1\tEEG\tuV\tgood\n",
        encoding="utf-8",
    )
    (tmp_path / "sub-001_task-oddball_events.tsv").write_text(
        "onset\tduration\ttrial_type\n1.0\t0.1\ttarget\n",
        encoding="utf-8",
    )
    (tmp_path / "sub-001_task-oddball_electrodes.tsv").write_text(
        "name\tx\ty\tz\nFp1\t0\t0\t0\n",
        encoding="utf-8",
    )

    discovery = discover_bids_sidecars(reference)

    assert discovery.bids_basename == "sub-001_task-oddball"
    assert discovery.diagnostics == []
    assert {
        candidate.sidecar_type: candidate.status
        for candidate in discovery.candidates
    } == {
        "eeg_json": "valid",
        "channels_tsv": "valid",
        "events_tsv": "valid",
        "electrodes_tsv": "discovered",
    }


def test_discover_bids_sidecars_returns_empty_result_without_sidecars(tmp_path):
    reference = tmp_path / "sample_resting_raw.fif"
    reference.write_bytes(b"placeholder")

    discovery = discover_bids_sidecars(reference)

    assert discovery.bids_basename == "sample_resting_raw"
    assert discovery.candidates == []
    assert discovery.diagnostics == []


def test_discover_bids_sidecars_records_invalid_sidecar_diagnostics(tmp_path):
    reference = tmp_path / "sub-001_task-rest_eeg.fif"
    reference.write_bytes(b"placeholder")
    (tmp_path / "sub-001_task-rest_eeg.json").write_text(
        '{"PowerLineFrequency": "sixty"}',
        encoding="utf-8",
    )

    discovery = discover_bids_sidecars(reference)

    assert len(discovery.candidates) == 1
    assert discovery.candidates[0].status == "invalid"
    assert discovery.diagnostics[0].code == "bids_sidecar_invalid"
    assert discovery.diagnostics[0].source == "bids"
