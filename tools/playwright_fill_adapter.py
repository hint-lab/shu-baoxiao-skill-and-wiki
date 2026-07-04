#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright


ROOT = Path("/Users/hao/Documents/自助报销Agent")
DEFAULT_PLAN = ROOT / "output/packages/论文版面费报销包/playwright_plan.json"
DEFAULT_ADAPTER = ROOT / "data/adapters/mock_school.json"
ARTIFACT_DIR = ROOT / "output/playwright"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def get_value(payload: dict[str, Any], path: str) -> Any:
    value: Any = payload
    for part in path.split("."):
        value = value[part]
    return value


def locator(page: Page, spec: dict[str, Any]):
    if spec.get("test_id"):
        return page.get_by_test_id(spec["test_id"])
    if spec.get("label"):
        return page.get_by_label(spec["label"], exact=bool(spec.get("exact", True)))
    if spec.get("placeholder"):
        return page.get_by_placeholder(spec["placeholder"], exact=bool(spec.get("exact", True)))
    if spec.get("role"):
        return page.get_by_role(spec["role"], name=spec.get("name"))
    if spec.get("selector"):
        return page.locator(spec["selector"])
    if spec.get("text"):
        return page.get_by_text(spec["text"])
    raise ValueError(f"Adapter locator is missing a supported locator: {spec}")


def wait_form_ready(page: Page, adapter: dict[str, Any]) -> None:
    ready = adapter["form_ready"]
    locator(page, ready).wait_for(state="visible", timeout=ready.get("timeout_ms", 10000))


def maybe_complete_mock_login(page: Page, adapter: dict[str, Any], allow_auto_login: bool) -> None:
    manual = adapter.get("manual_login", {})
    if not allow_auto_login:
        return
    test_id = manual.get("complete_click_test_id")
    if not test_id:
        return
    button = page.get_by_test_id(test_id)
    if button.count() == 1:
        button.click()


def fill_field(page: Page, field_spec: dict[str, Any], plan: dict[str, Any]) -> Any:
    value = get_value(plan, field_spec["value_path"])
    target = locator(page, field_spec)
    kind = field_spec.get("kind", "text")
    if kind == "select":
        target.select_option(str(value))
    elif kind in {"textarea", "text", "input"}:
        target.fill(str(value))
    else:
        raise ValueError(f"Unsupported field kind: {kind}")
    return value


def inject_mock_lists(page: Page, adapter: dict[str, Any], plan: dict[str, Any]) -> dict[str, int]:
    lists = adapter.get("lists", {})
    attachment_spec = lists.get("attachments")
    pause_spec = lists.get("pause_points")
    counts = {"attachment_count": 0, "pause_count": 0}
    if attachment_spec:
        attachment = locator(page, attachment_spec)
        attachment.evaluate(
            """(node, docs) => {
              node.innerHTML = '';
              for (const doc of docs) {
                const li = document.createElement('li');
                li.textContent = `${doc.document_type} · ${doc.file_name}`;
                node.appendChild(li);
              }
            }""",
            plan["upload_documents"],
        )
        counts["attachment_count"] = attachment.locator("li").count()
    if pause_spec:
        pause = locator(page, pause_spec)
        pause.evaluate(
            """(node, items) => {
              node.innerHTML = '';
              for (const item of items) {
                const li = document.createElement('li');
                li.textContent = item;
                node.appendChild(li);
              }
            }""",
            plan["must_pause_for_confirmation"],
        )
        counts["pause_count"] = pause.locator("li").count()
    status = adapter.get("status_message")
    if status:
        locator(page, status).evaluate("(node, text) => { node.textContent = text; }", status.get("text", ""))
    return counts


def verify_submission_guard(page: Page, adapter: dict[str, Any]) -> bool:
    guard = adapter.get("submission_guard", {})
    if not guard:
        return True
    button = locator(page, guard)
    if guard.get("must_be_disabled"):
        return button.is_disabled()
    if guard.get("must_pause_before_click"):
        return True
    return True


def run_fill(
    plan_path: Path,
    adapter_path: Path,
    allow_auto_login: bool,
    headed: bool,
    out: Path,
    screenshot: Path,
    profile_dir: Path | None = None,
) -> dict[str, Any]:
    plan = load_json(plan_path)
    adapter = load_json(adapter_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    target_url = adapter.get("target_after_login_url") or adapter["start_url"]

    with sync_playwright() as p:
        browser = None
        if profile_dir:
            profile_dir.mkdir(parents=True, exist_ok=True)
            context = p.chromium.launch_persistent_context(
                str(profile_dir),
                headless=not headed,
                viewport={"width": 1280, "height": 900},
                ignore_https_errors=True,
                accept_downloads=True,
            )
        else:
            browser = p.chromium.launch(headless=not headed)
            context = browser.new_context(viewport={"width": 1280, "height": 900}, ignore_https_errors=True)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto(target_url)
            maybe_complete_mock_login(page, adapter, allow_auto_login)
            wait_form_ready(page, adapter)
            filled = {}
            for name, spec in adapter.get("fields", {}).items():
                filled[name] = fill_field(page, spec, plan)
            list_counts = inject_mock_lists(page, adapter, plan)
            stop_ok = verify_submission_guard(page, adapter)
            page.screenshot(path=str(screenshot), full_page=True)
            current_url = page.url
        finally:
            context.close()
            if browser is not None:
                browser.close()

    report = {
        "adapter": str(adapter_path.resolve()),
        "adapter_id": adapter["id"],
        "plan": str(plan_path.resolve()),
        "target_url": target_url,
        "current_url": current_url,
        "package_id": plan["package_id"],
        "package_status": plan["status"],
        "agent_boundary": plan["agent_boundary"],
        "filled": filled,
        "attachment_count": list_counts["attachment_count"],
        "pause_count": list_counts["pause_count"],
        "verified_stop_before_submission": stop_ok,
        "screenshot": str(screenshot.resolve()),
    }
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Generic Playwright reimbursement filler driven by an adapter JSON.")
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--adapter", type=Path, default=DEFAULT_ADAPTER)
    parser.add_argument("--allow-auto-login", action="store_true", help="Only for local mock adapters. Real systems require manual login.")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--profile-dir", type=Path, default=None, help="Reuse a persistent browser profile, for example an already logged-in school session.")
    parser.add_argument("--out", type=Path, default=ARTIFACT_DIR / "fill_adapter_report.json")
    parser.add_argument("--screenshot", type=Path, default=ARTIFACT_DIR / "fill_adapter.png")
    args = parser.parse_args()

    report = run_fill(args.plan, args.adapter, args.allow_auto_login, args.headed, args.out, args.screenshot, args.profile_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
