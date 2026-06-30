#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import time
import urllib.request
from urllib.parse import quote
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path("/Users/hao/Documents/自助报销Agent")
BASE_URL = "http://127.0.0.1:8765"
TITLE = f"状态流办公用品报销包-{int(time.time())}"
PACKAGE_ID = TITLE
PACKAGE_URL_ID = quote(PACKAGE_ID)
DB_PATH = ROOT / "data/app.db"


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
            "状态流验证：办公用品发票、清单和支付记录齐全",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def db_status() -> str:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT status FROM package_status WHERE package_id = ?", (PACKAGE_ID,)).fetchone()
    return row[0] if row else ""


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

    errors: list[str] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1360, "height": 920})
            page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
            page.goto(f"{BASE_URL}/packages/{PACKAGE_URL_ID}/view", wait_until="networkidle")
            page.get_by_text("待本人复核").first.wait_for(timeout=10000)
            page.get_by_role("button", name="标记已报销").click()
            page.get_by_text("已报销").first.wait_for(timeout=10000)
            page.goto(f"{BASE_URL}/#reimbursed", wait_until="networkidle")
            page.locator("h2:has-text('已报销')").wait_for(timeout=10000)
            page.get_by_text(TITLE).wait_for(timeout=10000)
            browser.close()
        if errors:
            raise AssertionError(f"Frontend console errors: {errors}")
        status = db_status()
        if status != "reimbursed":
            raise AssertionError(f"Expected reimbursed status in SQLite, got {status!r}")
        print(json.dumps({"ok": True, "package": TITLE, "status": status}, ensure_ascii=False, indent=2))
    finally:
        if server is not None:
            server.terminate()
            server.wait(timeout=5)


if __name__ == "__main__":
    main()
