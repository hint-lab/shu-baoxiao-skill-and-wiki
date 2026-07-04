#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path("/Users/hao/Documents/自助报销Agent")
BASE_URL = "http://127.0.0.1:8765"
INPUT_DIR = ROOT / "data/uploads/catering_reception_20260522"
TITLE = f"学校代填门禁验证-{int(time.time())}"


def server_ready() -> bool:
    try:
        with urllib.request.urlopen(BASE_URL, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def build_package() -> None:
    subprocess.run(
        [
            sys.executable,
            "tools/build_reimbursement_package.py",
            str(INPUT_DIR),
            "--title",
            TITLE,
            "--note",
            "餐饮招待费，京悦南门涮肉餐饮消费，金额736元",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def post_school_fill() -> None:
    request = urllib.request.Request(
        f"{BASE_URL}/packages/{urllib.parse.quote(TITLE)}/school-fill",
        data=b"",
        method="POST",
    )
    urllib.request.urlopen(request, timeout=20).read()


def main() -> None:
    build_package()
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
        post_school_fill()
        report_path = ROOT / "output/playwright" / f"{TITLE}-school_fill_report.json"
        screenshot_path = ROOT / "output/playwright" / f"{TITLE}-school_fill.png"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report.get("status") != "blocked":
            raise AssertionError(f"Expected blocked report, got {report}")
        blockers = [item.get("message", "") for item in report.get("gate", {}).get("blockers", [])]
        joined = "\n".join(blockers)
        for expected in ["餐费、食品发票或内转单", "确认报销项目", "项目余额", "真实学校系统字段适配"]:
            if expected not in joined:
                raise AssertionError(f"Expected blocker {expected!r}, got {blockers}")
        if screenshot_path.exists():
            raise AssertionError(f"School fill should not open browser or create screenshot while blocked: {screenshot_path}")
        print(json.dumps({"ok": True, "package": TITLE, "blockers": blockers}, ensure_ascii=False, indent=2))
    finally:
        if server is not None:
            server.terminate()
            server.wait(timeout=5)


if __name__ == "__main__":
    main()
