#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path("/Users/hao/Documents/自助报销Agent")
DOCS_PATH = ROOT / "data/cwc/documents.jsonl"
INDEX_PATH = ROOT / "data/cwc/index.json"
RULES_PATH = ROOT / "data/rules/reimbursement_rules.json"

MIN_INDEXABLE_CHARS = 20
STOPWORDS = {
    "的",
    "了",
    "和",
    "与",
    "及",
    "或",
    "在",
    "是",
    "有",
    "为",
    "请",
    "需",
    "需要",
    "可以",
    "什么",
    "哪些",
    "怎么",
    "如何",
    "报销",
    "材料",
    "the",
    "and",
    "for",
    "with",
    "from",
}
STATIC_DOMAIN_KEYWORDS = {
    "上海大学",
    "财务处",
    "智能报销",
    "日常报销",
    "差旅报销",
    "国内差旅",
    "市内差旅",
    "出差审批单",
    "差旅费结算单",
    "版面费",
    "出版费",
    "审稿费",
    "录用通知",
    "外币支付",
    "付款记录",
    "公务卡",
    "消费记录",
    "银行转账",
    "办公用品",
    "耗材",
    "电脑配件",
    "明细清单",
    "销售清单",
    "材料费",
    "合同",
    "测试化验加工费",
    "测试费",
    "加工清单",
    "公务接待",
    "公务接待清单",
    "邀请函",
    "派出公函",
    "信息服务费",
    "服务合同",
    "发票",
    "增值税发票",
    "票据",
    "附件",
    "审批",
    "预审",
    "提交审批",
    "借款",
    "冲账",
    "经费项目",
    "预算项目",
    "支付信息",
}


@dataclass
class Chunk:
    id: str
    doc_id: str
    url: str
    title: str
    source_type: str
    text: str
    keywords: list[str]
    metadata: dict


def load_domain_keywords() -> set[str]:
    keywords = set(STATIC_DOMAIN_KEYWORDS)
    if not RULES_PATH.exists():
        return keywords
    try:
        payload = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return keywords
    for rule in payload.get("reimbursement_types", []):
        for field in ("name", "school_form_hint"):
            value = rule.get(field)
            if value:
                keywords.add(str(value))
        for value in rule.get("aliases", []):
            if value:
                keywords.add(str(value))
        for query in rule.get("search_queries", []):
            keywords.update(part.strip() for part in re.split(r"[\s,，、/]+", query) if len(part.strip()) >= 2)
        for item in rule.get("checklist", []):
            name = item.get("name")
            if name:
                keywords.add(str(name))
            keywords.update(str(value).strip() for value in item.get("keywords", []) if len(str(value).strip()) >= 2)
    return {keyword for keyword in keywords if len(keyword) >= 2}


DOMAIN_KEYWORDS = load_domain_keywords()


def normalize_text(text: str) -> str:
    text = text.lower().replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_keywords(text: str, limit: int = 80) -> list[str]:
    normalized = normalize_text(text)
    hits = [keyword for keyword in DOMAIN_KEYWORDS if keyword.lower() in normalized]
    hits.extend(re.findall(r"[a-z0-9_@.+-]{2,}", normalized))
    seen: set[str] = set()
    result: list[str] = []
    for keyword in sorted(hits, key=lambda value: (-len(value), value)):
        keyword = keyword.strip()
        if not keyword or keyword in STOPWORDS or keyword in seen:
            continue
        seen.add(keyword)
        result.append(keyword)
        if len(result) >= limit:
            break
    return result


def tokenize(text: str) -> list[str]:
    text = normalize_text(text)
    tokens: list[str] = []
    tokens.extend(token for token in re.findall(r"[a-z0-9_@.+-]{2,}", text) if token not in STOPWORDS)
    tokens.extend(re.findall(r"20\d{2}[-./年]\d{1,2}[-./月]\d{1,2}", text))
    for keyword in DOMAIN_KEYWORDS:
        if keyword.lower() in text:
            tokens.append(keyword)
    chinese = re.findall(r"[\u4e00-\u9fff]+", text)
    for block in chinese:
        if block in STOPWORDS:
            continue
        if len(block) <= 2:
            tokens.append(block)
            continue
        for n in (2, 3, 4):
            tokens.extend(
                block[i : i + n]
                for i in range(0, len(block) - n + 1)
                if block[i : i + n] not in STOPWORDS
            )
    return tokens


def split_text(text: str, max_chars: int = 900, overlap: int = 120) -> list[str]:
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    if not text:
        return []
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 <= max_chars:
            current = f"{current}\n\n{para}".strip()
        else:
            if current:
                chunks.append(current)
            while len(para) > max_chars:
                chunks.append(para[:max_chars])
                para = para[max_chars - overlap :]
            current = para
    if current:
        chunks.append(current)
    return chunks


def load_docs(path: Path) -> list[dict]:
    docs = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                docs.append(json.loads(line))
    return docs


def is_indexable_doc(doc: dict[str, Any]) -> bool:
    return len((doc.get("text") or "").strip()) >= MIN_INDEXABLE_CHARS


