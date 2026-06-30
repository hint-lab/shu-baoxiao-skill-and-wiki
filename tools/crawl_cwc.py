#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urldefrag, urljoin, urlparse

import requests
from lxml import html
from pypdf import PdfReader


ROOT = Path("/Users/hao/Documents/自助报销Agent")
DATA_DIR = ROOT / "data/cwc"
RAW_DIR = DATA_DIR / "raw"
ATTACHMENT_DIR = DATA_DIR / "attachments"
DOCS_PATH = DATA_DIR / "documents.jsonl"
MANIFEST_PATH = DATA_DIR / "crawl_manifest.json"

BASE_URL = "https://cwc.shu.edu.cn/"
HOST = "cwc.shu.edu.cn"
DEFAULT_START_URLS = [
    BASE_URL,
    "https://cwc.shu.edu.cn/fwzn/jbbxywlczn.htm",
    "https://cwc.shu.edu.cn/fwzn/xtczzn.htm",
    "https://cwc.shu.edu.cn/xzzx.htm",
    "https://cwc.shu.edu.cn/tzgg.htm",
]

TEXT_EXTENSIONS = {".htm", ".html", ""}
ATTACHMENT_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".zip",
    ".rar",
    ".ofd",
}


@dataclass
class Document:
    id: str
    url: str
    title: str
    source_type: str
    fetched_at: str
    status: str
    content_type: str
    text: str
    links: list[str]
    attachments: list[dict]
    metadata: dict


def normalize_url(url: str) -> str:
    url = urldefrag(url)[0]
    parsed = urlparse(url)
    if not parsed.scheme:
        return url
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = re.sub(r"/+", "/", parsed.path)
    return parsed._replace(scheme=scheme, netloc=netloc, path=path).geturl()


def allowed_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    if parsed.netloc.lower() != HOST:
        return False
    return True


def looks_like_attachment(url: str) -> bool:
    path = urlparse(url).path.lower()
    query = urlparse(url).query.lower()
    return (
        any(path.endswith(ext) for ext in ATTACHMENT_EXTENSIONS)
        or "/__local/" in path
        or "download.jsp" in path
        or "downloadattachurl" in query
        or "wbfileid=" in query
    )


