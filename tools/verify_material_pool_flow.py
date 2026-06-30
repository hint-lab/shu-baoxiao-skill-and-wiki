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
BASE_URL = "http://127.0.0.1:8769"
DB_PATH = ROOT / "data/app.db"
TITLE = f"材料池流程办公用品包-{int(time.time())}"
FILES = [
    ROOT / "samples/office_supplies/01-办公用品发票.txt",
    ROOT / "samples/office_supplies/02-销货清单.txt",
    ROOT / "samples/office_supplies/03-公务卡支付记录.txt",
]


def server_ready() -> bool:
    try:
        with urllib.request.urlopen(BASE_URL, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def material_row() -> tuple[str, str, str, int] | None:
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute(
            """
            SELECT id, status, linked_package_id, file_count
            FROM material_items
            WHERE title = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (TITLE,),
        ).fetchone()


def main() -> None:
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8769"],
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
            raise RuntimeError("Local server did not become ready on 127.0.0.1:8769")

        errors: list[str] = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1360, "height": 920})
            page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
            page.goto(f"{BASE_URL}/#collection", wait_until="networkidle")
            card = page.locator(".work-card", has_text="暂存未归类材料").first
            card.get_by_placeholder("例如：李老师差旅票据一组").fill(TITLE)
            card.get_by_placeholder("例如：这些票据可能是 6 月北京会议，后面再补会议通知。").fill("材料先暂存，不立即生成报销包。")
            card.locator('input[type="file"]').set_input_files([str(path) for path in FILES])
            card.get_by_role("button", name="暂存到资料归集").click()
            page.get_by_text(TITLE).wait_for(timeout=10000)
            page.get_by_text("未归类").first.wait_for(timeout=10000)
            pool_item = page.locator(".ant-list-item").filter(has_text=TITLE).first
            pool_item.get_by_role("button", name="生成报销包").click()
            page.get_by_text("材料识别").wait_for(timeout=15000)
            browser.close()
        if errors:
            raise AssertionError(f"Frontend console errors: {errors}")

        row = material_row()
        if not row:
            raise AssertionError("Expected saved material pool row")
        item_id, status, package_id, file_count = row
        package_json = ROOT / "output/packages" / package_id / "package.json"
        if status != "packaged" or not package_id or not package_json.exists():
            raise AssertionError(f"Expected packaged material item, got id={item_id}, status={status}, package={package_id}")
        if file_count != len(FILES):
            raise AssertionError(f"Expected {len(FILES)} stored files, got {file_count}")
        package = json.loads(package_json.read_text(encoding="utf-8"))
        if package["reimbursement_type"] != "office_supplies":
            raise AssertionError(f"Expected office_supplies package, got {package['reimbursement_type']}")
        print(json.dumps({"ok": True, "material": item_id, "package": package_id, "files": file_count}, ensure_ascii=False, indent=2))
    finally:
        server.terminate()
        server.wait(timeout=5)


if __name__ == "__main__":
    main()
