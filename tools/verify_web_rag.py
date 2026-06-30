#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path("/Users/hao/Documents/自助报销Agent")
BASE_URL = "http://127.0.0.1:8765"


def server_ready() -> bool:
    try:
        with urllib.request.urlopen(BASE_URL, timeout=2) as response:
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
        query = urllib.parse.urlencode({"q": "版面费 报销 需要什么材料"})
        errors: list[str] = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1360, "height": 900})
            page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
            page.goto(f"{BASE_URL}/?{query}", wait_until="networkidle")
            page.get_by_text("检索式答复").wait_for(timeout=10000)
            page.get_by_text("版面费、出版费报销指南").first.wait_for(timeout=10000)
            page.get_by_text("财务处").first.wait_for(timeout=10000)
            browser.close()
        if errors:
            raise AssertionError(f"Web RAG console errors: {errors}")
        print(json.dumps({"ok": True, "query": "版面费 报销 需要什么材料"}, ensure_ascii=False, indent=2))
    finally:
        if server is not None:
            server.terminate()
            server.wait(timeout=5)


if __name__ == "__main__":
    main()
