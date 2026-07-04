#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


ROOT = Path("/Users/hao/Documents/自助报销Agent")
BASE_URL = "http://127.0.0.1:8765"
TMP_DIR = ROOT / "tmp" / "shu_finance_observer"


def server_ready() -> bool:
    try:
        with urllib.request.urlopen(BASE_URL, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def write_mock_form() -> Path:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    html = TMP_DIR / "daily_form.html"
    html.write_text(
        """<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>日常报销单</title></head>
<body>
  <main>
    <h1>日常报销单</h1>
    <label for="reason">报销事由</label>
    <textarea id="reason" placeholder="某某人报销某某事项某某费用"></textarea>
    <label for="note">情况说明</label>
    <textarea id="note" placeholder="请输入备注"></textarea>
    <button type="button">请选择预算项目</button>
    <button type="button">请选择票据</button>
    <button type="button">请选择附件</button>
    <button type="button">下一步</button>
  </main>
</body>
</html>
""",
        encoding="utf-8",
    )
    return html


def main() -> None:
    html = write_mock_form()
    report_path = TMP_DIR / "report.json"
    adapter_path = TMP_DIR / "adapter.json"
    subprocess.run(
        [
            sys.executable,
            "tools/shu_finance_observer.py",
            "--mock-file",
            str(html),
            "--out",
            str(report_path),
            "--adapter-out",
            str(adapter_path),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    adapter = json.loads(adapter_path.read_text(encoding="utf-8"))
    if report.get("status") != "form_ready" or report.get("control_count", 0) < 6:
        raise AssertionError(f"Unexpected observation report: {report}")
    fields = adapter.get("fields", {})
    if "reason_short" not in fields or "note_short" not in fields:
        raise AssertionError(f"Expected reason and note fields in adapter draft: {adapter}")
    if adapter.get("ready_for_school_fill") is not False or not adapter.get("draft_only"):
        raise AssertionError(f"Adapter draft must not be executable by default: {adapter}")
    if len(adapter.get("manual_actions", [])) < 3:
        raise AssertionError(f"Expected manual pause points, got {adapter.get('manual_actions')}")

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
        request = urllib.request.Request(f"{BASE_URL}/api/shu-finance/observe?dry_run=true", data=b"", method="POST")
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not payload.get("ok") or not payload.get("dry_run"):
            raise AssertionError(f"Unexpected dry-run observe response: {payload}")
    finally:
        if server is not None:
            server.terminate()
            server.wait(timeout=5)

    print(
        json.dumps(
            {
                "ok": True,
                "status": report["status"],
                "fields": sorted(fields.keys()),
                "manual_actions": len(adapter.get("manual_actions", [])),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
