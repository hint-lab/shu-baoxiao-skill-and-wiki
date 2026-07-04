#!/usr/bin/env python3
from __future__ import annotations

import json
import urllib.parse
import urllib.request


BASE_URL = "http://127.0.0.1:8765"
PACKAGE_ID = "餐饮招待费报销包-京悦南门涮肉-20260522"


def read_url(path: str) -> str:
    with urllib.request.urlopen(BASE_URL + path, timeout=10) as response:
        return response.read().decode("utf-8")


def post_json(path: str) -> dict:
    request = urllib.request.Request(BASE_URL + path, data=b"", method="POST")
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    html = read_url(f"/packages/{urllib.parse.quote(PACKAGE_ID)}/view")
    if "invoice_request_exists" not in html:
        raise AssertionError("Package page did not include invoice request state")
    if "package-" not in html:
        raise AssertionError("Package page did not include built package asset")
    dry_run = post_json("/api/shu-auth/login?dry_run=true")
    if not dry_run.get("ok") or not dry_run.get("dry_run"):
        raise AssertionError(f"Unexpected dry-run login response: {dry_run}")
    print(json.dumps({"ok": True, "package": PACKAGE_ID, "login_dry_run": dry_run}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
