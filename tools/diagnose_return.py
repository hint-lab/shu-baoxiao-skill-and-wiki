#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path("/Users/hao/Documents/自助报销Agent")
OUTPUT_ROOT = ROOT / "output/packages"
RULES_PATH = ROOT / "data/rules/return_reason_rules.json"


@dataclass
class ReturnMatch:
    rule_id: str
    checklist_id: str
    checklist_name: str
    status_before: str
    action: str
    evidence_title: str
    evidence_url: str


@dataclass
class ReturnDiagnosis:
    package_id: str
    title: str
    created_at: str
    return_reason: str
    matched_items: list[ReturnMatch]
    fallback_action: str | None
    next_steps: list[str]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def package_path(package: str) -> Path:
    path = Path(package)
    if path.exists():
        if path.is_dir():
            return path / "package.json"
        return path
    return OUTPUT_ROOT / package / "package.json"


def evidence_from_item(item: dict[str, Any]) -> tuple[str, str]:
    evidence = item.get("evidence") or {}
    return evidence.get("title", ""), evidence.get("url", "")


def diagnose(package_json: Path, reason: str) -> ReturnDiagnosis:
    package = load_json(package_json)
    rules = load_json(RULES_PATH)
    reason_norm = normalize(reason)
    checklist_by_id = {item["id"]: item for item in package.get("checklist", [])}

    matches: list[ReturnMatch] = []
    seen: set[tuple[str, str]] = set()
    for rule in rules["rules"]:
        if not any(normalize(keyword) in reason_norm for keyword in rule["keywords"]):
            continue
        for checklist_id in rule["checklist_ids"]:
            item = checklist_by_id.get(checklist_id)
            if not item:
                continue
            key = (rule["id"], checklist_id)
            if key in seen:
                continue
            seen.add(key)
            title, url = evidence_from_item(item)
            matches.append(
                ReturnMatch(
                    rule_id=rule["id"],
                    checklist_id=checklist_id,
                    checklist_name=item["name"],
                    status_before=item["status"],
                    action=rule["action"],
                    evidence_title=title,
                    evidence_url=url,
                )
            )

    fallback = None if matches else rules["fallback_action"]
    next_steps = []
    if matches:
        next_steps.append("按下列命中项补充或替换材料后，重新生成报销包。")
        next_steps.append("重新检查缺漏清单，确认相关项目从 missing/optional 变为 ready 或已人工确认。")
        next_steps.append("再次进入 Playwright 代填流程，仍需在提交预审前由本人确认。")
    else:
        next_steps.append(rules["fallback_action"])
        next_steps.append("必要时把退回意见补充到备注中重新生成报销包。")

    return ReturnDiagnosis(
        package_id=package["id"],
        title=package["title"],
        created_at=datetime.now(timezone.utc).isoformat(),
        return_reason=reason,
        matched_items=matches,
        fallback_action=fallback,
        next_steps=next_steps,
    )


def write_markdown(diagnosis: ReturnDiagnosis, path: Path) -> None:
    lines = [
        f"# 退回诊断：{diagnosis.title}",
        "",
        "## 退回意见",
        "",
        diagnosis.return_reason,
        "",
        "## 命中项",
        "",
    ]
    if diagnosis.matched_items:
        for item in diagnosis.matched_items:
            lines.extend(
                [
                    f"### {item.checklist_name}",
                    "",
                    f"- 退回前状态：{item.status_before}",
                    f"- 建议动作：{item.action}",
                    f"- 依据：{item.evidence_title or '-'} {item.evidence_url or ''}".rstrip(),
                    "",
                ]
            )
    else:
        lines.append(diagnosis.fallback_action or "未匹配到明确缺漏项。")
        lines.append("")

    lines.extend(["## 下一步", ""])
    lines.extend(f"- {step}" for step in diagnosis.next_steps)
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def export_diagnosis(diagnosis: ReturnDiagnosis, package_dir: Path) -> None:
    package_dir.mkdir(parents=True, exist_ok=True)
    payload = asdict(diagnosis)
    (package_dir / "return_diagnosis.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(diagnosis, package_dir / "return_diagnosis.md")


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose finance-system return reasons against a reimbursement package.")
    parser.add_argument("package", help="Package id, package directory, or package.json path")
    parser.add_argument("--reason", required=True, help="Original return reason from the finance system")
    args = parser.parse_args()

    pkg_json = package_path(args.package)
    if not pkg_json.exists():
        raise FileNotFoundError(f"Package not found: {args.package}")
    diagnosis = diagnose(pkg_json, args.reason)
    export_diagnosis(diagnosis, pkg_json.parent)
    print(json.dumps(asdict(diagnosis), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
