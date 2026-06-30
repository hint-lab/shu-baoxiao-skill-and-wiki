#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path("/Users/hao/Documents/自助报销Agent")
BASE_URL = "http://127.0.0.1:8768"
TITLE = f"责任确认门禁办公用品包-{int(time.time())}"
DB_PATH = ROOT / "data/app.db"
CONFIRM_ITEMS = [
    "funding_project",
    "payment_account",
    "invoice_truth",
    "no_auto_submit",
    "review_before_submit",
]


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
            "samples/office_supplies",
            "--title",
            TITLE,
            "--note",
            "责任确认门禁验证：材料齐全但必须本人确认后才能代填",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def status() -> str:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT status FROM package_status WHERE package_id = ?", (TITLE,)).fetchone()
    return row[0] if row else ""


def post_status(fields: list[tuple[str, str]]) -> None:
    body = urllib.parse.urlencode(fields).encode("utf-8")
    request = urllib.request.Request(f"{BASE_URL}/packages/{urllib.parse.quote(TITLE)}/status", data=body, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler)
    opener.open(request, timeout=10).read()


def main() -> None:
    build_package()
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8768"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(30):
            if server_ready():
                break
            time.sleep(0.2)
        else:
            raise RuntimeError("Local server did not become ready on 127.0.0.1:8768")

        urllib.request.urlopen(f"{BASE_URL}/packages/{urllib.parse.quote(TITLE)}/view", timeout=10).read()
        initial = status()
        if initial != "ready_for_review":
            raise AssertionError(f"Expected initial ready_for_review, got {initial!r}")

        post_status([("status", "ready_for_school"), ("note", "伪造请求，未确认责任")])
        blocked = status()
        if blocked != "ready_for_review":
            raise AssertionError(f"Ready-for-school should be blocked without confirmations, got {blocked!r}")

        fields = [("status", "ready_for_school"), ("note", "本人确认可代填")]
        fields.extend(("confirm_items", item) for item in CONFIRM_ITEMS)
        post_status(fields)
        allowed = status()
        if allowed != "ready_for_school":
            raise AssertionError(f"Expected ready_for_school after full confirmations, got {allowed!r}")

        print(json.dumps({"ok": True, "package": TITLE, "blocked_status": blocked, "allowed_status": allowed}, ensure_ascii=False, indent=2))
    finally:
        server.terminate()
        server.wait(timeout=5)


if __name__ == "__main__":
    main()
