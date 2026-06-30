#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pypdf import PdfReader


ROOT = Path("/Users/hao/Documents/自助报销Agent")
DOCS_PATH = ROOT / "data/cwc/documents.jsonl"
ATTACHMENTS_RETRY_DIR = ROOT / "data/cwc/attachments_retry"
MINERU_CACHE_DIR = ROOT / "data/cwc/mineru"
DEFAULT_LOCAL_PDFS = [
    ROOT / "tmp/pdfs/上海大学智能报销操作手册2025年3月.pdf",
    ROOT / "data/cwc/browser_downloads/c3b16291ce28-2018年新版常见业务费报销指南(文字版).pdf",
    ROOT / "data/cwc/browser_downloads/2025CWCCZSC.pdf",
]
MIN_TEXT_CHARS = 80


@dataclass
class MergeResult:
    attachment_pdfs_seen: int = 0
    attachment_docs_filled: int = 0
    local_pdfs_added: int = 0
    mineru_attempted: int = 0
    mineru_filled: int = 0
    still_empty_attachments: int = 0


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_id(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]


def clean_text(text: str) -> str:
    return "\n".join(line.strip() for line in text.replace("\xa0", " ").splitlines() if line.strip())


def extract_pdf_text(path: Path) -> tuple[str, int]:
    reader = PdfReader(str(path))
    pages: list[str] = []
    for page_index, page in enumerate(reader.pages, 1):
        text = clean_text(page.extract_text() or "")
        if text:
            pages.append(f"--- page {page_index} ---\n{text}")
    return "\n\n".join(pages), len(reader.pages)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    backup = path.with_suffix(path.suffix + f".bak-{int(time.time())}")
    if path.exists():
        shutil.copy2(path, backup)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def retry_pdf_map(retry_dir: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    if not retry_dir.exists():
        return result
    for path in sorted(retry_dir.glob("*.pdf")):
        prefix = path.name.split("-", 1)[0]
        if prefix:
            result[prefix] = path
    return result


def read_http_json(url: str, payload: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout: int = 60) -> dict[str, Any]:
    data = None
    method = "GET"
    request_headers = {"Accept": "application/json", **(headers or {})}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
        method = "POST"
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def put_file(url: str, path: Path, timeout: int = 300) -> None:
    completed = subprocess.run(
        [
            "curl",
            "--globoff",
            "-sS",
            "-o",
            "/tmp/mineru-upload.out",
            "-w",
            "%{http_code}",
            "-X",
            "PUT",
            "--upload-file",
            str(path),
            url,
        ],
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    status = (completed.stdout or "").strip()
    if completed.returncode != 0 or not status.startswith("2"):
        raise RuntimeError(f"MinerU upload failed with curl={completed.returncode} http={status}")


def put_file_with_urllib(url: str, path: Path, timeout: int = 300) -> None:
    data = path.read_bytes()
    request = urllib.request.Request(
        url,
        data=data,
        method="PUT",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status >= 300:
            raise RuntimeError(f"MinerU upload failed with HTTP {response.status}")


def download_text(url: str, timeout: int = 120) -> str:
    request = urllib.request.Request(url, headers={"Accept": "text/markdown,text/plain,*/*"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def mineru_agent_parse(path: Path, page_count: int, wait_seconds: int, poll_interval: float) -> str:
    if path.stat().st_size > 10 * 1024 * 1024:
        return ""
    if page_count > 20:
        return ""
    create_payload = {
        "file_name": path.name,
        "language": "ch",
        "enable_table": True,
        "enable_formula": False,
        "is_ocr": True,
    }
    created = read_http_json("https://mineru.net/api/v1/agent/parse/file", create_payload)
    data = created.get("data") or {}
    task_id = data.get("task_id")
    file_url = data.get("file_url")
    if not task_id or not file_url:
        return ""
    put_file(file_url, path)
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        result = read_http_json(f"https://mineru.net/api/v1/agent/parse/{task_id}")
        payload = result.get("data") or {}
        state = payload.get("state")
        if state == "done" and payload.get("markdown_url"):
            markdown = download_text(payload["markdown_url"])
            cache_path = MINERU_CACHE_DIR / f"{path.stem}.md"
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(markdown, encoding="utf-8")
            return clean_text(markdown)
        if state == "failed":
            return ""
        time.sleep(poll_interval)
    return ""


def merge_attachment_pdfs(rows: list[dict[str, Any]], use_mineru: bool, limit: int, result: MergeResult) -> None:
    pdfs = retry_pdf_map(ATTACHMENTS_RETRY_DIR)
    result.attachment_pdfs_seen = len(pdfs)
    processed = 0
    for doc in rows:
        if limit and processed >= limit:
            break
        if doc.get("source_type") != "attachment":
            continue
        if (doc.get("text") or "").strip():
            continue
        doc_id = str(doc.get("id") or "")
        pdf = None
        for size in (12, 16):
            candidate = pdfs.get(doc_id[:size])
            if candidate:
                pdf = candidate
                break
        if not pdf:
            continue
        processed += 1
        try:
            text, page_count = extract_pdf_text(pdf)
        except Exception as exc:
            text, page_count = "", 0
            doc.setdefault("metadata", {})["pdf_extract_error"] = exc.__class__.__name__
        method = "pypdf"
        mineru_eligible = use_mineru and page_count and page_count <= 20 and pdf.stat().st_size <= 10 * 1024 * 1024
        if len(text.strip()) < MIN_TEXT_CHARS and mineru_eligible:
            result.mineru_attempted += 1
            try:
                mineru_text = mineru_agent_parse(pdf, page_count, wait_seconds=240, poll_interval=3)
            except (urllib.error.URLError, TimeoutError, RuntimeError):
                mineru_text = ""
            if len(mineru_text.strip()) >= MIN_TEXT_CHARS:
                text = mineru_text
                method = "mineru_agent"
                result.mineru_filled += 1
        if len(text.strip()) >= MIN_TEXT_CHARS:
            doc["text"] = text
            doc["status"] = "downloaded_pdf_text"
            metadata = doc.setdefault("metadata", {})
            metadata["downloaded"] = True
            metadata["is_pdf"] = True
            metadata["local_path"] = str(pdf.resolve())
            metadata["extract_method"] = method
            metadata["page_count"] = page_count
            result.attachment_docs_filled += 1
    result.still_empty_attachments = sum(1 for doc in rows if doc.get("source_type") == "attachment" and not (doc.get("text") or "").strip())


def append_local_pdfs(rows: list[dict[str, Any]], pdfs: list[Path], result: MergeResult) -> None:
    existing_ids = {str(row.get("id") or "") for row in rows}
    existing_paths = {str((row.get("metadata") or {}).get("local_path") or row.get("url") or "") for row in rows}
    for raw_path in pdfs:
        path = raw_path.expanduser()
        if not path.is_absolute():
            path = (ROOT / path).resolve()
        if not path.exists() or path.suffix.lower() != ".pdf":
            continue
        doc_id = stable_id(str(path.resolve()))
        if doc_id in existing_ids or str(path.resolve()) in existing_paths:
            continue
        try:
            text, page_count = extract_pdf_text(path)
        except Exception:
            text, page_count = "", 0
        if len(text.strip()) < MIN_TEXT_CHARS:
            continue
        rows.append(
            {
                "id": doc_id,
                "url": str(path.resolve()),
                "title": path.stem,
                "source_type": "local_pdf",
                "fetched_at": now_iso(),
                "status": "local",
                "content_type": "application/pdf",
                "text": text,
                "links": [],
                "attachments": [],
                "metadata": {
                    "local_path": str(path.resolve()),
                    "is_pdf": True,
                    "extract_method": "pypdf",
                    "page_count": page_count,
                },
            }
        )
        existing_ids.add(doc_id)
        existing_paths.add(str(path.resolve()))
        result.local_pdfs_added += 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge retried CWC PDF attachment downloads into documents.jsonl and append local PDFs.")
    parser.add_argument("--docs", type=Path, default=DOCS_PATH)
    parser.add_argument("--mineru", action="store_true", help="Use MinerU Agent OCR for small scanned PDFs when local extraction is empty.")
    parser.add_argument("--limit", type=int, default=0, help="Limit empty attachment PDFs to process; 0 means all.")
    parser.add_argument("--local-pdf", action="append", type=Path, default=[], help="Extra local PDF to add as local_pdf.")
    args = parser.parse_args()

    rows = read_jsonl(args.docs)
    result = MergeResult()
    merge_attachment_pdfs(rows, args.mineru, args.limit, result)
    append_local_pdfs(rows, [*DEFAULT_LOCAL_PDFS, *args.local_pdf], result)
    write_jsonl(args.docs, rows)
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
