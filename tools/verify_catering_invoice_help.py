#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import app


PACKAGE_TITLE = "餐饮招待费报销包-京悦南门涮肉-20260522"


def main() -> None:
    history = json.dumps(
        [
            {
                "role": "assistant",
                "text": f"我已经先建好工作单：{PACKAGE_TITLE}。",
            }
        ],
        ensure_ascii=False,
    )
    payload, status_code = app.create_home_assistant_payload("", "没有发票，怎么补开发票？", [], history=history)
    if status_code != 200:
        raise AssertionError(f"Expected HTTP 200, got {status_code}: {payload}")
    if payload.get("action") != "invoice_help":
        raise AssertionError(f"Expected invoice_help action, got {payload.get('action')}: {payload}")
    message = str(payload.get("message") or "")
    for expected in ["上海大学", "1231000042502637XE", "736.00", "上海京北涮餐饮管理有限公司", "4200003034202605223103168150"]:
        if expected not in message:
            raise AssertionError(f"Missing {expected!r} in invoice help message: {message}")
    actions = payload.get("actions") if isinstance(payload.get("actions"), list) else []
    if not any(action.get("label") == "如何上传发票" for action in actions):
        raise AssertionError(f"Expected next-step invoice action, got {actions}")

    upload_payload, upload_status = app.create_home_assistant_payload("", "我已经拿到发票，怎么上传？", [], history=history)
    if upload_status != 200 or upload_payload.get("action") != "invoice_upload_prompt":
        raise AssertionError(f"Expected invoice upload prompt, got {upload_status}: {upload_payload}")

    blocked = app.school_flow_payload_for_package(app.load_package(PACKAGE_TITLE) or {}, "开始代填")
    if blocked.get("action") != "school_flow_blocked":
        raise AssertionError(f"Expected school_flow_blocked, got {blocked}")
    blocked_actions = blocked.get("actions") if isinstance(blocked.get("actions"), list) else []
    if not any(action.get("label") == "怎么补发票" for action in blocked_actions):
        raise AssertionError(f"Expected invoice help action on school block, got {blocked_actions}")

    print(
        json.dumps(
            {
                "ok": True,
                "action": payload.get("action"),
                "package": payload.get("package", {}).get("id"),
                "blocked_action": blocked.get("action"),
                "upload_action": upload_payload.get("action"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
