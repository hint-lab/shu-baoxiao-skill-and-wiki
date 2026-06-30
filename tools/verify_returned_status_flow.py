#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright


ROOT = Path("/Users/hao/Documents/自助报销Agent")
BASE_URL = "http://127.0.0.1:8767"
DB_PATH = ROOT / "data/app.db"
STAMP = int(time.time())
MANUAL_TITLE = f"退回状态办公用品包-{STAMP}"
DIAGNOSIS_TITLE = f"退回诊断办公用品包-{STAMP}"


def server_ready() -> bool:
    try:
        with urllib.request.urlopen(BASE_URL, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def build_package(title: str) -> None:
    subprocess.run(
        [
            sys.executable,
            "tools/build_reimbursement_package.py",
            "samples/office_supplies",
            "--title",
            title,
            "--note",
            "办公用品发票、清单和支付记录齐全，等待学校系统状态回写。",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def db_status(package_id: str) -> str:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT status FROM package_status WHERE package_id = ?", (package_id,)).fetchone()
    return row[0] if row else ""


def main() -> None:
    build_package(MANUAL_TITLE)
    build_package(DIAGNOSIS_TITLE)
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8767"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(30):
        if server_ready():
            break
        time.sleep(0.2)
    else:
        raise RuntimeError("Local server did not become ready on 127.0.0.1:8767")

    errors: list[str] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1360, "height": 920})
            page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)

            page.goto(f"{BASE_URL}/packages/{quote(MANUAL_TITLE)}/view", wait_until="networkidle")
            page.get_by_role("button", name="标记已退回").click()
            page.get_by_text("已退回").first.wait_for(timeout=10000)
            page.goto(f"{BASE_URL}/#waiting", wait_until="networkidle")
            page.get_by_role("tab", name=re.compile("退回待处理")).click()
            page.get_by_text(MANUAL_TITLE).wait_for(timeout=10000)

            page.goto(f"{BASE_URL}/packages/{quote(DIAGNOSIS_TITLE)}/view", wait_until="networkidle")
            page.get_by_label("财务系统退回意见").fill("请补充公务卡支付记录，并上传明细清单。")
            page.get_by_role("button", name="生成退回诊断").click()
            page.get_by_text("退回意见").wait_for(timeout=10000)
            browser.close()

        if errors:
            raise AssertionError(f"Frontend console errors: {errors}")
        manual_status = db_status(MANUAL_TITLE)
        diagnosis_status = db_status(DIAGNOSIS_TITLE)
        if manual_status != "returned" or diagnosis_status != "returned":
            raise AssertionError(f"Expected returned statuses, got manual={manual_status!r}, diagnosis={diagnosis_status!r}")
        print(
            json.dumps(
                {
                    "ok": True,
                    "manual_package": MANUAL_TITLE,
                    "diagnosis_package": DIAGNOSIS_TITLE,
                    "status": "returned",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        server.terminate()
        server.wait(timeout=5)


if __name__ == "__main__":
    main()
