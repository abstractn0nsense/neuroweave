from multiprocessing.queues import Queue
from pathlib import Path
from typing import Any

from eeg_core.domain import PreprocessingConfig
from eeg_processing.preprocessing import PreprocessingError, preprocess_raw_eeg


def run_preprocessing_job(
    input_path: str,
    output_path: str,
    config: PreprocessingConfig,
    result_queue: Queue,
) -> None:
    try:
        metadata = preprocess_raw_eeg(
            input_path=Path(input_path),
            output_path=Path(output_path),
            config=config,
        )
        result_queue.put({"status": "completed", "metadata": metadata})
    except PreprocessingError as exc:
        result_queue.put(
            {
                "status": "failed",
                "error": str(exc),
                "warnings": exc.processing_warnings,
            }
        )
    except BaseException as exc:
        result_queue.put(
            {
                "status": "failed",
                "error": f"Preprocessing subprocess failed: {exc}",
                "warnings": [],
            }
        )
