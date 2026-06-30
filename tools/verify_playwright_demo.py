#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


ROOT = Path("/Users/hao/Documents/自助报销Agent")
REPORT = ROOT / "output/playwright/fill_demo_report.json"


def server_ready() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8765/mock-school", timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def main() -> None:
    server = None
    if not server_ready():
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8765"],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(30):
            if server_ready():
                break
            time.sleep(0.2)
        else:
            raise RuntimeError("Local server did not become ready on 127.0.0.1:8765")

    try:
        subprocess.run(
            [
                sys.executable,
                "tools/playwright_fill_adapter.py",
                "--plan",
                "output/packages/论文版面费报销包/playwright_plan.json",
                "--adapter",
                "data/adapters/mock_school.json",
                "--allow-auto-login",
                "--out",
                "output/playwright/fill_demo_report.json",
                "--screenshot",
                "output/playwright/fill_demo.png",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        if not report.get("verified_stop_before_submission"):
            raise AssertionError("Playwright demo did not stop before submission")
        if report["filled"]["entry"] != "日常报销":
            raise AssertionError("Unexpected recommended entry")
        if report["attachment_count"] != 3:
            raise AssertionError("Expected 3 queued attachments")
        print(json.dumps({"ok": True, "report": str(REPORT)}, ensure_ascii=False, indent=2))
    finally:
        if server is not None:
            server.terminate()
            server.wait(timeout=5)


if __name__ == "__main__":
    main()
