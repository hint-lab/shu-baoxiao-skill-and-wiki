#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path("/Users/hao/Documents/自助报销Agent")
EML = ROOT / "samples/emails/office_supplies_forward.eml"
PACKAGE_TITLE = "邮件导入验证办公用品报销包"
PACKAGE_DIR = ROOT / "output/packages" / PACKAGE_TITLE


def main() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "tools/ingest_eml.py",
            str(EML),
            "--title",
            PACKAGE_TITLE,
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    summary = json.loads(result.stdout)
    if summary["type"] != "办公用品/耗材报销":
        raise AssertionError(f"Unexpected type: {summary['type']}")
    if summary["missing_required"]:
        raise AssertionError(f"Expected no missing required items, got {summary['missing_required']}")
    docs = set(summary["documents"])
    expected = {"01-办公用品发票.txt", "02-销货清单.txt", "03-公务卡支付记录.txt"}
    if not expected.issubset(docs):
        raise AssertionError(f"Missing extracted attachments: expected {expected}, got {docs}")
    if not (PACKAGE_DIR / "package.json").exists():
        raise AssertionError("Package JSON was not exported")
    print(json.dumps({"ok": True, "package": str(PACKAGE_DIR), "documents": sorted(docs)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
