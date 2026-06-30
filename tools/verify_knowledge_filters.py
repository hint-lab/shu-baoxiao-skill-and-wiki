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


def get_json(path: str) -> dict:
    with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


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
        status = get_json("/api/knowledge/status")
        if not status.get("index_exists"):
            raise AssertionError("Knowledge index should exist")
        for source in ["page", "attachment", "local_pdf"]:
            if source not in status.get("source_types", {}):
                raise AssertionError(f"Missing source type count: {source}")

        url = "/?" + urllib.parse.urlencode({"q": "报销 材料", "source_type": "local_pdf"})
        with urllib.request.urlopen(f"{BASE_URL}{url}", timeout=5) as response:
            html = response.read().decode("utf-8")
        marker = "window.__REIMBURSEMENT_DATA__ = "
        start = html.index(marker) + len(marker)
        end = html.index(";", start)
        data = json.loads(html[start:end])
        hits = data["rag_result"]["hits"]
        if not hits:
            raise AssertionError("Expected local_pdf hits")
        bad = [hit["source_type"] for hit in hits if hit["source_type"] != "local_pdf"]
        if bad:
            raise AssertionError(f"Expected only local_pdf hits, got {bad}")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1360, "height": 920})
            page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
            page.goto(f"{BASE_URL}/#knowledge", wait_until="networkidle")
            page.locator(".ant-statistic-title", has_text="索引片段").wait_for(timeout=10000)
            page.locator(".ant-statistic-title", has_text="财务处网页").wait_for(timeout=10000)
            page.locator(".ant-statistic-title", has_text="附件入口").wait_for(timeout=10000)
            page.locator(".ant-statistic-title", has_text="本地 PDF").wait_for(timeout=10000)
            browser.close()
        if errors:
            raise AssertionError(f"Frontend console errors: {errors}")
        print(json.dumps({"ok": True, "source_types": status["source_types"], "filtered_hits": len(hits)}, ensure_ascii=False, indent=2))
    finally:
        if server is not None:
            server.terminate()
            server.wait(timeout=5)


if __name__ == "__main__":
    main()
