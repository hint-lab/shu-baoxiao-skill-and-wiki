#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path("/Users/hao/Documents/自助报销Agent")
STATE = ROOT / "data/mail_inbox/verify_state.json"
EML = ROOT / "samples/emails/office_supplies_forward.eml"


def run_once() -> dict:
    result = subprocess.run(
        [
            sys.executable,
            "tools/poll_imap.py",
            "--fixture-eml",
            str(EML),
            "--state",
            str(STATE),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def main() -> None:
    STATE.unlink(missing_ok=True)
    first = run_once()
    if first["count"] != 1:
        raise AssertionError(f"Expected first poll to process 1 message, got {first['count']}")
    item = first["processed"][0]
    if item["reimbursement_type"] != "办公用品/耗材报销":
        raise AssertionError(f"Unexpected reimbursement type: {item['reimbursement_type']}")
    if item["missing_required"]:
        raise AssertionError(f"Expected no missing required items, got {item['missing_required']}")
    second = run_once()
    if second["count"] != 0:
        raise AssertionError(f"Expected second poll to skip duplicate message, got {second['count']}")
    print(json.dumps({"ok": True, "first_count": first["count"], "second_count": second["count"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
