#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path("/Users/hao/Documents/自助报销Agent")
BASE_URL = "http://127.0.0.1:8765"
INPUT_DIR = ROOT / "data/uploads/catering_reception_20260522"
TITLE = f"餐饮聊天流程-{int(time.time())}"


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
            str(INPUT_DIR),
            "--title",
            TITLE,
            "--note",
            "餐饮招待费，京悦南门涮肉餐饮消费，金额736元",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def post_assistant(note: str, history: list[dict[str, str]]) -> dict:
    body = urllib.parse.urlencode(
        {
            "note": note,
            "history": json.dumps(history, ensure_ascii=False),
        }
    ).encode("utf-8")
    request = urllib.request.Request(f"{BASE_URL}/api/home/assistant", data=body, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


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
    try:
        history = [
            {
                "role": "assistant",
                "text": f"我识别这笔是餐饮接待/工作用餐类报销。我已经先建好工作单：{TITLE}。",
            }
        ]
        confirm = post_assistant("确认报销这笔餐饮费。", history)
        if confirm.get("action") != "catering_reimbursement_confirmed":
            raise AssertionError(f"Expected catering confirmation action, got {confirm}")
        project = post_assistant("帮我报，走横向科研经费，项目：HINT-聊天验证，余额足够。", history)
        if project.get("action") != "project_confirmation":
            raise AssertionError(f"Expected project confirmation before school flow, got {project}")
        if project.get("package", {}).get("missing_count") != 1:
            raise AssertionError(f"Expected only invoice missing after project confirmation, got {project}")
        print(
            json.dumps(
                {
                    "ok": True,
                    "package": TITLE,
                    "confirm_action": confirm.get("action"),
                    "project_action": project.get("action"),
                    "missing_count": project.get("package", {}).get("missing_count"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        if server is not None:
            server.terminate()
            server.wait(timeout=5)


if __name__ == "__main__":
    main()
