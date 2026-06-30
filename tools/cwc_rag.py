from __future__ import annotations

import json
import math
import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from tools.build_cwc_index import DOMAIN_KEYWORDS, INDEX_PATH, extract_keywords, tokenize
from tools.rag_llm import generate_rag_answer

ROOT = Path("/Users/hao/Documents/自助报销Agent")
DB_PATH = ROOT / "data/app.db"


QUERY_EXPANSIONS: tuple[tuple[re.Pattern[str], tuple[str, ...]], ...] = (
    (
        re.compile(r"(版面|论文发表|发表费|出版报销|版面报销)"),
        ("版面费", "出版费", "审稿费", "论文录用通知", "论文审稿通知", "论文版面费"),
    ),
    (
        re.compile(r"(测试化验|测试加工|化验加工)"),
        ("测试化验加工费", "测试费", "加工清单", "测试合同"),
    ),
    (
        re.compile(r"(接待报销|公务接待|内宾接待)"),
        ("公务接待费", "公务接待清单", "邀请函", "派出公函"),
    ),
    (
        re.compile(r"(信息服务|数据服务|软件服务|技术服务)"),
        ("信息服务费", "服务合同", "服务清单"),
    ),
)


def expand_query_text(query: str) -> str:
    extras: list[str] = []
    for pattern, terms in QUERY_EXPANSIONS:
        if pattern.search(query):
            extras.extend(terms)
    if not extras:
        return query
    unique_extras = [term for term in dict.fromkeys(extras) if term not in query]
    return " ".join([query, *unique_extras])


def load_index(path: Path = INDEX_PATH) -> dict[str, Any]:
    if not path.exists():
        return load_index_from_db()
    return json.loads(path.read_text(encoding="utf-8"))


