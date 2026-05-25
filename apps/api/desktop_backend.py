from __future__ import annotations

import os
import sys

import uvicorn


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "worker":
        from eeg_processing.worker_cli import main as worker_main

        return worker_main(sys.argv[2:])

    host = os.environ.get("NEUROWEAVE_API_HOST", "127.0.0.1")
    port = int(os.environ.get("NEUROWEAVE_API_PORT", "8000"))
    uvicorn.run("main:app", host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
