from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request


HEALTH_URL = "http://127.0.0.1:8765/api/settings/status"


def server_is_ready() -> bool:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=0.7) as response:
            return 200 <= response.status < 500
    except (OSError, urllib.error.URLError):
        return False


def main() -> int:
    if server_is_ready():
        print("FastAPI reimbursement service is already running on 127.0.0.1:8765")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return 0

    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8765",
        ],
        env=env,
    )
    try:
        return process.wait()
    except KeyboardInterrupt:
        process.terminate()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