def load_index_from_db(db_path: Path = DB_PATH) -> dict[str, Any]:
    if not db_path.exists():
        return {}
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT chunk_id, doc_id, title, url, source_type, text, keywords_json, metadata_json
                FROM knowledge_chunks
                ORDER BY doc_id, chunk_index
                """
            ).fetchall()
        except sqlite3.OperationalError:
            return {}
    chunks = []
    for row in rows:
        chunks.append(
            {
                "id": row["chunk_id"],
                "doc_id": row["doc_id"],
                "title": row["title"],
                "url": row["url"],
                "source_type": row["source_type"],
                "text": row["text"],
                "keywords": json.loads(row["keywords_json"] or "[]"),
                "metadata": json.loads(row["metadata_json"] or "{}"),
            }
        )
    term_freqs = []
    doc_freq: Counter[str] = Counter()
    lengths = []
    for chunk in chunks:
        tf = Counter(tokenize(chunk["text"]))
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
        "version": "db-runtime",
        "source": "sqlite",
        "chunk_count": n_docs,
        "avgdl": avgdl,
        "chunks": chunks,
        "term_freqs": [dict(tf) for tf in term_freqs],
        "lengths": lengths,
        "idf": idf,
    }


def query_terms(query: str) -> list[str]:
    expanded_query = expand_query_text(query)
    terms = extract_keywords(expanded_query, limit=40)
    terms.extend(part.strip() for part in re.split(r"[\s,，、/]+", expanded_query) if len(part.strip()) >= 2)
    terms.extend(block for block in re.findall(r"[\u4e00-\u9fff]{2,12}", expanded_query) if block not in {"需要什么材料", "什么材料"})
    seen: set[str] = set()
    result: list[str] = []
    for term in sorted(terms, key=lambda value: (-len(value), value)):
        if term in seen:
            continue
        seen.add(term)
        result.append(term)
    return result


def bm25_scores(index: dict[str, Any], query: str, top_k: int, source_type: str = "") -> list[tuple[float, dict[str, Any]]]:
    scored = hybrid_scores(index, query, top_k, source_type, bm25_weight=1.0, keyword_weight=0.0)
    return [(item["bm25_score"], item["chunk"]) for item in scored if item["bm25_score"] > 0]


def bm25_score_map(index: dict[str, Any], query: str, source_type: str = "") -> dict[int, float]:
    q_tokens = tokenize(expand_query_text(query))
    if not q_tokens:
        return {}
    q_counts = Counter(q_tokens)
    avgdl = index["avgdl"] or 1.0
    k1 = 1.5
    b = 0.75
    scores: dict[int, float] = {}
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
            scores[i] = score
    return scores


def keyword_score(chunk: dict[str, Any], terms: list[str]) -> tuple[float, list[str]]:
    if not terms:
        return 0.0, []
    title = (chunk.get("title") or "").lower()
    text = (chunk.get("text") or "").lower()
    chunk_keywords = {str(value).lower() for value in chunk.get("keywords", [])}
    matched: list[str] = []
    score = 0.0
    for term in terms:
        lowered = term.lower()
        term_score = 0.0
        if lowered in title:
            term_score += 5.0
        if lowered in chunk_keywords:
            term_score += 3.0
        text_count = text.count(lowered)
        if text_count:
            term_score += min(4.0, 1.0 + text_count * 0.6)
        if term in DOMAIN_KEYWORDS and term_score:
            term_score *= 1.25
        if term_score:
            matched.append(term)
            score += term_score
    if matched:
        coverage = len(matched) / max(1, len(terms))
        score *= 1.0 + min(0.5, coverage)
    return score, matched[:12]


def hybrid_scores(
    index: dict[str, Any],
    query: str,
    top_k: int,
    source_type: str = "",
    bm25_weight: float = 0.72,
    keyword_weight: float = 0.28,
) -> list[dict[str, Any]]:
    terms = query_terms(query)
    bm25 = bm25_score_map(index, query, source_type)
    keyword_scores: dict[int, tuple[float, list[str]]] = {}
    for i, chunk in enumerate(index.get("chunks", [])):
        if source_type and chunk.get("source_type") != source_type:
            continue
        score, matched = keyword_score(chunk, terms)
        if score > 0:
            keyword_scores[i] = (score, matched)

    candidate_ids = set(bm25) | set(keyword_scores)
    if not candidate_ids:
        return []

    max_bm25 = max((bm25.get(i, 0.0) for i in candidate_ids), default=1.0) or 1.0
    max_keyword = max((keyword_scores.get(i, (0.0, []))[0] for i in candidate_ids), default=1.0) or 1.0
    results: list[dict[str, Any]] = []
    for i in candidate_ids:
        raw_bm25 = bm25.get(i, 0.0)
        raw_keyword, matched = keyword_scores.get(i, (0.0, []))
        combined = bm25_weight * (raw_bm25 / max_bm25) + keyword_weight * (raw_keyword / max_keyword)
        chunk = index["chunks"][i]
        source_boost = {"local_pdf": 0.04, "page": 0.02, "attachment": 0.0}.get(chunk.get("source_type") or "", 0.0)
        combined += source_boost
        results.append(
            {
                "combined_score": combined,
                "bm25_score": raw_bm25,
                "keyword_score": raw_keyword,
                "matched_keywords": matched,
                "chunk": chunk,
            }
        )

    results.sort(
        key=lambda item: (
            item["combined_score"],
            item["bm25_score"],
            item["keyword_score"],
            len(item["matched_keywords"]),
        ),
        reverse=True,
    )
    selected: list[dict[str, Any]] = []
    selected_ids: set[int] = set()
    selected_docs: set[str] = set()
    for i, item in enumerate(results):
        doc_id = str(item["chunk"].get("doc_id") or item["chunk"].get("id") or "")
        if doc_id in selected_docs:
            continue
        selected.append(item)
        selected_ids.add(i)
        selected_docs.add(doc_id)
        if len(selected) >= top_k:
            return selected
    for i, item in enumerate(results):
        if i in selected_ids:
            continue
        selected.append(item)
        if len(selected) >= top_k:
            break
    return selected


def snippet(text: str, query: str, max_len: int = 360) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    q_terms = sorted(set(query_terms(query)), key=len, reverse=True)
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
    if not index_path.exists() and not DB_PATH.exists():
        return {
            "query": query,
            "answer": "本地财务处索引和数据库还不存在，请先初始化知识库。",
            "hits": [],
            "source_count": 0,
            "source_type": source_type,
        }

    index = load_index(index_path)
    if not index.get("chunks"):
        return {
            "query": query,
            "answer": "本地财务处知识库还没有可检索片段，请先导入处理后的知识库 JSON。",
            "hits": [],
            "source_count": 0,
            "source_type": source_type,
        }
    raw_hits = hybrid_scores(index, query, top_k, source_type)
    hits = []
    for rank, item in enumerate(raw_hits, 1):
        chunk = item["chunk"]
        metadata = chunk.get("metadata") or {}
        hits.append(
            {
                "rank": rank,
                "score": round(item["combined_score"], 4),
                "bm25_score": round(item["bm25_score"], 2),
                "keyword_score": round(item["keyword_score"], 2),
                "retrieval_method": "bm25+keyword",
                "matched_keywords": item["matched_keywords"],
                "title": chunk["title"],
                "url": chunk["url"],
                "source_type": chunk["source_type"],
                "published_date": metadata.get("published_date") or "",
                "snippet": snippet(chunk["text"], query),
            }
        )

    llm_result = generate_rag_answer(query, hits)
    if llm_result.get("answer"):
        answer = llm_result["answer"]
        answer_mode = "llm_rag"
    elif not hits:
        answer = "没有在本地财务处资料库里找到足够证据。建议换关键词，或检查资料是否需要校内登录、验证码附件或人工补充。"
        answer_mode = "retrieval"
    else:
        if llm_result.get("enabled"):
            answer = "已找到可核对依据，但大模型生成暂不可用，先展示检索片段。请检查设置页的大模型配置。"
        else:
            answer = f"找到 {len(hits)} 条可核对依据。当前未启用知识库大模型生成，先展示 BM25 + 关键词检索片段；提交前仍以财务处系统预审和最新通知为准。"
        answer_mode = "retrieval"
    return {
        "query": query,
        "answer": answer,
        "answer_mode": answer_mode,
        "llm": llm_result,
        "hits": hits,
        "source_count": len(hits),
        "source_type": source_type,
        "retrieval_method": "bm25+keyword",
        "corpus_report": index.get("corpus_report", {}),
    }


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
        if hit.get("matched_keywords"):
            lines.append(f"   命中关键词：{'、'.join(hit['matched_keywords'])}")
        lines.append(f"   片段：{hit['snippet']}")
        lines.append(
            f"   分数：{hit['score']:.4f}（BM25 {hit.get('bm25_score', 0):.2f} / 关键词 {hit.get('keyword_score', 0):.2f}）"
        )
    return "\n".join(lines)
