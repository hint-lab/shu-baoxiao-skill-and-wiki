#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import time
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

    errors: list[str] = []
    try:
        with urllib.request.urlopen(f"{BASE_URL}/api/settings/status", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        raw = json.dumps(payload, ensure_ascii=False)
        forbidden = ["DOUBAO_API_KEY", "ARK_API_KEY", "REIMBURSEMENT_IMAP_PASSWORD", "app-password-or-token"]
        leaked = [item for item in forbidden if item in raw]
        if leaked:
            raise AssertionError(f"Settings status leaked sensitive keys: {leaked}")
        for key in ["doubao", "imap", "knowledge_base", "playwright"]:
            if key not in payload:
                raise AssertionError(f"Missing settings status section: {key}")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1360, "height": 920})
            page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
            page.goto(f"{BASE_URL}/#settings", wait_until="networkidle")
            page.locator("h2:has-text('设置')").wait_for(timeout=10000)
            main = page.locator("main")
            main.get_by_text("学校账号", exact=True).wait_for(timeout=10000)
            main.get_by_text("学校系统代填", exact=True).wait_for(timeout=10000)
            main.get_by_text("邮箱收票", exact=True).wait_for(timeout=10000)
            main.get_by_text("知识库问答", exact=True).wait_for(timeout=10000)
            main.get_by_text("本地资料库", exact=True).wait_for(timeout=10000)
            browser.close()
        if errors:
            raise AssertionError(f"Frontend console errors: {errors}")
        print(json.dumps({"ok": True, "sections": sorted(payload.keys())}, ensure_ascii=False, indent=2))
    finally:
        if server is not None:
            server.terminate()
            server.wait(timeout=5)


if __name__ == "__main__":
    main()