def stable_id(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def clean_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def extract_date(text: str) -> str | None:
    match = re.search(r"(20\d{2})[-./年](\d{1,2})[-./月](\d{1,2})", text)
    if not match:
        return None
    y, m, d = match.groups()
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"


def strip_noise(tree: html.HtmlElement) -> None:
    for node in tree.xpath("//script|//style|//noscript|//iframe"):
        parent = node.getparent()
        if parent is not None:
            parent.remove(node)


def extract_page(url: str, body: bytes, content_type: str) -> tuple[str, str, list[str], list[dict], dict]:
    tree = html.fromstring(body, base_url=url)
    strip_noise(tree)

    title_parts = [t.strip() for t in tree.xpath("//title/text()") if t.strip()]
    h1_parts = [t.strip() for t in tree.xpath("//h1//text()|//*[contains(@class,'title')]//text()") if t.strip()]
    title = h1_parts[0] if h1_parts else (title_parts[0] if title_parts else url)
    title = re.sub(r"[\s_-]*上海大学财务处.*$", "", title).strip() or title

    candidate_xpaths = [
        "//*[contains(@class,'vsb_content') or contains(@class,'v_news_content')]",
        "//*[contains(@id,'ArtDetail') or contains(@id,'CalendarDetail')]",
        "//*[contains(@class,'article') or contains(@class,'Article') or contains(@class,'news_detail')]",
        "//*[contains(@id,'content') or contains(@class,'content')]",
    ]
    candidates = []
    for xpath in candidate_xpaths:
        candidates = tree.xpath(xpath)
        candidates = [node for node in candidates if len(clean_text(node.text_content())) >= 80]
        if candidates:
            break
    root = max(candidates, key=lambda node: len(clean_text(node.text_content()))) if candidates else tree
    text = clean_text(root.text_content())
    if len(text) < 80:
        text = clean_text(tree.text_content())

    links: list[str] = []
    attachments: list[dict] = []
    for a in tree.xpath("//a[@href]"):
        href = a.get("href")
        if not href:
            continue
        target = normalize_url(urljoin(url, href))
        if not allowed_url(target):
            continue
        label = clean_text(a.text_content())[:200]
        if looks_like_attachment(target):
            attachments.append({"url": target, "label": label})
        else:
            links.append(target)

    metadata = {
        "published_date": extract_date(text),
        "page_title": title_parts[0] if title_parts else "",
    }
    return title, text, sorted(set(links)), attachments, metadata


def read_pdf_text(path: Path) -> str:
    try:
        reader = PdfReader(str(path))
        pages = []
        for i, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            if text.strip():
                pages.append(f"--- page {i} ---\n{text}")
        return clean_text("\n\n".join(pages))
    except Exception as exc:
        return f"[PDF text extraction failed: {type(exc).__name__}: {exc}]"


def fetch(session: requests.Session, url: str, timeout: int = 20) -> requests.Response:
    headers = {
        "User-Agent": "Mozilla/5.0 SHU-CWC-RAG/0.1 (+local research)",
        "Accept": "text/html,application/xhtml+xml,application/pdf,application/octet-stream,*/*;q=0.8",
    }
    return session.get(url, headers=headers, timeout=timeout, allow_redirects=True)


def attachment_filename(url: str, content_type: str, label: str = "") -> str:
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix
    label_suffix = Path(label).suffix
    if not suffix and label_suffix:
        suffix = label_suffix
    if not suffix:
        if "pdf" in content_type.lower():
            suffix = ".pdf"
        else:
            suffix = ".bin"
    return f"{stable_id(url)}{suffix}"


def save_jsonl(path: Path, docs: Iterable[Document]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for doc in docs:
            f.write(json.dumps(asdict(doc), ensure_ascii=False) + "\n")


def crawl(max_pages: int, max_attachments: int, delay: float, start_urls: list[str]) -> list[Document]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    ATTACHMENT_DIR.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    queue = deque(normalize_url(u) for u in start_urls)
    seen: set[str] = set()
    docs: list[Document] = []
    attachment_seen: set[str] = set()
    fetched_at = datetime.now(timezone.utc).isoformat()

    while queue and len([d for d in docs if d.source_type == "page"]) < max_pages:
        url = queue.popleft()
        if url in seen or not allowed_url(url):
            continue
        seen.add(url)

        try:
            response = fetch(session, url)
            status = str(response.status_code)
            content_type = response.headers.get("content-type", "")
            body = response.content
        except Exception as exc:
            docs.append(
                Document(stable_id(url), url, url, "page", fetched_at, f"error:{type(exc).__name__}", "", "", [], [], {"error": str(exc)})
            )
            continue

        raw_path = RAW_DIR / f"{stable_id(url)}.html"
        raw_path.write_bytes(body)

        if response.status_code != 200 or "html" not in content_type.lower():
            docs.append(
                Document(stable_id(url), url, url, "page", fetched_at, status, content_type, "", [], [], {"raw_path": str(raw_path)})
            )
            continue

        title, text, links, attachments, metadata = extract_page(url, body, content_type)
        metadata["raw_path"] = str(raw_path)
        docs.append(
            Document(stable_id(url), url, title, "page", fetched_at, status, content_type, text, links, attachments, metadata)
        )

        for link in links:
            if link not in seen and len(seen) + len(queue) < max_pages * 3:
                queue.append(link)

        for attachment in attachments:
            att_url = normalize_url(attachment["url"])
            if att_url in attachment_seen or len(attachment_seen) >= max_attachments:
                continue
            attachment_seen.add(att_url)
            try:
                att_response = fetch(session, att_url)
                att_type = att_response.headers.get("content-type", "")
                att_status = str(att_response.status_code)
                filename = attachment_filename(att_url, att_type, attachment.get("label") or "")
                path = ATTACHMENT_DIR / filename
                path.write_bytes(att_response.content)
                is_html_gate = "html" in att_type.lower() and (
                    "附件下载" in att_response.text[:1000] or "验证码" in att_response.text[:2000]
                )
                is_pdf = not is_html_gate and (path.suffix.lower() == ".pdf" or "pdf" in att_type.lower())
                text_att = read_pdf_text(path) if is_pdf else ""
                docs.append(
                    Document(
                        stable_id(att_url),
                        att_url,
                        attachment.get("label") or Path(urlparse(att_url).path).name or att_url,
                        "attachment",
                        fetched_at,
                        att_status,
                        att_type,
                        text_att,
                        [],
                        [],
                        {
                            "parent_url": url,
                            "local_path": str(path),
                            "downloaded": not is_html_gate and att_response.status_code == 200,
                            "is_pdf": is_pdf,
                            "requires_captcha": is_html_gate,
                        },
                    )
                )
            except Exception as exc:
                docs.append(
                    Document(
                        stable_id(att_url),
                        att_url,
                        attachment.get("label") or att_url,
                        "attachment",
                        fetched_at,
                        f"error:{type(exc).__name__}",
                        "",
                        "",
                        [],
                        [],
                        {"parent_url": url, "downloaded": False, "error": str(exc)},
                    )
                )
            time.sleep(delay)

        time.sleep(delay)

    return docs


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl public Shanghai University finance office pages for local RAG.")
    parser.add_argument("--max-pages", type=int, default=250)
    parser.add_argument("--max-attachments", type=int, default=120)
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument("--start-url", action="append", default=[])
    args = parser.parse_args()

    start_urls = args.start_url or DEFAULT_START_URLS
    docs = crawl(args.max_pages, args.max_attachments, args.delay, start_urls)
    save_jsonl(DOCS_PATH, docs)
    manifest = {
        "base_url": BASE_URL,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "document_count": len(docs),
        "page_count": sum(1 for d in docs if d.source_type == "page"),
        "attachment_count": sum(1 for d in docs if d.source_type == "attachment"),
        "documents_path": str(DOCS_PATH),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
