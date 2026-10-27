#!/usr/bin/env python3
"""Maintain public source snapshots. No authentication, model calls, or application state."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "skills/shu-reimbursement/references/knowledge/documents.jsonl"
MAX_BYTES = 5 * 1024 * 1024
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


def official_url(url: str) -> str:
    url = urldefrag(url.strip())[0]
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "cwc.shu.edu.cn" or parsed.username or parsed.password:
        raise ValueError("只接受 https://cwc.shu.edu.cn/ 的公开链接。")
    return url


class OfficialRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        official_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@dataclass
class Node:
    tag: str
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)

    def text(self) -> str:
        if self.tag in {"script", "style", "noscript"}:
            return ""
        return "\n".join(child.text() if isinstance(child, Node) else child for child in self.children)

    def all(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.all()


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs))
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, dict(attrs)))

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def clean(text: str) -> str:
    return "\n".join(line.strip() for line in text.replace("\xa0", " ").splitlines() if line.strip())


def parse_page(url: str, html: str, fetched_at: str) -> dict:
    parser = PageParser()
    parser.feed(html)
    nodes = list(parser.root.all())
    title = next((clean(node.text()) for node in nodes if node.tag == "title"), url)
    title = re.sub(r"[-_\s]*上海大学财务处.*$", "", title).strip() or url
    candidates = [node for node in nodes if any(marker in (node.attrs.get("id", "") + " " + node.attrs.get("class", "")) for marker in ("vsb_content", "v_news_content", "Article_Content"))]
    # A whole navigation page is not policy body text.
    text = clean(max(candidates, key=lambda node: len(node.text())).text()) if candidates else ""
    date = re.search(r"创建时间\s*[:：]\s*(\d{4}-\d{2}-\d{2})", clean(parser.root.text()))
    attachments = []
    seen = set()
    for node in nodes:
        if node.tag != "a" or "href" not in node.attrs:
            continue
        target = urljoin(url, node.attrs["href"])
        parsed = urlparse(target)
        if parsed.netloc != "cwc.shu.edu.cn" or not re.search(r"download\.jsp|/__local/|\.(pdf|docx?|xlsx?|rar|zip|pptx?)$", parsed.path, re.I):
            continue
        if parsed.scheme == "http":
            target = "https:" + target[5:]
        target = official_url(target)
        if target in seen:
            continue
        seen.add(target)
        attachments.append({"title": clean(node.text()) or parsed.path.rsplit("/", 1)[-1], "url": target})
    return {"id": hashlib.sha1(url.encode()).hexdigest()[:16], "title": title, "url": url,
            "source_type": "page", "category": "guide" if re.search("指南|手册|讲解|百问百答|演示", title) else "policy",
            "published_date": date.group(1) if date else "", "fetched_at": fetched_at,
            "effectivity": "unverified", "availability": "text_available" if len(text) >= 65 else "entry_only",
            "text": text, "attachments": attachments}


def fetch(url: str) -> dict:
    url = official_url(url)
    request = Request(url, headers={"User-Agent": "SHU-Reimbursement-Knowledge/1.0 (public documentation maintenance)"})
    with build_opener(OfficialRedirect()).open(request, timeout=20) as response:
        official_url(response.url)
        if response.headers.get_content_type() not in {"text/html", "application/xhtml+xml"}:
            raise ValueError("此链接不是 HTML 页面；请人工提取附件文字后使用 import-text。")
        raw = response.read(MAX_BYTES+1)
        if len(raw) > MAX_BYTES:
            raise ValueError("页面超过 5 MiB，未导入。")
        encoding = response.headers.get_content_charset() or "utf-8"
        text = raw.decode(encoding, errors="replace")
    if "请输入验证码" in text or "统一身份认证" in text:
        raise ValueError("页面需要验证码或认证，未读取或覆盖已有资料。")
    return parse_page(url, text, datetime.now(timezone.utc).isoformat())


def save(doc: dict, path: Path = DATA) -> None:
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    previous = next((item for item in records if item["url"] == doc["url"]), None)
    if previous:
        doc["id"] = previous["id"]
        # A previously obtained copy remains a historical source, not proof of current validity.
        if previous.get("public_asset"):
            doc["public_asset"] = previous["public_asset"]
    records = [item for item in records if item["url"] != doc["url"]] + [doc]
    payload = "".join(json.dumps(item, ensure_ascii=False, sort_keys=True)+"\n" for item in sorted(records, key=lambda item: item["id"]))
    temp = path.with_suffix(".tmp")
    temp.write_text(payload, encoding="utf-8")
    temp.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    refresh = commands.add_parser("refresh")
    refresh.add_argument("url")
    import_text = commands.add_parser("import-text")
    import_text.add_argument("--url", required=True)
    import_text.add_argument("--title", required=True)
    import_text.add_argument("--text", type=Path, required=True)
    import_text.add_argument("--ocr", action="store_true", help="标记扫描件 OCR 未逐页核验，不能直接据此引用数字和表格")
    args = parser.parse_args()
    try:
        if args.command == "refresh":
            doc = fetch(args.url)
        else:
            url = official_url(args.url)
            text = args.text.read_text(encoding="utf-8").strip()
            if len(text) < 65:
                raise ValueError("文字过短，不足以作为可读正文。")
            doc = {"id": hashlib.sha1(url.encode()).hexdigest()[:16], "title": args.title, "url": url,
                   "source_type": "attachment", "category": "policy", "published_date": "",
                   "fetched_at": datetime.now(timezone.utc).isoformat(), "effectivity": "unverified",
                   "availability": "text_available", "text": text, "attachments": [],
                   "text_quality": "ocr_unverified" if args.ocr else "extracted_unverified",
                   "extraction_method": "manual_text_import",
                   "provenance": {"acquisition": "manual_text_import", "downloaded_at": "unknown"}}
        save(doc)
        print(f"已更新快照：{doc['title']} [{doc['availability']}]。请核对 Git 差异和适用条件，然后运行 python3 tools/build.py。")
    except (OSError, ValueError) as exc:
        parser.exit(1, f"未更新资料：{exc}\n")


if __name__ == "__main__":
    main()
