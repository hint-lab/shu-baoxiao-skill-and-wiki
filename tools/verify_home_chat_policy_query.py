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
DB_PATH = ROOT / "data/app.db"
QUESTION = "版面费报销需要哪些材料？"


def server_ready() -> bool:
    try:
        with urllib.request.urlopen(BASE_URL, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def inbox_count() -> int:
    if not DB_PATH.exists():
        return 0
    with sqlite3.connect(DB_PATH) as conn:
        try:
            row = conn.execute("SELECT COUNT(*) FROM inbox_items").fetchone()
        except sqlite3.OperationalError:
            return 0
    return int(row[0])


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
    before = inbox_count()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1360, "height": 920})
            page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
            page.goto(BASE_URL, wait_until="networkidle")
            page.get_by_label("报销助手").fill(QUESTION)
            page.get_by_role("button", name="查询依据").click()
            page.locator("h2:has-text('报销知识库')").wait_for(timeout=10000)
            page.get_by_text("检索式答复").wait_for(timeout=10000)
            browser.close()
        if errors:
            raise AssertionError(f"Frontend console errors: {errors}")
        after = inbox_count()
        if after != before:
            raise AssertionError(f"Policy question should not create inbox item: before={before}, after={after}")
        print(json.dumps({"ok": True, "question": QUESTION, "inbox_count": after}, ensure_ascii=False, indent=2))
    finally:
        if server is not None:
            server.terminate()
            server.wait(timeout=5)


if __name__ == "__main__":
    main()
