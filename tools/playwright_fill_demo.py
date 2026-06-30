#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright


ROOT = Path("/Users/hao/Documents/自助报销Agent")
DEFAULT_PLAN = ROOT / "output/packages/论文版面费报销包/playwright_plan.json"
ARTIFACT_DIR = ROOT / "output/playwright"


def load_plan(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def fill_mock_school(page, plan: dict[str, Any], mock_auto_login: bool) -> dict[str, Any]:
    if mock_auto_login:
        login_done = page.get_by_test_id("manual-login-done")
        if login_done.count() == 1:
            login_done.click()
    page.get_by_test_id("reimbursement-form").wait_for(state="visible", timeout=10000)

    recommended_entry = plan["school_system"]["recommended_entry"]
    page.get_by_test_id("school-entry").select_option(recommended_entry)
    page.get_by_test_id("reason").fill(plan["draft_fields"]["reason"])

    attachment_list = page.get_by_test_id("attachment-list")
    pause_list = page.get_by_test_id("pause-list")
    page.evaluate(
        """(payload) => {
          const attachmentList = document.querySelector('[data-testid="attachment-list"]');
          const pauseList = document.querySelector('[data-testid="pause-list"]');
          attachmentList.innerHTML = '';
          pauseList.innerHTML = '';
          for (const doc of payload.documents) {
            const li = document.createElement('li');
            li.textContent = `${doc.document_type} · ${doc.file_name}`;
            attachmentList.appendChild(li);
          }
          for (const item of payload.pauseItems) {
            const li = document.createElement('li');
            li.textContent = item;
            pauseList.appendChild(li);
          }
          const stopMessage = document.querySelector('[data-testid="stop-message"]');
          stopMessage.textContent = payload.stopMessage;
        }""",
        {
            "documents": plan["upload_documents"],
            "pauseItems": plan["must_pause_for_confirmation"],
            "stopMessage": "Agent 已完成可自动填写内容，已在提交预审前停止，等待老师确认。",
        },
    )

    submit_disabled = page.get_by_test_id("submit-precheck").is_disabled()
    return {
        "url": page.url,
        "entry": page.get_by_test_id("school-entry").input_value(),
        "reason": page.get_by_test_id("reason").input_value(),
        "attachment_count": attachment_list.locator("li").count(),
        "pause_count": pause_list.locator("li").count(),
        "submit_precheck_disabled": submit_disabled,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Playwright demo filler for reimbursement packages.")
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--url", default="http://127.0.0.1:8765/mock-school")
    parser.add_argument("--mock-auto-login", action="store_true", help="Click the local mock login-complete button for demo verification.")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--out", type=Path, default=ARTIFACT_DIR / "fill_demo_report.json")
    parser.add_argument("--screenshot", type=Path, default=ARTIFACT_DIR / "fill_demo.png")
    args = parser.parse_args()

    plan = load_plan(args.plan)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.screenshot.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(args.url)
        result = fill_mock_school(page, plan, args.mock_auto_login)
        page.screenshot(path=str(args.screenshot), full_page=True)
        browser.close()

    report = {
        "plan": str(args.plan.resolve()),
        "target_url": args.url,
        "package_id": plan["package_id"],
        "package_status": plan["status"],
        "agent_boundary": plan["agent_boundary"],
        "result": result,
        "screenshot": str(args.screenshot.resolve()),
        "verified_stop_before_submission": result["submit_precheck_disabled"] is True,
    }
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
