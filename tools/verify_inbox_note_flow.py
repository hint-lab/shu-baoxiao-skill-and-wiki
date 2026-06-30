#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path("/Users/hao/Documents/自助报销Agent")
BASE_URL = "http://127.0.0.1:8765"
TITLE = f"随手记验证差旅事项-{int(time.time())}"
NOTE = "这张票是 6 月去北京参加高校人工智能会议，后面再补高铁票、酒店发票和会议通知。"
DB_PATH = ROOT / "data/app.db"


def server_ready() -> bool:
    try:
        with urllib.request.urlopen(BASE_URL, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def inbox_row() -> tuple[str, str, str] | None:
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute(
            """
            SELECT id, status, linked_package_id
            FROM inbox_items
            WHERE title = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (TITLE,),
        ).fetchone()


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

    errors: list[str] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1360, "height": 920})
            page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
            page.goto(f"{BASE_URL}/#collection", wait_until="networkidle")
            page.get_by_label("事项名称").fill(TITLE)
            page.get_by_label("随手备注").fill(NOTE)
            page.get_by_role("button", name="存入资料归集").click()
            page.get_by_text(TITLE).wait_for(timeout=10000)
            page.get_by_text("未归类").first.wait_for(timeout=10000)
            page.locator(".ant-list-item").filter(has_text=TITLE).first.get_by_role("button", name="生成报销包").click()
            page.get_by_text("报销状态", exact=True).wait_for(timeout=15000)
            page.get_by_text("待补材料").first.wait_for(timeout=10000)
            browser.close()
        if errors:
            raise AssertionError(f"Frontend console errors: {errors}")
        row = inbox_row()
        if not row:
            raise AssertionError("Expected saved inbox note")
        item_id, status, package_id = row
        package_json = ROOT / "output/packages" / package_id / "package.json"
        if status != "packaged" or not package_id or not package_json.exists():
            raise AssertionError(f"Expected packaged inbox note, got id={item_id}, status={status}, package={package_id}")
        package = json.loads(package_json.read_text(encoding="utf-8"))
        if package["reimbursement_type"] != "domestic_travel":
            raise AssertionError(f"Expected domestic_travel package, got {package['reimbursement_type']}")
        print(json.dumps({"ok": True, "inbox": item_id, "package": package_id, "type": package["reimbursement_type"]}, ensure_ascii=False, indent=2))
    finally:
        if server is not None:
            server.terminate()
            server.wait(timeout=5)


if __name__ == "__main__":
    main()
