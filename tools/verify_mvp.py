#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path("/Users/hao/Documents/自助报销Agent")


CASES = [
    {
        "input": "samples/domestic_travel",
        "title": "北京会议差旅报销包",
        "note": "6 月去北京参加高校人工智能学术会议，报销高铁和酒店费用，走张老师科研项目",
        "expected_type": "国内差旅报销",
        "expected_missing": {"国内出差审批单", "国内差旅费结算单"},
    },
    {
        "input": "samples/publication_fee",
        "title": "论文版面费报销包",
        "note": "论文 A Study on Reimbursement Agents 版面费，外币 USD 600，由银行卡支付",
        "expected_type": "版面费/出版费",
        "expected_missing": set(),
    },
    {
        "input": "data/test_inputs/office_supplies_missing_payment",
        "title": "办公用品报销包",
        "note": "课题组日常办公购买打印纸、签字笔和文件夹",
        "expected_type": "办公用品/耗材报销",
        "expected_missing": {"支付记录"},
    },
    {
        "input": "samples/materials_fee",
        "title": "实验材料费报销包",
        "note": "课题组科研实验材料采购，报销离心管、吸头和培养皿等材料费",
        "expected_type": "材料费",
        "expected_missing": set(),
    },
    {
        "input": "samples/testing_processing_fee",
        "title": "测试化验加工费报销包",
        "note": "科研样品材料成分分析和显微结构观察测试化验加工费",
        "expected_type": "测试化验加工费",
        "expected_missing": set(),
    },
    {
        "input": "samples/official_reception",
        "title": "公务接待费报销包",
        "note": "合作高校教师来访开展科研合作交流，报销公务接待餐费",
        "expected_type": "公务接待费",
        "expected_missing": set(),
    },
    {
        "input": "samples/information_service_fee",
        "title": "信息服务费报销包",
        "note": "科研数据检索与数据接口服务，报销信息服务费",
        "expected_type": "信息服务费",
        "expected_missing": set(),
    },
]


def run_case(case: dict) -> dict:
    cmd = [
        sys.executable,
        "tools/build_reimbursement_package.py",
        case["input"],
        "--note",
        case["note"],
        "--title",
        case["title"],
    ]
    result = subprocess.run(cmd, cwd=ROOT, check=True, text=True, capture_output=True)
    return json.loads(result.stdout)


def main() -> None:
    for case in CASES:
        summary = run_case(case)
        missing = set(summary["missing_required"])
        if summary["type"] != case["expected_type"]:
            raise AssertionError(f"{case['title']}: expected type {case['expected_type']}, got {summary['type']}")
        if missing != case["expected_missing"]:
            raise AssertionError(f"{case['title']}: expected missing {case['expected_missing']}, got {missing}")
        package_dir = Path(summary["package"])
        for required in ["package.json", "package.md"]:
            if not (package_dir / required).exists():
                raise AssertionError(f"{case['title']}: missing exported {required}")
    print(json.dumps({"ok": True, "cases": len(CASES)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
