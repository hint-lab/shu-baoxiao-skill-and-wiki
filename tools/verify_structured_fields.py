#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path("/Users/hao/Documents/自助报销Agent")


def build_package(input_dir: str, title: str, note: str) -> dict:
    subprocess.run(
        [
            sys.executable,
            "tools/build_reimbursement_package.py",
            input_dir,
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
    package_path = ROOT / "output/packages" / title / "package.json"
    if not package_path.exists():
        raise AssertionError(f"Missing package output: {package_path}")
    return json.loads(package_path.read_text(encoding="utf-8"))


def invoice_doc(package: dict) -> dict:
    invoices = [doc for doc in package["documents"] if doc["document_type"] == "invoice"]
    if not invoices:
        raise AssertionError("Expected at least one invoice document")
    return invoices[0]


def main() -> None:
    normal = build_package(
        "samples/office_supplies",
        "结构化字段验证办公用品包",
        "课题组日常办公购买打印纸、签字笔和文件夹",
    )
    fields = invoice_doc(normal)["extracted_fields"]
    expected = {
        "buyer_name": "上海大学",
        "seller_name": "上海某办公用品有限公司",
        "item_name": "办公用品",
        "invoice_no": "98765432101234567890",
        "invoice_date": "2026-06-15",
        "amount_total": 420.0,
        "title_valid": True,
    }
    for key, value in expected.items():
        if fields.get(key) != value:
            raise AssertionError(f"Expected {key}={value!r}, got {fields.get(key)!r}")

    wrong_title = build_package(
        "data/test_inputs/office_supplies_wrong_title",
        "结构化字段验证错误抬头包",
        "课题组日常办公购买打印纸、签字笔和文件夹",
    )
    wrong_fields = invoice_doc(wrong_title)["extracted_fields"]
    if wrong_fields.get("title_valid") is not False:
        raise AssertionError("Expected wrong title invoice to be marked invalid")
    if not any("发票抬头可能不是上海大学" in flag for flag in wrong_title["risk_flags"]):
        raise AssertionError("Expected title risk flag for wrong title invoice")

    print(json.dumps({"ok": True, "normal_fields": fields, "wrong_title_flags": wrong_title["risk_flags"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
