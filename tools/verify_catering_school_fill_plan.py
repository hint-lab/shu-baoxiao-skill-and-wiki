#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path("/Users/hao/Documents/自助报销Agent")
INPUT_DIR = ROOT / "data/uploads/catering_reception_20260522"


def build(title: str, note: str) -> dict:
    subprocess.run(
        [
            sys.executable,
            "tools/build_reimbursement_package.py",
            str(INPUT_DIR),
            "--title",
            title,
            "--note",
            note,
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    plan_path = ROOT / "output/packages" / title / "playwright_plan.json"
    if not plan_path.exists():
        raise AssertionError(f"Missing playwright plan: {plan_path}")
    return json.loads(plan_path.read_text(encoding="utf-8"))


def main() -> None:
    suffix = int(time.time())
    base_note = "餐饮招待费，京悦南门涮肉（虹桥天街店）餐饮消费，金额736元"
    unknown = build(f"餐饮代填计划验证-未确认-{suffix}", base_note)
    unknown_fill = unknown["school_fill"]
    line = unknown_fill["expense_lines"][0]
    if line["amount"] != 736.0:
        raise AssertionError(f"Expected amount 736.0, got {line}")
    if "上海京北涮餐饮管理有限公司" not in line["merchant"]:
        raise AssertionError(f"Expected merchant from payment record, got {line}")
    if unknown_fill["invoice_state"]["status"] != "missing":
        raise AssertionError(f"Expected missing invoice state, got {unknown_fill['invoice_state']}")
    if unknown_fill["project"]["status"] != "needs_user_selection":
        raise AssertionError(f"Expected project selection blocker, got {unknown_fill['project']}")
    if unknown_fill["readiness"]["can_start_school_fill"]:
        raise AssertionError(f"School fill should not start while project/materials are incomplete: {unknown_fill['readiness']}")

    confirmed = build(
        f"餐饮代填计划验证-横向-{suffix}",
        f"{base_note}。确认报销这笔餐饮费，走横向科研经费，项目：HINT-真实项目，余额足够。",
    )
    confirmed_fill = confirmed["school_fill"]
    if confirmed_fill["official_reception"]["fund_context"] != "horizontal_research":
        raise AssertionError(f"Expected horizontal fund context, got {confirmed_fill['official_reception']}")
    if confirmed_fill["project"]["status"] != "confirmed_by_user":
        raise AssertionError(f"Expected confirmed project, got {confirmed_fill['project']}")
    if confirmed_fill["project"]["balance_status"] != "confirmed_sufficient":
        raise AssertionError(f"Expected sufficient balance confirmation, got {confirmed_fill['project']}")
    blockers = confirmed_fill["readiness"]["blockers"]
    if blockers != ["餐费、食品发票或内转单"]:
        raise AssertionError(f"Expected only invoice blocker after horizontal confirmation, got {blockers}")

    print(
        json.dumps(
            {
                "ok": True,
                "unknown_project_status": unknown_fill["project"]["status"],
                "confirmed_project_status": confirmed_fill["project"]["status"],
                "confirmed_blockers": blockers,
                "line": {
                    "amount": line["amount"],
                    "merchant": line["merchant"],
                    "transaction_no": line["transaction_no"],
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
