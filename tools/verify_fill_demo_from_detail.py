#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright


ROOT = Path("/Users/hao/Documents/自助报销Agent")
BASE_URL = "http://127.0.0.1:8765"
TITLE = f"详情页代填演示办公用品包-{int(time.time())}"
PACKAGE_URL_ID = quote(TITLE)
REPORT = ROOT / "output/playwright" / f"{TITLE}-fill_report.json"


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
            "详情页代填演示验证：办公用品发票、清单和支付记录齐全",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


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
            page = browser.new_page(viewport={"width": 1360, "height": 940})
            page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
            page.goto(f"{BASE_URL}/packages/{PACKAGE_URL_ID}/view", wait_until="networkidle")
            page.get_by_text("受控代填 Agent").wait_for(timeout=10000)
            page.get_by_text("待本人复核").first.wait_for(timeout=10000)
            if not page.get_by_role("button", name="启动本地代填演示").is_disabled():
                raise AssertionError("Fill demo button should be disabled before ready_for_school")
            if not page.get_by_role("button", name="确认可代填").is_disabled():
                raise AssertionError("Ready-for-school button should require responsibility confirmations")
            for label in [
                "经费项目已经本人确认",
                "收款账号或对公账户已经本人确认",
                "票据和附件真实、合法、与业务相关",
                "我知道 Agent 不会自动提交学校系统",
                "进入学校系统后提交前仍由本人最终复核",
            ]:
                page.get_by_text(label).click()
            page.get_by_role("button", name="确认可代填").click()
            page.get_by_text("等待代填").first.wait_for(timeout=10000)
            page.get_by_role("button", name="启动本地代填演示").click()
            page.get_by_text("最近一次演示已停在提交前").wait_for(timeout=30000)
            browser.close()
        if errors:
            raise AssertionError(f"Frontend console errors: {errors}")
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        if not report.get("verified_stop_before_submission"):
            raise AssertionError("Fill demo did not stop before submission")
        if report.get("pause_count", 0) < 6:
            raise AssertionError(f"Expected pause points in report, got {report.get('pause_count')}")
        print(json.dumps({"ok": True, "package": TITLE, "report": str(REPORT)}, ensure_ascii=False, indent=2))
    finally:
        if server is not None:
            server.terminate()
            server.wait(timeout=5)


if __name__ == "__main__":
    main()
