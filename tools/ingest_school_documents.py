#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from lxml import html
from pypdf import PdfReader

try:
    from docx import Document as DocxDocument
except ImportError:  # pragma: no cover - dependency is optional at runtime.
    DocxDocument = None

try:
    import openpyxl
except ImportError:  # pragma: no cover - dependency is optional at runtime.
    openpyxl = None

try:
    import xlrd
except ImportError:  # pragma: no cover - dependency is optional at runtime.
    xlrd = None


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = ROOT / "data/school_knowledge"
DEFAULT_INPUTS = [
    ROOT / "data/cwc/raw",
    ROOT / "data/cwc/attachments",
    ROOT / "data/cwc/attachments_retry",
    ROOT / "data/cwc/browser_downloads",
    ROOT / "data/xssf_portal/raw",
    ROOT / "tmp/pdfs",
    ROOT / "samples",
]
RULES_PATH = ROOT / "data/rules/reimbursement_rules.json"
LLM_CONFIG_PATH = ROOT / "data/settings/rag_llm.json"

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".doc",
    ".txt",
    ".md",
    ".html",
    ".htm",
    ".jsp",
    ".xls",
    ".xlsx",
    ".pptx",
}
SKIP_DIRS = {
    ".git",
    ".playwright-cli",
    "__pycache__",
    "node_modules",
    "output",
    ".venv",
    "venv",
}

KNOWLEDGE_PATTERNS = {
    "policy_rule": [
        "管理办法",
        "规定",
        "制度",
        "细则",
        "暂行办法",
        "财经纪律",
        "应当",
        "不得",
        "严禁",
        "按照",
    ],
    "operation_guide": [
        "操作",
        "流程",
        "步骤",
        "登录",
        "系统",
        "填报",
        "提交",
        "预审",
        "审批",
        "预约",
        "打印",
    ],
    "reimbursement_materials": [
        "报销材料",
        "所需材料",
        "附件",
        "清单",
        "发票",
        "支付记录",
        "审批单",
        "结算单",
        "合同",
    ],
    "form_template": [
        "模板",
        "表格",
        "申请表",
        "审批表",
        "结算单",
        "下载",
        "填表说明",
    ],
    "faq": [
        "常见问题",
        "问答",
        "FAQ",
        "热点问答",
        "如何",
        "怎么办",
    ],
    "announcement": [
        "通知",
        "公告",
        "公示",
        "名单",
        "结算通知",
    ],
    "financial_account": [
        "银行账号",
        "开户行",
        "户名",
        "税号",
        "纳税人识别号",
        "开票信息",
        "增值税",
    ],
}

BASE_KEYWORDS = {
    "上海大学",
    "财务处",
    "智能报销",
    "网上报销",
    "日常报销",
    "差旅报销",
    "国内差旅",
    "市内差旅",
    "出差审批单",
    "差旅费结算单",
    "版面费",
    "出版费",
    "审稿费",
    "外币支付",
    "付款记录",
    "公务卡",
    "支付记录",
    "办公用品",
    "耗材",
    "电脑配件",
    "明细清单",
    "销售清单",
    "材料费",
    "服务合同",
    "测试化验加工费",
    "公务接待",
    "邀请函",
    "信息服务费",
    "发票",
    "附件",
    "审批",
    "预审",
    "借款",
    "冲账",
    "经费项目",
    "预算项目",
    "支付信息",
}


@dataclass
class SourceUnit:
    kind: str
    index: int
    text: str


@dataclass
class ExtractedDocument:
    doc_id: str
    source_uri: str
    source_path: str
    file_name: str
    file_ext: str
    source_type: str
    content_type: str
    title: str
    text: str
    text_sha256: str
    text_length: int
    extraction_method: str
    extracted_at: str
    units: list[SourceUnit]
    metadata: dict[str, Any]
    quality: dict[str, Any]


