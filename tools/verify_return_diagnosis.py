#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path("/Users/hao/Documents/自助报销Agent")


CASES = [
    {
        "package": "办公用品报销包",
        "reason": "请补充公务卡支付记录或银行付款记录，并确认办公用品明细清单包含品名、单价、数量。",
        "expected_checklist": {"payment_record", "detail_list"},
    },
    {
        "package": "北京会议差旅报销包",
        "reason": "退回：缺少国内出差审批单和国内差旅费结算单，请补充后重新提交。",
        "expected_checklist": {"travel_approval", "travel_settlement"},
    },
    {
        "package": "论文版面费报销包",
        "reason": "外币版面费请补充版面费报销说明和付款记录。",
        "expected_checklist": {"publication_explanation", "payment_record"},
    },
]


def main() -> None:
    for case in CASES:
        result = subprocess.run(
            [
                sys.executable,
                "tools/diagnose_return.py",
                case["package"],
                "--reason",
                case["reason"],
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        diagnosis = json.loads(result.stdout)
        got = {item["checklist_id"] for item in diagnosis["matched_items"]}
        if not case["expected_checklist"].issubset(got):
            raise AssertionError(f"{case['package']}: expected {case['expected_checklist']}, got {got}")
    print(json.dumps({"ok": True, "cases": len(CASES)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
