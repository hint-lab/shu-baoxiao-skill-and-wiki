from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from tools.build_cwc_index import INDEX_PATH, tokenize


def load_index(path: Path = INDEX_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def bm25_scores(index: dict[str, Any], query: str, top_k: int, source_type: str = "") -> list[tuple[float, dict[str, Any]]]:
    q_tokens = tokenize(query)
    if not q_tokens:
        return []
    q_counts = Counter(q_tokens)
    avgdl = index["avgdl"] or 1.0
    k1 = 1.5
    b = 0.75
    scores: list[tuple[float, int]] = []
    for i, tf in enumerate(index["term_freqs"]):
        chunk = index["chunks"][i]
        if source_type and chunk.get("source_type") != source_type:
            continue
        dl = index["lengths"][i] or 1
        score = 0.0
        for term, q_weight in q_counts.items():
            freq = tf.get(term, 0)
            if not freq:
                continue
            idf = index["idf"].get(term, 0.0)
            score += q_weight * idf * (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * dl / avgdl))
        if score > 0:
            scores.append((score, i))
    scores.sort(reverse=True)
    return [(score, index["chunks"][i]) for score, i in scores[:top_k]]


def snippet(text: str, query: str, max_len: int = 360) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    q_terms = sorted(set(tokenize(query)), key=len, reverse=True)
    pos = -1
    for term in q_terms:
        if len(term) < 2:
            continue
        pos = text.lower().find(term.lower())
        if pos >= 0:
            break
    if pos < 0:
        return text[:max_len] + ("..." if len(text) > max_len else "")
    start = max(0, pos - max_len // 3)
    end = min(len(text), start + max_len)
    return ("..." if start else "") + text[start:end] + ("..." if end < len(text) else "")


def query_policy(query: str, top_k: int = 5, index_path: Path = INDEX_PATH, source_type: str = "") -> dict[str, Any]:
    query = query.strip()
    source_type = source_type.strip()
    if not query:
        return {"query": "", "answer": "", "hits": [], "source_count": 0}
    if not index_path.exists():
        return {
            "query": query,
            "answer": "本地财务处索引还不存在，请先刷新资料并重建索引。",
            "hits": [],
            "source_count": 0,
            "source_type": source_type,
        }

    index = load_index(index_path)
    raw_hits = bm25_scores(index, query, top_k, source_type)
    hits = []
    for rank, (score, chunk) in enumerate(raw_hits, 1):
        metadata = chunk.get("metadata") or {}
        hits.append(
            {
                "rank": rank,
                "score": round(score, 2),
                "title": chunk["title"],
                "url": chunk["url"],
                "source_type": chunk["source_type"],
                "published_date": metadata.get("published_date") or "",
                "snippet": snippet(chunk["text"], query),
            }
        )

    if not hits:
        answer = "没有在本地财务处资料库里找到足够证据。建议换关键词，或检查资料是否需要校内登录、验证码附件或人工补充。"
    else:
        answer = f"找到 {len(hits)} 条可核对依据。下面是财务处公开网页或本地 PDF 片段；提交前仍以财务处系统预审和最新通知为准。"
    return {"query": query, "answer": answer, "hits": hits, "source_count": len(hits), "source_type": source_type}


def format_cli_answer(result: dict[str, Any]) -> str:
    if not result["query"]:
        return "请输入要查询的问题。"
    lines = [f"问题：{result['query']}", "", result["answer"]]
    if result["hits"]:
        lines.append("")
        lines.append("检索依据：")
    for hit in result["hits"]:
        lines.append(f"{hit['rank']}. {hit['title']} [{hit['source_type']}]")
        lines.append(f"   来源：{hit['url']}")
        if hit["published_date"]:
            lines.append(f"   日期：{hit['published_date']}")
        lines.append(f"   片段：{hit['snippet']}")
        lines.append(f"   分数：{hit['score']:.2f}")
    return "\n".join(lines)