def corpus_quality_report(docs: list[dict[str, Any]], chunks: list[Chunk]) -> dict[str, Any]:
    indexed_doc_ids = {chunk.doc_id for chunk in chunks}
    source_types = Counter(doc.get("source_type") or "page" for doc in docs)
    indexed_source_types = Counter(chunk.source_type or "page" for chunk in chunks)
    status_counts = Counter(str(doc.get("status") or "") for doc in docs)
    empty_docs = [doc for doc in docs if not (doc.get("text") or "").strip()]
    short_docs = [
        doc
        for doc in docs
        if (doc.get("text") or "").strip() and not is_indexable_doc(doc)
    ]
    empty_by_source = Counter(doc.get("source_type") or "page" for doc in empty_docs)
    skipped = [
        {
            "id": doc.get("id", ""),
            "title": doc.get("title", "")[:120],
            "url": doc.get("url", ""),
            "source_type": doc.get("source_type") or "page",
            "status": doc.get("status", ""),
            "requires_captcha": bool((doc.get("metadata") or {}).get("requires_captcha")),
            "downloaded": bool((doc.get("metadata") or {}).get("downloaded")),
        }
        for doc in empty_docs[:30]
    ]
    attachment_docs = [doc for doc in docs if (doc.get("source_type") or "") == "attachment"]
    warnings: list[str] = []
    if not docs:
        warnings.append("documents.jsonl 为空，知识库没有任何入库文档。")
    if empty_by_source.get("attachment", 0):
        warnings.append(
            f"{empty_by_source['attachment']} 个附件没有正文，只能作为附件入口，不能参与正文检索。"
        )
    if source_types.get("local_pdf", 0) == 0:
        warnings.append("未发现本地 PDF 入库；常见业务费指南等 PDF 资料可能缺失。")
    if not chunks:
        warnings.append("索引片段为空，请检查爬取、PDF 提取和入库步骤。")
    return {
        "document_count": len(docs),
        "indexed_document_count": len(indexed_doc_ids),
        "skipped_empty_text_count": len(empty_docs),
        "skipped_short_text_count": len(short_docs),
        "source_types": dict(source_types),
        "indexed_source_types": dict(indexed_source_types),
        "empty_text_by_source_type": dict(empty_by_source),
        "status_counts": dict(status_counts),
        "attachment_count": len(attachment_docs),
        "attachment_downloaded_count": sum(1 for doc in attachment_docs if (doc.get("metadata") or {}).get("downloaded")),
        "attachment_requires_captcha_count": sum(1 for doc in attachment_docs if (doc.get("metadata") or {}).get("requires_captcha")),
        "skipped_empty_examples": skipped,
        "warnings": warnings,
    }


def build_index(docs: list[dict]) -> dict:
    chunks: list[Chunk] = []
    for doc in docs:
        text = (doc.get("text") or "").strip()
        if not is_indexable_doc(doc):
            continue
        prefix = f"{doc.get('title') or ''}\n来源：{doc.get('url')}\n"
        for idx, chunk_text in enumerate(split_text(text)):
            searchable_text = (prefix + chunk_text).strip()
            chunks.append(
                Chunk(
                    id=f"{doc['id']}:{idx}",
                    doc_id=doc["id"],
                    url=doc["url"],
                    title=doc.get("title") or doc["url"],
                    source_type=doc.get("source_type") or "page",
                    text=searchable_text,
                    keywords=extract_keywords(searchable_text),
                    metadata=doc.get("metadata") or {},
                )
            )

    term_freqs = []
    doc_freq: Counter[str] = Counter()
    lengths = []
    for chunk in chunks:
        tf = Counter(tokenize(chunk.text))
        term_freqs.append(tf)
        lengths.append(sum(tf.values()))
        doc_freq.update(tf.keys())

    n_docs = len(chunks)
    avgdl = sum(lengths) / n_docs if n_docs else 0.0
    idf = {
        term: math.log(1 + (n_docs - freq + 0.5) / (freq + 0.5))
        for term, freq in doc_freq.items()
    }
    return {
        "version": 2,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "tokenizer": "domain-keywords+cjk-ngram-v2",
        "chunk_count": n_docs,
        "avgdl": avgdl,
        "chunks": [asdict(c) for c in chunks],
        "term_freqs": [dict(tf) for tf in term_freqs],
        "lengths": lengths,
        "idf": idf,
        "keyword_vocabulary": sorted(DOMAIN_KEYWORDS),
        "corpus_report": corpus_quality_report(docs, chunks),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a local BM25 index for crawled SHU finance office content.")
    parser.add_argument("--docs", type=Path, default=DOCS_PATH)
    parser.add_argument("--out", type=Path, default=INDEX_PATH)
    args = parser.parse_args()

    docs = load_docs(args.docs)
    index = build_index(docs)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    print(
        json.dumps(
            {
                "index": str(args.out),
                "chunk_count": index["chunk_count"],
                "corpus_report": index["corpus_report"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
