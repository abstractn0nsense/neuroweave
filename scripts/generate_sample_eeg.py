from __future__ import annotations

import argparse
from pathlib import Path

import mne
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "eeg"
LOCAL_SAMPLE_DIR = REPO_ROOT / "data" / "raw" / "samples"

CHANNEL_NAMES = ["Fp1", "Fp2", "F3", "F4", "C3", "C4", "O1", "O2"]
SAMPLING_RATE_HZ = 256


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate deterministic synthetic EEG samples for Phase 0."
    )
    parser.add_argument(
        "--fixtures-only",
        action="store_true",
        help="Only write committed test fixtures under tests/fixtures/eeg.",
    )
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Only write local app samples under data/raw/samples.",
    )
    args = parser.parse_args()

    targets: list[Path] = []
    if not args.local_only:
        targets.append(FIXTURE_DIR)
    if not args.fixtures_only:
        targets.append(LOCAL_SAMPLE_DIR)

    for target in targets:
        target.mkdir(parents=True, exist_ok=True)
        _write_resting_sample(target / "sample_resting_raw.fif")
        _write_event_sample(target / "sample_events_raw.fif")

    print("Generated EEG samples:")
    for target in targets:
        print(f"- {target}")


def _write_resting_sample(path: Path) -> None:
    raw = _make_raw(duration_seconds=4, include_events=False)
    raw.save(path, overwrite=True, verbose=False)


def _write_event_sample(path: Path) -> None:
    raw = _make_raw(duration_seconds=6, include_events=True)
    raw.save(path, overwrite=True, verbose=False)


def _make_raw(duration_seconds: int, include_events: bool) -> mne.io.RawArray:
    rng = np.random.default_rng(seed=42 if include_events else 7)
    sample_count = SAMPLING_RATE_HZ * duration_seconds
    times = np.arange(sample_count) / SAMPLING_RATE_HZ
    data = []

    for channel_index, _channel_name in enumerate(CHANNEL_NAMES):
        alpha = np.sin(2 * np.pi * (9 + channel_index * 0.2) * times)
        slow = 0.25 * np.sin(2 * np.pi * 1.5 * times + channel_index)
        noise = 0.03 * rng.standard_normal(sample_count)
        data.append(20e-6 * (alpha + slow + noise))

    info = mne.create_info(CHANNEL_NAMES, sfreq=SAMPLING_RATE_HZ, ch_types="eeg")
    info.set_montage("standard_1020", on_missing="ignore")
    raw = mne.io.RawArray(np.asarray(data), info, verbose=False)

    if include_events:
        raw.set_annotations(
            mne.Annotations(
                onset=[1.0, 2.5, 4.0],
                duration=[0.2, 0.2, 0.2],
                description=["stim/left", "stim/right", "response/button"],
            )
        )

    return raw


if __name__ == "__main__":
    main()
