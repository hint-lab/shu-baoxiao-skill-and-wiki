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
EML = ROOT / "samples/emails/office_supplies_forward.eml"
TITLE = "AntD前端上传验证办公用品包"
PACKAGE_JSON = ROOT / "output/packages" / TITLE / "package.json"


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
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1360, "height": 920})
            page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
            page.goto(BASE_URL, wait_until="networkidle")
            page.get_by_label("报销事项名称").fill(TITLE)
            page.get_by_label("一句话备注").fill("AntD 前端上传 eml 邮件验证")
            page.locator('input[type="file"]').first.set_input_files(str(EML))
            page.get_by_role("button", name="生成报销包").click()
            page.get_by_text("材料识别").wait_for(timeout=20000)
            page.get_by_text("邮件正文.txt").wait_for(timeout=20000)
            browser.close()
        if errors:
            raise AssertionError(f"Frontend upload console errors: {errors}")
        package = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
        docs = {doc["file_name"] for doc in package["documents"]}
        expected = {"01-办公用品发票.txt", "02-销货清单.txt", "03-公务卡支付记录.txt", "邮件正文.txt"}
        if not expected.issubset(docs):
            raise AssertionError(f"Missing uploaded email materials: expected {expected}, got {docs}")
        print(json.dumps({"ok": True, "package": str(PACKAGE_JSON.parent)}, ensure_ascii=False, indent=2))
    finally:
        if server is not None:
            server.terminate()
            server.wait(timeout=5)


if __name__ == "__main__":
    main()
