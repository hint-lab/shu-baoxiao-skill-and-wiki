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
TITLE = f"工作单项目确认验证-{int(time.time())}"


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


def post_confirmation() -> None:
    body = urllib.parse.urlencode(
        {
            "fund_context": "horizontal_research",
            "project": "HINT-验证项目",
            "balance_status": "sufficient",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{BASE_URL}/packages/{urllib.parse.quote(TITLE)}/project-confirmation",
        data=body,
        method="POST",
    )
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
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
        post_confirmation()
        plan_path = ROOT / "output/packages" / TITLE / "playwright_plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        fill = plan["school_fill"]
        blockers = fill["readiness"]["blockers"]
        if blockers != ["餐费、食品发票或内转单"]:
            raise AssertionError(f"Expected only invoice blocker after project confirmation, got {blockers}")
        if fill["project"]["status"] != "confirmed_by_user":
            raise AssertionError(f"Expected confirmed project, got {fill['project']}")
        if fill["project"]["balance_status"] != "confirmed_sufficient":
            raise AssertionError(f"Expected sufficient balance, got {fill['project']}")
        print(
            json.dumps(
                {
                    "ok": True,
                    "package": TITLE,
                    "project": fill["project"],
                    "blockers": blockers,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        if server is not None:
            server.terminate()
            server.wait(timeout=5)


if __name__ == "__main__":
    main()
