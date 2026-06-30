#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright


ROOT = Path("/Users/hao/Documents/自助报销Agent")
PROFILE_DIR = ROOT / "data/browser_profiles/shu-finance"
SESSION_DIR = ROOT / "data/auth_sessions"
SESSION_META = SESSION_DIR / "shu_finance_session.json"

BUSINESS_HOME_URL = "https://znbx.shu.edu.cn:8000/BaseDataMobileWeb/#/Frame/Service/Index"
SHU_AUTH_URL = "https://znbx.shu.edu.cn:8000/BaseDataMobileWeb/#/Login/ShuAuth"
BUSINESS_HOST_MARKER = "znbx.shu.edu.cn:8000"
BUSINESS_APP_MARKER = "/BaseDataMobileWeb/"
SSO_HOST_MARKER = "newsso.shu.edu.cn"

STATUS_READY = "ready"
STATUS_NEEDS_RENEW = "needs_renew"
STATUS_NEEDS_SCAN = "needs_scan"
STATUS_UNKNOWN = "unknown"
STATUS_ERROR = "error"


@dataclass
class SessionStatus:
    status: str
    url: str = ""
    title: str = ""
    message: str = ""
    profile_dir: str = str(PROFILE_DIR)
    profile_exists: bool = False
    checked_at: str = ""
    last_ready_at: str = ""
    last_scan_required_at: str = ""
    business_host: str = BUSINESS_HOST_MARKER
    sso_host: str = SSO_HOST_MARKER


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_meta() -> dict[str, Any]:
    if not SESSION_META.exists():
        return {}
    try:
        return json.loads(SESSION_META.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_meta(status: SessionStatus) -> None:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    previous = load_meta()
    payload = {**previous, **asdict(status)}
    if status.status == STATUS_READY:
        payload["last_ready_at"] = status.checked_at
    if status.status == STATUS_NEEDS_SCAN:
        payload["last_scan_required_at"] = status.checked_at
    SESSION_META.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def saved_status() -> dict[str, Any]:
    meta = load_meta()
    return {
        "profile_dir": str(PROFILE_DIR),
        "profile_exists": PROFILE_DIR.exists(),
        "meta_exists": SESSION_META.exists(),
        "status": meta.get("status", "not_checked"),
        "url": meta.get("url", ""),
        "title": meta.get("title", ""),
        "message": meta.get("message", ""),
        "checked_at": meta.get("checked_at", ""),
        "last_ready_at": meta.get("last_ready_at", ""),
        "last_scan_required_at": meta.get("last_scan_required_at", ""),
        "business_home_url": BUSINESS_HOME_URL,
        "shu_auth_url": SHU_AUTH_URL,
        "business_host": BUSINESS_HOST_MARKER,
        "sso_host": SSO_HOST_MARKER,
    }


def classify_page(page: Page) -> SessionStatus:
    url = page.url
    title = ""
    try:
        title = page.title()
    except Exception:
        title = ""

    status = STATUS_UNKNOWN
    message = "未能判断当前登录态。"
    if BUSINESS_HOST_MARKER in url and BUSINESS_APP_MARKER in url and "#/Frame/" in url:
        status = STATUS_READY
        message = "上海大学财务系统业务会话可用。"
    elif BUSINESS_HOST_MARKER in url and "#/Login/ShuAuth" in url:
        status = STATUS_NEEDS_SCAN
        message = "已进入财务系统 ShuAuth 续登入口，下一步需要上海大学统一身份认证会话或本人扫码。"
    elif BUSINESS_HOST_MARKER in url and "#/Login" in url:
        status = STATUS_NEEDS_RENEW
        message = "财务系统业务会话不可用，可以尝试通过上海大学统一身份认证续登。"
    elif SSO_HOST_MARKER in url:
        status = STATUS_NEEDS_SCAN
        message = "停在上海大学统一身份认证页，需要本人扫码或确认登录。"
    elif "eportal.shu.edu.cn" in url:
        status = STATUS_NEEDS_RENEW
        message = "当前是个人门户登录结果，不是财务系统业务会话；需要回到财务系统 ShuAuth 入口换取报销系统登录态。"

    return SessionStatus(
        status=status,
        url=url,
        title=title,
        message=message,
        profile_exists=PROFILE_DIR.exists(),
        checked_at=now_iso(),
    )


def _best_effort_wait(page: Page, timeout_ms: int) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except PlaywrightTimeoutError:
        pass


def _best_effort_goto(page: Page, url: str, timeout_ms: int) -> None:
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    except PlaywrightTimeoutError:
        pass


def _wait_for_auth_transition(page: Page, timeout_ms: int) -> None:
    try:
        page.wait_for_url(
            lambda url: (
                (BUSINESS_HOST_MARKER in url and BUSINESS_APP_MARKER in url and "#/Frame/" in url)
                or SSO_HOST_MARKER in url
            ),
            timeout=timeout_ms,
        )
    except PlaywrightTimeoutError:
        pass


def _launch_context(playwright, headed: bool):
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    return playwright.chromium.launch_persistent_context(
        str(PROFILE_DIR),
        headless=not headed,
        viewport={"width": 1360, "height": 900},
        ignore_https_errors=True,
        accept_downloads=True,
    )


def check_business_session(headed: bool = False, timeout_ms: int = 15000) -> SessionStatus:
    with sync_playwright() as p:
        context = _launch_context(p, headed=headed)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            _best_effort_goto(page, BUSINESS_HOME_URL, timeout_ms)
            _best_effort_wait(page, min(timeout_ms, 8000))
            status = classify_page(page)
        except Exception as exc:
            status = SessionStatus(
                status=STATUS_ERROR,
                message=f"检查财务系统登录态失败：{exc.__class__.__name__}",
                profile_exists=PROFILE_DIR.exists(),
                checked_at=now_iso(),
            )
        finally:
            context.close()
    save_meta(status)
    return status


def ensure_ready(headed: bool = True, wait_scan: bool = True, timeout_ms: int = 180000) -> SessionStatus:
    with sync_playwright() as p:
        context = _launch_context(p, headed=headed)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            _best_effort_goto(page, BUSINESS_HOME_URL, 30000)
            _best_effort_wait(page, 8000)
            status = classify_page(page)
            save_meta(status)
            if status.status != STATUS_READY:
                _best_effort_goto(page, SHU_AUTH_URL, 30000)
                _best_effort_wait(page, 8000)
                status = classify_page(page)
                save_meta(status)
                if wait_scan:
                    try:
                        page.wait_for_url(
                            lambda url: BUSINESS_HOST_MARKER in url and BUSINESS_APP_MARKER in url and "#/Frame/" in url,
                            timeout=timeout_ms,
                        )
                    except PlaywrightTimeoutError:
                        pass
                else:
                    _wait_for_auth_transition(page, min(timeout_ms, 30000))
                status = classify_page(page)
                save_meta(status)
        except Exception as exc:
            status = SessionStatus(
                status=STATUS_ERROR,
                message=f"续登流程失败：{exc.__class__.__name__}",
                profile_exists=PROFILE_DIR.exists(),
                checked_at=now_iso(),
            )
            save_meta(status)
        finally:
            context.close()
    save_meta(status)
    return status


def clear_session() -> dict[str, Any]:
    if PROFILE_DIR.exists():
        shutil.rmtree(PROFILE_DIR)
    if SESSION_META.exists():
        SESSION_META.unlink()
    return saved_status()


def main() -> None:
    parser = argparse.ArgumentParser(description="上海大学财务系统扫码登录保持工具")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("saved-status", help="只读取本地已保存的会话状态，不启动浏览器")

    check_parser = subparsers.add_parser("check", help="启动专用浏览器 profile，检查财务系统业务会话是否仍可用")
    check_parser.add_argument("--headed", action="store_true", help="显示浏览器窗口")
    check_parser.add_argument("--timeout-ms", type=int, default=15000)

    login_parser = subparsers.add_parser("login", help="打开专用浏览器并等待本人扫码/续登到财务系统")
    login_parser.add_argument("--headless", action="store_true", help="不显示浏览器窗口；仅适合已有 SSO 会话时自动续登")
    login_parser.add_argument("--no-wait-scan", action="store_true", help="打开登录入口后不等待扫码完成")
    login_parser.add_argument("--timeout-ms", type=int, default=180000)

    subparsers.add_parser("clear", help="清除本机保存的专用浏览器 profile 和会话状态")

    args = parser.parse_args()
    if args.command == "saved-status":
        result = saved_status()
    elif args.command == "check":
        result = asdict(check_business_session(headed=args.headed, timeout_ms=args.timeout_ms))
    elif args.command == "login":
        result = asdict(ensure_ready(headed=not args.headless, wait_scan=not args.no_wait_scan, timeout_ms=args.timeout_ms))
    elif args.command == "clear":
        result = clear_session()
    else:
        raise AssertionError(args.command)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
