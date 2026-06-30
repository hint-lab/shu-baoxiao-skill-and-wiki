#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path("/Users/hao/Documents/自助报销Agent")
PACKAGE_NAME = "补材料验证办公用品包"
PACKAGE_DIR = ROOT / "output/packages" / PACKAGE_NAME
INPUT_DIR = ROOT / "data/test_inputs/office_supplies_missing_payment"
PAYMENT_FILE = ROOT / "samples/office_supplies/03-公务卡支付记录.txt"


def run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True)
    return result.stdout


def missing_items() -> list[str]:
    pkg = json.loads((PACKAGE_DIR / "package.json").read_text(encoding="utf-8"))
    return [item["name"] for item in pkg["checklist"] if item["status"] == "missing"]


def docs() -> list[str]:
    pkg = json.loads((PACKAGE_DIR / "package.json").read_text(encoding="utf-8"))
    return [doc["file_name"] for doc in pkg["documents"]]


def main() -> None:
    shutil.rmtree(PACKAGE_DIR, ignore_errors=True)
    run(
        [
            sys.executable,
            "tools/build_reimbursement_package.py",
            str(INPUT_DIR),
            "--note",
            "补材料验证：先上传办公用品发票和清单，不含支付记录",
            "--title",
            PACKAGE_NAME,
        ]
    )
    before = missing_items()
    if "支付记录" not in before:
        raise AssertionError(f"Expected 支付记录 missing before supplement, got {before}")

    run(
        [
            sys.executable,
            "tools/supplement_package.py",
            PACKAGE_NAME,
            str(PAYMENT_FILE),
            "--note",
            "根据退回意见补充公务卡支付记录",
        ]
    )
    after = missing_items()
    if after:
        raise AssertionError(f"Expected no missing items after supplement, got {after}")
    if "03-公务卡支付记录.txt" not in docs():
        raise AssertionError("Supplemented payment record not present in rebuilt package")
    versions = [p.name for p in (PACKAGE_DIR / "versions").iterdir() if p.is_dir()]
    if not versions:
        raise AssertionError("Expected archived previous version")
    files = sorted(p.name for p in (PACKAGE_DIR / "files").iterdir() if p.is_file())
    if len(files) != len(set(files)):
        raise AssertionError("Duplicate files found in rebuilt package")

    print(json.dumps({"ok": True, "before": before, "after": after, "versions": versions}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
