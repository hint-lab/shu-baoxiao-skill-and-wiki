#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright


ROOT = Path("/Users/hao/Documents/自助报销Agent")
PROFILE_DIR = ROOT / "data/browser_profiles/shu-finance"
OBSERVED_ADAPTER = ROOT / "data/adapters/shu_finance_observed.json"
ARTIFACT_DIR = ROOT / "output/playwright"
OBSERVATION_REPORT_PATH = ARTIFACT_DIR / "shu_finance_observation.json"
ADAPTER_DRAFT_PATH = ARTIFACT_DIR / "shu_finance_adapter_draft.json"
DEFAULT_TARGET_URL = "https://znbx.shu.edu.cn:8000/BaseDataMobileWeb/#/Frame/Iframe/%23%2FLogin%2FCMSLogin%3FreturnUrl%3Dhttps%253A%252F%252Fznbx.shu.edu.cn%253A8000%252FClaimsPhone%252F%2523%252Fdaily%252Fstep1"
FORM_READY_TEXT = "日常报销单"
LOGIN_MARKERS = ["拖动滑块验证", "记住账号", "统一身份认证", "扫码登录"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def target_url() -> str:
    observed = read_json(OBSERVED_ADAPTER)
    return str(observed.get("target_after_login_url") or DEFAULT_TARGET_URL)


CONTROL_SCRIPT = """
() => {
  const visible = (el) => {
    const style = window.getComputedStyle(el);
    const box = el.getBoundingClientRect();
    return style && style.visibility !== 'hidden' && style.display !== 'none' && box.width > 0 && box.height > 0;
  };
  const selectorFor = (el) => {
    const tag = el.tagName.toLowerCase();
    if (el.id) return `#${CSS.escape(el.id)}`;
    const name = el.getAttribute('name');
    if (name) return `${tag}[name="${CSS.escape(name)}"]`;
    const placeholder = el.getAttribute('placeholder');
    if (placeholder) return `${tag}[placeholder="${placeholder.replaceAll('"', '\\"')}"]`;
    const type = el.getAttribute('type');
    if (type) return `${tag}[type="${CSS.escape(type)}"]`;
    return tag;
  };
  const labelText = (el) => {
    const labels = Array.from(el.labels || []).map((node) => node.innerText.trim()).filter(Boolean);
    if (labels.length) return labels;
    const id = el.id;
    if (id) {
      const label = document.querySelector(`label[for="${CSS.escape(id)}"]`);
      if (label && label.innerText.trim()) return [label.innerText.trim()];
    }
    const parent = el.closest('.ant-form-item, .form-item, .field, li, div');
    if (!parent) return [];
    return Array.from(parent.querySelectorAll('label, .ant-form-item-label, .label, .title'))
      .map((node) => node.innerText.trim())
      .filter(Boolean)
      .slice(0, 3);
  };
  return Array.from(document.querySelectorAll('input, textarea, select, button, [role="button"], [contenteditable="true"]'))
    .filter(visible)
    .map((el, index) => ({
      index,
      tag: el.tagName.toLowerCase(),
      type: el.getAttribute('type') || '',
      role: el.getAttribute('role') || '',
      text: (el.innerText || el.value || '').trim().slice(0, 120),
      placeholder: el.getAttribute('placeholder') || '',
      aria_label: el.getAttribute('aria-label') || '',
      name: el.getAttribute('name') || '',
      id: el.id || '',
      labels: labelText(el),
      selector: selectorFor(el),
      disabled: Boolean(el.disabled || el.getAttribute('aria-disabled') === 'true'),
      readonly: Boolean(el.readOnly || el.getAttribute('readonly') !== null),
    }));
}
"""


def classify_page(url: str, body: str) -> tuple[str, str]:
    if FORM_READY_TEXT in body:
        return "form_ready", "已观察到日常报销单。"
    if any(marker in body for marker in LOGIN_MARKERS) or "#/Login" in url or "newsso.shu.edu.cn" in url:
        return "needs_login", "还没有进入学校财务系统日常报销单，需要先完成统一登录。"
    return "unknown", "已打开学校页面，但未识别到日常报销单。"


def infer_locator(control: dict[str, Any]) -> dict[str, Any]:
    labels = [str(item).strip() for item in control.get("labels", []) if str(item).strip()]
    placeholder = str(control.get("placeholder") or "").strip()
    text = str(control.get("text") or "").strip()
    selector = str(control.get("selector") or "").strip()
    if labels:
        return {"label": labels[0], "exact": True}
    if placeholder:
        return {"placeholder": placeholder, "exact": True}
    if text:
        return {"text": text}
    return {"selector": selector}


def infer_adapter(report: dict[str, Any]) -> dict[str, Any]:
    controls = report.get("controls") if isinstance(report.get("controls"), list) else []
    fields: dict[str, Any] = {}
    manual_actions: list[dict[str, Any]] = []
    for control in controls:
        label_text = " ".join(str(item) for item in control.get("labels", []))
        combined = " ".join(
            [
                label_text,
                str(control.get("placeholder") or ""),
                str(control.get("aria_label") or ""),
                str(control.get("text") or ""),
            ]
        )
        tag = control.get("tag")
        if tag in {"input", "textarea"} and "报销事由" in combined:
            fields["reason_short"] = {
                **infer_locator(control),
                "kind": "textarea" if tag == "textarea" else "input",
                "value_path": "draft_fields.reason_short",
            }
        elif tag in {"input", "textarea"} and ("情况说明" in combined or "备注" in combined):
            fields["note_short"] = {
                **infer_locator(control),
                "kind": "textarea" if tag == "textarea" else "input",
                "value_path": "draft_fields.note_short",
            }
        elif any(keyword in combined for keyword in ["预算项目", "内转订单", "请选择票据", "请选择附件", "保存草稿", "下一步", "提交"]):
            manual_actions.append(
                {
                    "text": combined.strip()[:120],
                    "selector": control.get("selector", ""),
                    "reason": "涉及项目、票据、附件、保存或提交动作，必须本人确认后继续。",
                }
            )
    return {
        "id": "shu_finance_observation_draft",
        "name": "上海大学财务系统日常报销观察草稿",
        "generated_at": now_iso(),
        "ready_for_school_fill": False,
        "draft_only": True,
        "start_url": report.get("target_url") or DEFAULT_TARGET_URL,
        "target_after_login_url": report.get("target_url") or DEFAULT_TARGET_URL,
        "form_ready": {"text": FORM_READY_TEXT, "timeout_ms": 120000},
        "fields": fields,
        "manual_actions": manual_actions,
        "submission_guard": {
            "must_pause_before_click": True,
            "pause_points": [
                "选择经费预算项目",
                "确认票据影像",
                "确认附件",
                "保存草稿",
                "下一步",
                "提交预审",
                "提交审批",
                "任何真实性、合规性或承诺类勾选",
            ],
        },
        "agent_boundary": "这是观察草稿，不会直接启用真实学校系统代填。确认字段、上传和暂停点后再复制为 data/adapters/shu_finance.json 并标记 ready_for_school_fill=true。",
    }


def observe_finance_form(
    headed: bool = False,
    timeout_ms: int = 60000,
    out: Path = OBSERVATION_REPORT_PATH,
    adapter_out: Path = ADAPTER_DRAFT_PATH,
    mock_file: Path | None = None,
) -> dict[str, Any]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    target = mock_file.resolve().as_uri() if mock_file else target_url()
    with sync_playwright() as p:
        if mock_file:
            browser = p.chromium.launch(headless=not headed)
            context = browser.new_context(viewport={"width": 1360, "height": 900}, ignore_https_errors=True)
        else:
            PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            browser = None
            context = p.chromium.launch_persistent_context(
                str(PROFILE_DIR),
                headless=not headed,
                viewport={"width": 1360, "height": 900},
                ignore_https_errors=True,
                accept_downloads=True,
            )
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto(target, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 10000))
            except PlaywrightTimeoutError:
                pass
            try:
                page.get_by_text(FORM_READY_TEXT).wait_for(timeout=5000)
            except PlaywrightTimeoutError:
                pass
            body = page.locator("body").inner_text(timeout=5000)
            status, message = classify_page(page.url, body)
            controls = page.evaluate(CONTROL_SCRIPT) if status == "form_ready" else []
            report = {
                "ok": status == "form_ready",
                "status": status,
                "message": message,
                "target_url": target,
                "current_url": page.url,
                "title": page.title(),
                "observed_at": now_iso(),
                "control_count": len(controls),
                "controls": controls,
            }
        finally:
            context.close()
            if mock_file and browser is not None:
                browser.close()
    adapter = infer_adapter(report)
    report["adapter_draft"] = {
        "path": str(adapter_out.resolve()),
        "field_count": len(adapter.get("fields", {})),
        "manual_action_count": len(adapter.get("manual_actions", [])),
        "ready_for_school_fill": False,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    adapter_out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    adapter_out.write_text(json.dumps(adapter, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def saved_observation_status() -> dict[str, Any]:
    report = read_json(OBSERVATION_REPORT_PATH)
    adapter = read_json(ADAPTER_DRAFT_PATH)
    return {
        "report_exists": OBSERVATION_REPORT_PATH.exists(),
        "adapter_draft_exists": ADAPTER_DRAFT_PATH.exists(),
        "report_path": str(OBSERVATION_REPORT_PATH),
        "adapter_draft_path": str(ADAPTER_DRAFT_PATH),
        "status": report.get("status", "not_observed") if report else "not_observed",
        "message": report.get("message", ""),
        "observed_at": report.get("observed_at", ""),
        "control_count": report.get("control_count", 0),
        "field_count": len(adapter.get("fields", {})) if adapter else 0,
        "manual_action_count": len(adapter.get("manual_actions", [])) if adapter else 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Observe the SHU finance daily reimbursement form and draft adapter metadata.")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--timeout-ms", type=int, default=60000)
    parser.add_argument("--out", type=Path, default=OBSERVATION_REPORT_PATH)
    parser.add_argument("--adapter-out", type=Path, default=ADAPTER_DRAFT_PATH)
    parser.add_argument("--mock-file", type=Path, default=None, help="Local HTML file for deterministic tests.")
    parser.add_argument("--saved-status", action="store_true")
    args = parser.parse_args()
    if args.saved_status:
        payload = saved_observation_status()
    else:
        payload = observe_finance_form(
            headed=args.headed,
            timeout_ms=args.timeout_ms,
            out=args.out,
            adapter_out=args.adapter_out,
            mock_file=args.mock_file,
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
