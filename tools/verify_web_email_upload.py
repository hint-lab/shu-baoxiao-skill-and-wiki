#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path


ROOT = Path("/Users/hao/Documents/自助报销Agent")
EML = ROOT / "samples/emails/office_supplies_forward.eml"
TITLE = "网页邮件上传验证办公用品包"
PACKAGE_JSON = ROOT / "output/packages" / TITLE / "package.json"


def server_ready() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8765/", timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def multipart_body(fields: dict[str, str], file_field: str, file_path: Path) -> tuple[bytes, str]:
    boundary = "----codex-" + uuid.uuid4().hex
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        chunks.append(value.encode("utf-8"))
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}\r\n".encode())
    chunks.append(
        (
            f'Content-Disposition: form-data; name="{file_field}"; filename="{file_path.name}"\r\n'
            "Content-Type: message/rfc822\r\n\r\n"
        ).encode()
    )
    chunks.append(file_path.read_bytes())
    chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), boundary


def main() -> None:
    server = None
    if not server_ready():
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8765"],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(30):
            if server_ready():
                break
            time.sleep(0.2)
        else:
            raise RuntimeError("Local server did not become ready on 127.0.0.1:8765")

    try:
        body, boundary = multipart_body(
            {"title": TITLE, "note": "网页上传 eml 邮件验证"},
            "files",
            EML,
        )
        request = urllib.request.Request(
            "http://127.0.0.1:8765/packages",
            data=body,
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler)
        with opener.open(request, timeout=20) as response:
            if response.status not in {200, 303}:
                raise AssertionError(f"Unexpected response status {response.status}")

        package = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
        if package["reimbursement_type_name"] != "办公用品/耗材报销":
            raise AssertionError(f"Unexpected package type {package['reimbursement_type_name']}")
        missing = [item["name"] for item in package["checklist"] if item["status"] == "missing"]
        if missing:
            raise AssertionError(f"Expected no missing required items, got {missing}")
        docs = {doc["file_name"] for doc in package["documents"]}
        expected = {"01-办公用品发票.txt", "02-销货清单.txt", "03-公务卡支付记录.txt"}
        if not expected.issubset(docs):
            raise AssertionError(f"Missing email attachments: expected {expected}, got {docs}")
        print(json.dumps({"ok": True, "package": str(PACKAGE_JSON.parent), "documents": sorted(docs)}, ensure_ascii=False, indent=2))
    finally:
        if server is not None:
            server.terminate()
            server.wait(timeout=5)


if __name__ == "__main__":
    main()
