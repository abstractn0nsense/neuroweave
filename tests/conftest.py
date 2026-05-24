from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]

for package_src in (
    "packages/eeg-core/src",
    "packages/eeg-io/src",
    "packages/eeg-processing/src",
):
    sys.path.insert(0, str(REPO_ROOT / package_src))
