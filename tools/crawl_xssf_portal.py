#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from lxml import html


ROOT = Path("/Users/hao/Documents/自助报销Agent")
DATA_DIR = ROOT / "data/xssf_portal"
RAW_DIR = DATA_DIR / "raw"
ATTACHMENT_DIR = DATA_DIR / "attachments"
DOCS_PATH = DATA_DIR / "documents.jsonl"
MANIFEST_PATH = DATA_DIR / "crawl_manifest.json"

BASE_URL = "https://xssf.shu.edu.cn:8100/SFP_Share/"
INDEX_URL = urljoin(BASE_URL, "Home/Index")

TOP_MENUS = {
    "1ddc1240-5ff0-4968-967e-c0135bbcfa5a": "财务制度",
    "9d546264-f7db-41fb-844e-63dc1f4e9018": "通知公告",
    "aa25c173-b1d2-4e23-bdb0-afd45a6cc07b": "常用表格",
    "48f30067-1e53-4d5c-932e-51de473a7860": "财务通讯录",
}


@dataclass
class PortalDocument:
    id: str
    url: str
    title: str
    source_type: str
    fetched_at: str
    status: str
    content_type: str
    text: str
    links: list[dict]
    attachments: list[dict]
    metadata: dict


def stable_id(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]


def clean_text(text: str) -> str:
    text = text.replace("\xa0", " ").replace("\u3000", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def decode_response(response: requests.Response) -> str:
    return response.content.decode("utf-8", errors="replace")


def fetch(session: requests.Session, url: str, timeout: int = 25) -> requests.Response:
    return session.get(
        url,
        timeout=timeout,
        verify=False,
        headers={
            "User-Agent": "Mozilla/5.0 SHU-XSSF-Portal-Crawler/0.1",
            "Accept": "text/html,application/xhtml+xml,application/pdf,application/octet-stream,*/*;q=0.8",
        },
    )


def post_fragment(session: requests.Session, action: str, data: dict[str, str]) -> str:
    response = session.post(
        urljoin(BASE_URL, f"Home/{action}"),
        data=data,
        timeout=25,
        verify=False,
        headers={"User-Agent": "Mozilla/5.0 SHU-XSSF-Portal-Crawler/0.1", "X-Requested-With": "XMLHttpRequest"},
    )
    response.raise_for_status()
    return decode_response(response)


def parse_article_links(fragment: str, base_url: str, parent_menu: str) -> list[dict]:
    tree = html.fromstring(fragment, base_url=base_url)
    articles: list[dict] = []
    seen: set[str] = set()
    for a in tree.xpath("//a[@href]"):
        href = a.get("href") or ""
        parsed_path = urlparse(urljoin(base_url, href)).path
        if not parsed_path.endswith("/Home/Article"):
            continue
        url = urljoin(base_url, href)
        if url in seen:
            continue
        seen.add(url)
        title = clean_text(a.text_content())
        date = ""
        parent = a.getparent()
        if parent is not None:
            text = clean_text(parent.text_content())
            match = re.search(r"\[(20\d{2}-\d{2}-\d{2})\]", text)
            if match:
                date = match.group(1)
        articles.append({"url": url, "title": title, "published_date": date, "parent_menu": parent_menu})
    return articles


def discover_articles(session: requests.Session) -> tuple[list[dict], dict[str, str]]:
    articles: list[dict] = []
    submenus: dict[str, str] = {}
    seen_urls: set[str] = set()

    for top_id, top_name in TOP_MENUS.items():
        list_page = fetch(session, urljoin(BASE_URL, f"Home/Articles?m={top_id}"))
        list_text = decode_response(list_page)
        for submenu_id, submenu_name in re.findall(r"getart\('([0-9a-f-]+)'\);\">\s*([^<]+)</div>", list_text):
            submenus[submenu_id] = clean_text(submenu_name)

        fragments = [post_fragment(session, "Ctrl_AllArticles", {"m": top_id})]
        for submenu_id in [item[0] for item in re.findall(r"getart\('([0-9a-f-]+)'\);\">\s*([^<]+)</div>", list_text)]:
            fragments.append(post_fragment(session, "Ctrl_Articles", {"m": submenu_id, "pm": top_id}))
        fragments.append(post_fragment(session, "Ctrl_ArticleSummary", {"p_MenuID": top_id}))

        for fragment in fragments:
            for article in parse_article_links(fragment, BASE_URL, top_name):
                if article["url"] in seen_urls:
                    continue
                seen_urls.add(article["url"])
                articles.append(article)
    return articles, submenus


def is_attachment_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar", ".ppt", ".pptx"))


def extract_article(session: requests.Session, article: dict, fetched_at: str) -> PortalDocument:
    response = fetch(session, article["url"])
    status = str(response.status_code)
    content_type = response.headers.get("content-type", "")
    body = response.content
    raw_path = RAW_DIR / f"{stable_id(article['url'])}.html"
    raw_path.write_bytes(body)

    if response.status_code != 200:
        return PortalDocument(
            stable_id(article["url"]),
            article["url"],
            article.get("title") or article["url"],
            "xssf_article",
            fetched_at,
            status,
            content_type,
            "",
            [],
            [],
            {"raw_path": str(raw_path), "parent_menu": article.get("parent_menu", ""), "published_date": article.get("published_date", "")},
        )

    text = decode_response(response)
    tree = html.fromstring(text, base_url=article["url"])
    title_parts = [clean_text(t) for t in tree.xpath("//*[contains(@class,'s-articleTitle-detail')]//text()") if clean_text(t)]
    time_parts = [clean_text(t) for t in tree.xpath("//*[contains(@class,'s-articleTime-detail')]//text()") if clean_text(t)]
    content_nodes = tree.xpath("//*[contains(@class,'s-articleContent-detail') or contains(@class,'s-articleFile-detail')]")
    content_text = clean_text("\n".join(node.text_content() for node in content_nodes)) if content_nodes else clean_text(tree.text_content())
    links: list[dict] = []
    attachments: list[dict] = []
    for a in tree.xpath("//a[@href]"):
        href = a.get("href") or ""
        target = urljoin(article["url"], href)
        label = clean_text(a.text_content())
        item = {"url": target, "label": label}
        if is_attachment_url(target):
            attachments.append(item)
        else:
            links.append(item)
    return PortalDocument(
        stable_id(article["url"]),
        article["url"],
        title_parts[0] if title_parts else (article.get("title") or article["url"]),
        "xssf_article",
        fetched_at,
        status,
        content_type,
        content_text,
        links,
        attachments,
        {
            "raw_path": str(raw_path),
            "parent_menu": article.get("parent_menu", ""),
            "published_date": article.get("published_date", ""),
            "detail_time": time_parts[0] if time_parts else "",
        },
    )


def save_jsonl(path: Path, docs: list[PortalDocument]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for doc in docs:
            f.write(json.dumps(asdict(doc), ensure_ascii=False) + "\n")


def crawl(delay: float) -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    ATTACHMENT_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    fetched_at = datetime.now(timezone.utc).isoformat()

    articles, submenus = discover_articles(session)
    docs: list[PortalDocument] = []
    for article in articles:
        docs.append(extract_article(session, article, fetched_at))
        time.sleep(delay)

    save_jsonl(DOCS_PATH, docs)
    manifest = {
        "base_url": BASE_URL,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "article_count": len(articles),
        "document_count": len(docs),
        "top_menus": TOP_MENUS,
        "submenus": submenus,
        "documents_path": str(DOCS_PATH),
        "raw_dir": str(RAW_DIR),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl SHU xssf finance portal public article/document pages.")
    parser.add_argument("--delay", type=float, default=0.1)
    args = parser.parse_args()
    print(json.dumps(crawl(args.delay), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