@dataclass
class KnowledgeChunk:
    schema_version: int
    chunk_id: str
    doc_id: str
    chunk_index: int
    file_name: str
    source_uri: str
    source_path: str
    source_type: str
    content_type: str
    title: str
    text: str
    text_length: int
    text_sha256: str
    knowledge_type: str
    knowledge_type_confidence: float
    reimbursement_types: list[dict[str, Any]]
    keywords: list[str]
    summary: str
    metadata: dict[str, Any]
    quality: dict[str, Any]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_id(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def clean_text(text: str) -> str:
    text = text.replace("\xa0", " ").replace("\u3000", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def read_text_with_fallback(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "gbk", "big5", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def split_paragraph_units(text: str, kind: str = "paragraph") -> list[SourceUnit]:
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    if not paragraphs:
        paragraphs = [p.strip() for p in text.splitlines() if p.strip()]
    return [SourceUnit(kind=kind, index=i + 1, text=p) for i, p in enumerate(paragraphs)]


def strip_html_noise(tree: html.HtmlElement) -> None:
    for node in tree.xpath("//script|//style|//noscript|//iframe|//svg"):
        parent = node.getparent()
        if parent is not None:
            parent.remove(node)


def extract_html_bytes(body: bytes, source_uri: str) -> tuple[str, str, list[SourceUnit], dict[str, Any]]:
    tree = html.fromstring(body, base_url=source_uri)
    strip_html_noise(tree)
    title_parts = [t.strip() for t in tree.xpath("//title/text()") if t.strip()]
    h1_parts = [t.strip() for t in tree.xpath("//h1//text()|//*[contains(@class,'title')]//text()") if t.strip()]
    title = h1_parts[0] if h1_parts else (title_parts[0] if title_parts else Path(urlparse(source_uri).path).name)

    candidates: list[html.HtmlElement] = []
    for xpath in (
        "//*[contains(@class,'vsb_content') or contains(@class,'v_news_content')]",
        "//*[contains(@id,'ArtDetail') or contains(@id,'CalendarDetail')]",
        "//*[contains(@class,'article') or contains(@class,'Article') or contains(@class,'news_detail')]",
        "//*[contains(@id,'content') or contains(@class,'content')]",
        "//body",
    ):
        candidates = [node for node in tree.xpath(xpath) if len(clean_text(node.text_content())) >= 40]
        if candidates:
            break
    root = max(candidates, key=lambda node: len(clean_text(node.text_content()))) if candidates else tree
    text = clean_text(root.text_content())
    links = []
    for a in tree.xpath("//a[@href]"):
        href = str(a.get("href") or "").strip()
        label = clean_text(a.text_content())
        if href:
            links.append({"href": href, "label": label[:160]})
    metadata = {
        "html_title": title_parts[0] if title_parts else "",
        "links": links[:200],
        "published_date": extract_date(text),
    }
    return title, text, split_paragraph_units(text), metadata


def extract_pdf(path: Path) -> tuple[str, str, list[SourceUnit], dict[str, Any], str]:
    reader = PdfReader(str(path))
    units: list[SourceUnit] = []
    for page_number, page in enumerate(reader.pages, 1):
        page_text = clean_text(page.extract_text() or "")
        if page_text:
            units.append(SourceUnit(kind="page", index=page_number, text=page_text))
    text = "\n\n".join(f"--- page {unit.index} ---\n{unit.text}" for unit in units)
    metadata = {"page_count": len(reader.pages), "extracted_page_count": len(units)}
    return first_heading(text) or path.stem, text, units, metadata, "pypdf"


def extract_docx(path: Path) -> tuple[str, str, list[SourceUnit], dict[str, Any], str]:
    if DocxDocument is None:
        raise RuntimeError("python-docx is not installed")
    doc = DocxDocument(str(path))
    blocks: list[str] = []
    for paragraph in doc.paragraphs:
        value = clean_text(paragraph.text)
        if value:
            blocks.append(value)
    for table in doc.tables:
        for row in table.rows:
            cells = [clean_text(cell.text).replace("\n", " / ") for cell in row.cells]
            row_text = " | ".join(cell for cell in cells if cell)
            if row_text:
                blocks.append(row_text)
    text = clean_text("\n\n".join(blocks))
    metadata = {"paragraph_count": len(doc.paragraphs), "table_count": len(doc.tables)}
    return path.stem, text, split_paragraph_units(text), metadata, "python-docx"


def extract_doc_with_textutil(path: Path) -> tuple[str, str, list[SourceUnit], dict[str, Any], str]:
    textutil = "/usr/bin/textutil"
    if Path(textutil).exists():
        result = subprocess.run(
            [textutil, "-convert", "txt", "-stdout", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0 and result.stdout.strip():
            text = clean_text(result.stdout)
            return first_heading(text) or path.stem, text, split_paragraph_units(text), {"converter": textutil}, "textutil"

    soffice = find_soffice()
    if soffice:
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = subprocess.run(
                [
                    soffice,
                    "--headless",
                    "--convert-to",
                    "txt:Text",
                    "--outdir",
                    tmp_dir,
                    str(path),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=90,
            )
            txt_path = Path(tmp_dir) / f"{path.stem}.txt"
            if result.returncode == 0 and txt_path.exists():
                text = clean_text(read_text_with_fallback(txt_path))
                return first_heading(text) or path.stem, text, split_paragraph_units(text), {"converter": soffice}, "soffice"

    raise RuntimeError("no available .doc converter found")


def extract_xlsx(path: Path) -> tuple[str, str, list[SourceUnit], dict[str, Any], str]:
    if openpyxl is None:
        raise RuntimeError("openpyxl is not installed")
    wb = openpyxl.load_workbook(str(path), data_only=True, read_only=True)
    rows: list[str] = []
    sheet_count = 0
    for sheet in wb.worksheets:
        sheet_count += 1
        rows.append(f"--- sheet: {sheet.title} ---")
        for row in sheet.iter_rows(values_only=True):
            values = [clean_text(str(value)) for value in row if value is not None and clean_text(str(value))]
            if values:
                rows.append(" | ".join(values))
    text = clean_text("\n".join(rows))
    return first_heading(text) or path.stem, text, split_paragraph_units(text), {"sheet_count": sheet_count}, "openpyxl"


def extract_xls(path: Path) -> tuple[str, str, list[SourceUnit], dict[str, Any], str]:
    if xlrd is None:
        raise RuntimeError("xlrd is not installed")
    wb = xlrd.open_workbook(str(path))
    rows: list[str] = []
    for sheet in wb.sheets():
        rows.append(f"--- sheet: {sheet.name} ---")
        for row_idx in range(sheet.nrows):
            values = []
            for col_idx in range(sheet.ncols):
                value = sheet.cell_value(row_idx, col_idx)
                if value not in ("", None):
                    values.append(clean_text(str(value)))
            if values:
                rows.append(" | ".join(values))
    text = clean_text("\n".join(rows))
    return first_heading(text) or path.stem, text, split_paragraph_units(text), {"sheet_count": wb.nsheets}, "xlrd"


def extract_pptx(path: Path) -> tuple[str, str, list[SourceUnit], dict[str, Any], str]:
    slides: list[SourceUnit] = []
    with zipfile.ZipFile(path) as zf:
        names = sorted(
            (name for name in zf.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)),
            key=lambda value: int(re.search(r"slide(\d+)\.xml", value).group(1)),
        )
        for idx, name in enumerate(names, 1):
            root = html.fromstring(zf.read(name))
            text = clean_text("\n".join(root.xpath("//*[local-name()='t']/text()")))
            if text:
                slides.append(SourceUnit(kind="slide", index=idx, text=text))
    text = "\n\n".join(f"--- slide {unit.index} ---\n{unit.text}" for unit in slides)
    return first_heading(text) or path.stem, text, slides, {"slide_count": len(slides)}, "pptx-xml"


def find_soffice() -> str:
    candidates = [
        os.getenv("SOFFICE_BIN", ""),
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        str(Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/bin/soffice"),
        "soffice",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        if "/" in candidate and Path(candidate).exists():
            return candidate
        if "/" not in candidate:
            result = subprocess.run(["/bin/zsh", "-lc", f"command -v {candidate}"], capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
    return ""


def extract_text_like(path: Path) -> tuple[str, str, list[SourceUnit], dict[str, Any], str]:
    text = clean_text(read_text_with_fallback(path))
    title = first_heading(text) or path.stem
    return title, text, split_paragraph_units(text), {"line_count": len(text.splitlines())}, "plain-text"


def extract_local_file(path: Path) -> ExtractedDocument:
    source_uri = str(path.resolve())
    file_ext = path.suffix.lower()
    content_type = content_type_for_ext(file_ext)
    extracted_at = now_iso()
    metadata: dict[str, Any] = {
        "file_size": path.stat().st_size,
        "modified_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
    }
    quality: dict[str, Any] = {"status": "ok", "needs_review": False, "review_reasons": []}
    title = path.stem
    text = ""
    units: list[SourceUnit] = []
    method = ""

    try:
        if file_ext == ".pdf":
            title, text, units, extra, method = extract_pdf(path)
        elif file_ext == ".docx":
            title, text, units, extra, method = extract_docx(path)
        elif file_ext == ".doc":
            title, text, units, extra, method = extract_doc_with_textutil(path)
        elif file_ext == ".xlsx":
            title, text, units, extra, method = extract_xlsx(path)
        elif file_ext == ".xls":
            title, text, units, extra, method = extract_xls(path)
        elif file_ext == ".pptx":
            title, text, units, extra, method = extract_pptx(path)
        elif file_ext in {".html", ".htm", ".jsp"}:
            title, text, units, extra = extract_html_bytes(path.read_bytes(), source_uri)
            method = "lxml-html"
        else:
            title, text, units, extra, method = extract_text_like(path)
        metadata.update(extra)
    except Exception as exc:
        quality["status"] = "error"
        quality["needs_review"] = True
        quality["review_reasons"].append(f"extract_failed:{type(exc).__name__}:{exc}")
        method = method or "unknown"

    text = clean_text(text)
    quality.update(quality_flags(text, metadata))
    doc_id = stable_id(source_uri)
    return ExtractedDocument(
        doc_id=doc_id,
        source_uri=source_uri,
        source_path=source_uri,
        file_name=path.name,
        file_ext=file_ext,
        source_type="local_file",
        content_type=content_type,
        title=title or path.stem,
        text=text,
        text_sha256=sha256_text(text),
        text_length=len(text),
        extraction_method=method,
        extracted_at=extracted_at,
        units=units,
        metadata=metadata,
        quality=quality,
    )


def extract_url(url: str, timeout: int = 30) -> ExtractedDocument:
    extracted_at = now_iso()
    headers = {"User-Agent": "SHU-Reimbursement-Agent/0.1 (+local knowledge ingestion)"}
    quality: dict[str, Any] = {"status": "ok", "needs_review": False, "review_reasons": []}
    title = url
    text = ""
    units: list[SourceUnit] = []
    metadata: dict[str, Any] = {}
    content_type = ""
    method = "requests"
    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        content_type = response.headers.get("content-type", "")
        metadata.update(
            {
                "http_status": response.status_code,
                "final_url": response.url,
                "headers_content_type": content_type,
            }
        )
        response.raise_for_status()
        if "pdf" in content_type.lower() or urlparse(response.url).path.lower().endswith(".pdf"):
            with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
                tmp.write(response.content)
                tmp.flush()
                title, text, units, extra, method = extract_pdf(Path(tmp.name))
                metadata.update(extra)
                method = "requests+pypdf"
        elif "html" in content_type.lower() or urlparse(response.url).path.lower().endswith((".html", ".htm", ".jsp", "")):
            title, text, units, extra = extract_html_bytes(response.content, response.url)
            metadata.update(extra)
            method = "requests+lxml-html"
        else:
            text = clean_text(response.text)
            title = first_heading(text) or Path(urlparse(response.url).path).name or response.url
            units = split_paragraph_units(text)
            method = "requests+plain-text"
    except Exception as exc:
        quality["status"] = "error"
        quality["needs_review"] = True
        quality["review_reasons"].append(f"fetch_or_extract_failed:{type(exc).__name__}:{exc}")

    text = clean_text(text)
    quality.update(quality_flags(text, metadata))
    parsed_name = Path(urlparse(url).path).name or stable_id(url)
    return ExtractedDocument(
        doc_id=stable_id(url),
        source_uri=url,
        source_path=url,
        file_name=parsed_name,
        file_ext=Path(parsed_name).suffix.lower(),
        source_type="web_url",
        content_type=content_type,
        title=title,
        text=text,
        text_sha256=sha256_text(text),
        text_length=len(text),
        extraction_method=method,
        extracted_at=extracted_at,
        units=units,
        metadata=metadata,
        quality=quality,
    )


def quality_flags(text: str, metadata: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    if not text.strip():
        reasons.append("no_extractable_text")
    elif len(text) < 80:
        reasons.append("short_text")
    sample = text[:2000]
    if "验证码" in sample or "captcha" in sample.lower():
        reasons.append("may_be_captcha_or_block_page")
    if metadata.get("page_count") and not metadata.get("extracted_page_count"):
        reasons.append("pdf_has_no_extractable_text")
    return {
        "char_count": len(text),
        "needs_review": bool(reasons),
        "review_reasons": reasons,
    }


def first_heading(text: str) -> str:
    for line in text.splitlines():
        line = line.strip(" #\t")
        if re.fullmatch(r"-+\s*page\s+\d+\s*-+", line, flags=re.IGNORECASE):
            continue
        if re.fullmatch(r"[0-9a-f]{12,}\.?", line, flags=re.IGNORECASE):
            continue
        if 3 <= len(line) <= 80:
            return line
    return ""


def extract_date(text: str) -> str:
    match = re.search(r"(20\d{2})[-./年](\d{1,2})[-./月](\d{1,2})", text)
    if not match:
        return ""
    y, m, d = match.groups()
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"


def content_type_for_ext(ext: str) -> str:
    return {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".doc": "application/msword",
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".html": "text/html",
        ".htm": "text/html",
        ".jsp": "text/html",
        ".xls": "application/vnd.ms-excel",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }.get(ext, "application/octet-stream")


def load_reimbursement_rules() -> list[dict[str, Any]]:
    if not RULES_PATH.exists():
        return []
    payload = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    return payload.get("supported_types") or payload.get("reimbursement_types") or []


def keyword_vocabulary(rules: list[dict[str, Any]]) -> set[str]:
    vocabulary = set(BASE_KEYWORDS)
    for rule in rules:
        for field in ("id", "name", "school_form_hint"):
            value = rule.get(field)
            if value:
                vocabulary.add(str(value))
        for field in ("keywords", "aliases", "policy_queries", "search_queries"):
            for item in rule.get(field, []):
                for part in re.split(r"[\s,，、/]+", str(item)):
                    if len(part) >= 2:
                        vocabulary.add(part)
        for checklist in rule.get("checklist", []):
            if checklist.get("name"):
                vocabulary.add(str(checklist["name"]))
            for item in checklist.get("keywords", []):
                if len(str(item)) >= 2:
                    vocabulary.add(str(item))
    return vocabulary


def detect_knowledge_type(text: str, title: str) -> tuple[str, float]:
    haystack = f"{title}\n{text[:2400]}".lower()
    scores: Counter[str] = Counter()
    for knowledge_type, patterns in KNOWLEDGE_PATTERNS.items():
        for pattern in patterns:
            if pattern.lower() in haystack:
                scores[knowledge_type] += 2 if pattern in title else 1
    if not scores:
        return "unknown", 0.2
    knowledge_type, score = scores.most_common(1)[0]
    confidence = min(0.95, 0.45 + score / 12)
    return knowledge_type, round(confidence, 2)


def detect_reimbursement_types(text: str, title: str, rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    haystack = f"{title}\n{text[:5000]}".lower()
    matches: list[dict[str, Any]] = []
    for rule in rules:
        keywords = set(str(item) for item in rule.get("keywords", []))
        if rule.get("name"):
            keywords.add(str(rule["name"]))
        if rule.get("school_form_hint"):
            keywords.add(str(rule["school_form_hint"]))
        for checklist in rule.get("checklist", []):
            if checklist.get("name"):
                keywords.add(str(checklist["name"]))
            keywords.update(str(item) for item in checklist.get("keywords", []))
        hit_keywords = sorted({kw for kw in keywords if kw and kw.lower() in haystack}, key=lambda value: (-len(value), value))
        if not hit_keywords:
            continue
        score = len(hit_keywords)
        matches.append(
            {
                "id": rule.get("id", ""),
                "name": rule.get("name", ""),
                "score": score,
                "confidence": round(min(0.96, 0.35 + score / 10), 2),
                "matched_keywords": hit_keywords[:12],
            }
        )
    return sorted(matches, key=lambda item: (-item["score"], item["name"]))[:5]


def extract_keywords(text: str, title: str, vocabulary: set[str], limit: int = 40) -> list[str]:
    haystack = f"{title}\n{text}".lower()
    hits = [keyword for keyword in vocabulary if keyword.lower() in haystack]
    hits.extend(re.findall(r"20\d{2}[-./年]\d{1,2}[-./月]\d{1,2}", text))
    hits.extend(re.findall(r"[a-zA-Z][a-zA-Z0-9_.+-]{2,}", text))
    seen: set[str] = set()
    result: list[str] = []
    for keyword in sorted(hits, key=lambda value: (-len(value), value.lower())):
        normalized = keyword.strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
        if len(result) >= limit:
            break
    return result


def summarize_locally(text: str, title: str, max_chars: int = 120) -> str:
    for part in [title, *re.split(r"[。！？\n]", text)]:
        part = clean_text(part)
        if len(part) >= 12:
            return part[:max_chars]
    return clean_text(text)[:max_chars]


def iter_local_files(inputs: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in inputs:
        if raw.startswith(("http://", "https://")):
            continue
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = (ROOT / path).resolve()
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(path)
        elif path.is_dir():
            for child in path.rglob("*"):
                if any(part in SKIP_DIRS for part in child.parts):
                    continue
                if child.is_file() and child.suffix.lower() in SUPPORTED_EXTENSIONS:
                    files.append(child)
    return sorted(set(files))


def iter_urls(inputs: list[str], explicit_urls: list[str]) -> list[str]:
    urls = [raw for raw in inputs if raw.startswith(("http://", "https://"))]
    urls.extend(explicit_urls)
    return sorted(set(urls))


def split_long_text(text: str, max_chars: int, overlap: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = max(0, end - overlap)
    return chunks


def build_chunk_payloads(doc: ExtractedDocument, max_chars: int, overlap: int) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    units = doc.units or split_paragraph_units(doc.text)
    current_parts: list[str] = []
    current_locators: list[dict[str, int | str]] = []

    def flush() -> None:
        nonlocal current_parts, current_locators
        if not current_parts:
            return
        payloads.append({"text": "\n\n".join(current_parts).strip(), "locators": current_locators})
        current_parts = []
        current_locators = []

    for unit in units:
        unit_text = unit.text.strip()
        if not unit_text:
            continue
        locator = {"kind": unit.kind, "index": unit.index}
        if len(unit_text) > max_chars:
            flush()
            for sub_index, sub_text in enumerate(split_long_text(unit_text, max_chars, overlap), 1):
                payloads.append(
                    {
                        "text": sub_text.strip(),
                        "locators": [{**locator, "part": sub_index}],
                    }
                )
            continue
        candidate = "\n\n".join([*current_parts, unit_text]).strip()
        if current_parts and len(candidate) > max_chars:
            flush()
        current_parts.append(unit_text)
        current_locators.append(locator)
    flush()
    return [payload for payload in payloads if payload["text"]]


def read_llm_config(args: argparse.Namespace) -> dict[str, Any]:
    saved: dict[str, Any] = {}
    if LLM_CONFIG_PATH.exists():
        try:
            saved = json.loads(LLM_CONFIG_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            saved = {}
    provider = args.llm_provider or os.getenv("RAG_LLM_PROVIDER") or saved.get("provider") or "deepseek"
    base_url = (
        args.llm_base_url
        or os.getenv("RAG_LLM_BASE_URL")
        or saved.get("base_url")
        or ("https://api.deepseek.com" if provider == "deepseek" else "")
    )
    model = args.llm_model or os.getenv("RAG_LLM_MODEL") or saved.get("model") or ("deepseek-v4-pro" if provider == "deepseek" else "")
    api_key = args.llm_api_key or os.getenv("RAG_LLM_API_KEY") or saved.get("api_key") or ""
    return {
        "provider": provider,
        "base_url": str(base_url).rstrip("/"),
        "model": model,
        "api_key": api_key,
        "ready": bool(base_url and model and api_key),
    }


def llm_enrich_chunk(chunk: KnowledgeChunk, config: dict[str, Any]) -> KnowledgeChunk:
    system = (
        "你是学校财务报销知识库清洗助手。"
        "只根据用户给出的片段判断，不要补充片段之外的政策。"
        "必须输出 JSON，不要输出 Markdown。"
    )
    user = {
        "task": "为知识库分片补充元信息",
        "allowed_knowledge_types": list(KNOWLEDGE_PATTERNS.keys()) + ["unknown"],
        "required_json_fields": [
            "knowledge_type",
            "reimbursement_types",
            "keywords",
            "summary",
            "confidence",
            "needs_review",
            "review_reasons",
        ],
        "file_name": chunk.file_name,
        "title": chunk.title,
        "text": chunk.text[:3600],
    }
    payload = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
        ],
        "temperature": 0.0,
    }
    request = urllib.request.Request(
        f"{config['base_url']}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        raw = json.loads(response.read().decode("utf-8"))
    content = raw["choices"][0]["message"]["content"].strip()
    content = re.sub(r"^```(?:json)?|```$", "", content, flags=re.MULTILINE).strip()
    enriched = json.loads(content)
    if enriched.get("knowledge_type"):
        chunk.knowledge_type = str(enriched["knowledge_type"])
    if enriched.get("confidence") is not None:
        chunk.knowledge_type_confidence = float(enriched["confidence"])
    if isinstance(enriched.get("reimbursement_types"), list):
        chunk.reimbursement_types = [
            item if isinstance(item, dict) else {"name": str(item)}
            for item in enriched["reimbursement_types"]
        ][:5]
    if isinstance(enriched.get("keywords"), list):
        chunk.keywords = [str(item) for item in enriched["keywords"] if str(item).strip()][:40]
    if enriched.get("summary"):
        chunk.summary = str(enriched["summary"])[:240]
    chunk.metadata["llm_enriched"] = True
    chunk.metadata["llm_provider"] = config["provider"]
    chunk.metadata["llm_model"] = config["model"]
    if enriched.get("needs_review"):
        chunk.quality["needs_review"] = True
    if isinstance(enriched.get("review_reasons"), list):
        existing = list(chunk.quality.get("review_reasons", []))
        existing.extend(str(item) for item in enriched["review_reasons"] if str(item).strip())
        chunk.quality["review_reasons"] = sorted(set(existing))
    return chunk


def build_chunks(
    docs: list[ExtractedDocument],
    rules: list[dict[str, Any]],
    vocabulary: set[str],
    max_chars: int,
    overlap: int,
    llm_config: dict[str, Any] | None,
    llm_limit: int,
) -> tuple[list[KnowledgeChunk], list[str]]:
    chunks: list[KnowledgeChunk] = []
    warnings: list[str] = []
    llm_calls = 0
    for doc in docs:
        for chunk_index, payload in enumerate(build_chunk_payloads(doc, max_chars=max_chars, overlap=overlap)):
            text = payload["text"]
            knowledge_type, confidence = detect_knowledge_type(text, doc.title)
            reimbursement_types = detect_reimbursement_types(text, doc.title, rules)
            metadata = {
                "file_ext": doc.file_ext,
                "document_metadata": doc.metadata,
                "source_locators": payload["locators"],
                "llm_enriched": False,
            }
            quality = dict(doc.quality)
            quality["chunk_char_count"] = len(text)
            chunk = KnowledgeChunk(
                schema_version=1,
                chunk_id=f"{doc.doc_id}:{chunk_index}",
                doc_id=doc.doc_id,
                chunk_index=chunk_index,
                file_name=doc.file_name,
                source_uri=doc.source_uri,
                source_path=doc.source_path,
                source_type=doc.source_type,
                content_type=doc.content_type,
                title=doc.title,
                text=text,
                text_length=len(text),
                text_sha256=sha256_text(text),
                knowledge_type=knowledge_type,
                knowledge_type_confidence=confidence,
                reimbursement_types=reimbursement_types,
                keywords=extract_keywords(text, doc.title, vocabulary),
                summary=summarize_locally(text, doc.title),
                metadata=metadata,
                quality=quality,
            )
            if llm_config and llm_config["ready"] and (llm_limit <= 0 or llm_calls < llm_limit):
                try:
                    chunk = llm_enrich_chunk(chunk, llm_config)
                    llm_calls += 1
                except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError) as exc:
                    warnings.append(f"llm_enrich_failed:{chunk.chunk_id}:{type(exc).__name__}")
                    chunk.quality["needs_review"] = True
                    chunk.quality.setdefault("review_reasons", []).append(f"llm_enrich_failed:{type(exc).__name__}")
            chunks.append(chunk)
    return chunks, warnings


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def build_manifest(
    docs: list[ExtractedDocument],
    chunks: list[KnowledgeChunk],
    warnings: list[str],
    args: argparse.Namespace,
    out_dir: Path,
    llm_config: dict[str, Any],
) -> dict[str, Any]:
    quality_counts = Counter(doc.quality.get("status", "unknown") for doc in docs)
    knowledge_counts = Counter(chunk.knowledge_type for chunk in chunks)
    source_counts = Counter(doc.source_type for doc in docs)
    review_count = sum(1 for chunk in chunks if chunk.quality.get("needs_review"))
    return {
        "schema_version": 1,
        "generated_at": now_iso(),
        "inputs": args.inputs,
        "out_dir": str(out_dir),
        "documents_path": str(out_dir / "documents.jsonl"),
        "chunks_jsonl_path": str(out_dir / "chunks.jsonl"),
        "chunks_json_path": str(out_dir / "chunks.json"),
        "document_count": len(docs),
        "chunk_count": len(chunks),
        "review_chunk_count": review_count,
        "source_type_counts": dict(source_counts),
        "extraction_status_counts": dict(quality_counts),
        "knowledge_type_counts": dict(knowledge_counts),
        "llm": {
            "requested": bool(args.use_llm),
            "ready": bool(llm_config.get("ready")),
            "provider": llm_config.get("provider", ""),
            "model": llm_config.get("model", ""),
            "base_url": llm_config.get("base_url", ""),
            "api_key_present": bool(llm_config.get("api_key")),
        },
        "warnings": warnings,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract messy school PDF/Word/text/web documents into chunked JSON for RAG."
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        help="Files, folders, or URLs. Defaults to data/cwc/raw, data/cwc/attachments, tmp/pdfs, samples.",
    )
    parser.add_argument("--url", action="append", default=[], help="Extra web URL to fetch. Can be used multiple times.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--max-chars", type=int, default=900)
    parser.add_argument("--overlap", type=int, default=120)
    parser.add_argument("--use-llm", action="store_true", help="Use DeepSeek/OpenAI-compatible model to enrich chunk metadata.")
    parser.add_argument("--llm-limit", type=int, default=0, help="Max LLM-enriched chunks. 0 means no limit.")
    parser.add_argument("--llm-provider", default="")
    parser.add_argument("--llm-base-url", default="")
    parser.add_argument("--llm-model", default="")
    parser.add_argument("--llm-api-key", default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.inputs:
        args.inputs = [str(path) for path in DEFAULT_INPUTS if path.exists()]
    out_dir = args.out_dir if args.out_dir.is_absolute() else (ROOT / args.out_dir)
    rules = load_reimbursement_rules()
    vocabulary = keyword_vocabulary(rules)
    warnings: list[str] = []

    local_files = iter_local_files(args.inputs)
    urls = iter_urls(args.inputs, args.url)
    docs: list[ExtractedDocument] = []
    for path in local_files:
        docs.append(extract_local_file(path))
    for url in urls:
        docs.append(extract_url(url))

    docs = [doc for doc in docs if doc.quality.get("status") == "ok" or doc.text.strip()]
    llm_config = read_llm_config(args)
    if args.use_llm and not llm_config["ready"]:
        warnings.append("llm_requested_but_not_configured")
    chunks, chunk_warnings = build_chunks(
        docs=docs,
        rules=rules,
        vocabulary=vocabulary,
        max_chars=args.max_chars,
        overlap=args.overlap,
        llm_config=llm_config if args.use_llm else None,
        llm_limit=args.llm_limit,
    )
    warnings.extend(chunk_warnings)

    document_rows = []
    for doc in docs:
        row = asdict(doc)
        row.pop("units", None)
        row["chunk_ids"] = [chunk.chunk_id for chunk in chunks if chunk.doc_id == doc.doc_id]
        document_rows.append(row)
    chunk_rows = [asdict(chunk) for chunk in chunks]

    out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(out_dir / "documents.jsonl", document_rows)
    write_jsonl(out_dir / "chunks.jsonl", chunk_rows)
    (out_dir / "chunks.json").write_text(json.dumps(chunk_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = build_manifest(docs, chunks, warnings, args, out_dir, llm_config)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
