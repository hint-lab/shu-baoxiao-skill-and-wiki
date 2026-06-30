#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path("/Users/hao/Documents/自助报销Agent")
BASE_URL = "http://127.0.0.1:8766"


def server_ready() -> bool:
    try:
        with urllib.request.urlopen(BASE_URL, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def post_poll() -> tuple[int, dict]:
    body = urllib.parse.urlencode({"limit": "10"}).encode()
    request = urllib.request.Request(f"{BASE_URL}/api/mail/poll", data=body, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


def main() -> None:
    env = os.environ.copy()
    for key in ["REIMBURSEMENT_IMAP_HOST", "REIMBURSEMENT_IMAP_USERNAME", "REIMBURSEMENT_IMAP_PASSWORD"]:
        env.pop(key, None)
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8766"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(40):
            if server_ready():
                break
            time.sleep(0.2)
        else:
            raise RuntimeError("Local server did not become ready on 127.0.0.1:8766")

        status_code, payload = post_poll()
        if status_code != 400 or payload.get("ok") is not False:
            raise AssertionError(f"Expected safe 400 for missing IMAP config, got {status_code}: {payload}")
        if "password" not in payload.get("missing", {}):
            raise AssertionError(f"Expected missing config flags without secrets, got {payload}")

        errors: list[str] = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1360, "height": 920})
            page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
            page.goto(f"{BASE_URL}/#settings", wait_until="networkidle")
            page.locator("h2:has-text('设置')").wait_for(timeout=10000)
            page.get_by_text("邮箱归集").wait_for(timeout=10000)
            page.get_by_text("未配置完整").wait_for(timeout=10000)
            poll_button = page.get_by_role("button", name="立即拉取邮箱")
            poll_button.wait_for(timeout=10000)
            if poll_button.is_enabled():
                raise AssertionError("Mail poll button should be disabled when IMAP config is incomplete")
            browser.close()
        if errors:
            raise AssertionError(f"Frontend console errors: {errors}")
        print(json.dumps({"ok": True, "status_code": status_code, "button_disabled": True}, ensure_ascii=False, indent=2))
    finally:
        server.terminate()
        server.wait(timeout=5)


if __name__ == "__main__":
    main()
