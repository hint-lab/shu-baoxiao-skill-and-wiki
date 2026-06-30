#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from urllib.parse import quote
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
    package_json = ROOT / "output/packages/结构化字段验证办公用品包/package.json"
    if not package_json.exists():
        subprocess.run(
            [
                sys.executable,
                "tools/build_reimbursement_package.py",
                "samples/office_supplies",
                "--title",
                "结构化字段验证办公用品包",
                "--note",
                "课题组日常办公购买打印纸、签字笔和文件夹",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

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
            page.goto(f"{BASE_URL}/?q=版面费%20报销%20需要什么材料", wait_until="networkidle")
            page.get_by_text("上海大学报销工作台").wait_for(timeout=10000)
            page.get_by_text("检索式答复").wait_for(timeout=10000)
            page.locator(".app-sider").get_by_text("主页").first.wait_for(timeout=10000)
            page.locator(".app-sider").get_by_text("报销知识库").first.wait_for(timeout=10000)
            page.locator(".app-sider").get_by_text("资料归集").first.wait_for(timeout=10000)
            page.locator(".app-sider").get_by_text("等待报销").first.wait_for(timeout=10000)
            page.locator(".app-sider").get_by_text("已报销").first.wait_for(timeout=10000)
            page.goto(f"{BASE_URL}/#waiting", wait_until="networkidle")
            page.locator("h2:has-text('等待报销')").wait_for(timeout=10000)
            page.goto(f"{BASE_URL}/#collection", wait_until="networkidle")
            page.locator("h2:has-text('资料归集')").wait_for(timeout=10000)
            page.goto(f"{BASE_URL}/packages/{quote('结构化字段验证办公用品包')}/view", wait_until="networkidle")
            page.locator(".app-sider").get_by_text("上海大学").first.wait_for(timeout=10000)
            page.get_by_text("材料识别").wait_for(timeout=10000)
            page.get_by_text("购买方 上海大学").wait_for(timeout=10000)
            browser.close()
        if errors:
            raise AssertionError(f"Frontend console errors: {errors}")
        print(json.dumps({"ok": True, "pages": 2}, ensure_ascii=False, indent=2))
    finally:
        if server is not None:
            server.terminate()
            server.wait(timeout=5)


if __name__ == "__main__":
    main()
