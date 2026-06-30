#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path("/Users/hao/Documents/自助报销Agent")
DOCS_PATH = ROOT / "data/cwc/documents.jsonl"
INDEX_PATH = ROOT / "data/cwc/index.json"


@dataclass
class Chunk:
    id: str
    doc_id: str
    url: str
    title: str
    source_type: str
    text: str
    metadata: dict


def tokenize(text: str) -> list[str]:
    text = text.lower()
    tokens: list[str] = []
    tokens.extend(re.findall(r"[a-z0-9_@.+-]{2,}", text))
    tokens.extend(re.findall(r"20\d{2}[-./年]\d{1,2}[-./月]\d{1,2}", text))
    chinese = re.findall(r"[\u4e00-\u9fff]+", text)
    for block in chinese:
        if len(block) <= 2:
            tokens.append(block)
            continue
        for n in (2, 3, 4):
            tokens.extend(block[i : i + n] for i in range(0, len(block) - n + 1))
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


def build_index(docs: list[dict]) -> dict:
    chunks: list[Chunk] = []
    for doc in docs:
        text = (doc.get("text") or "").strip()
        if not text:
            continue
        prefix = f"{doc.get('title') or ''}\n来源：{doc.get('url')}\n"
        for idx, chunk_text in enumerate(split_text(text)):
            chunks.append(
                Chunk(
                    id=f"{doc['id']}:{idx}",
                    doc_id=doc["id"],
                    url=doc["url"],
                    title=doc.get("title") or doc["url"],
                    source_type=doc.get("source_type") or "page",
                    text=(prefix + chunk_text).strip(),
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
        "version": 1,
        "chunk_count": n_docs,
        "avgdl": avgdl,
        "chunks": [asdict(c) for c in chunks],
        "term_freqs": [dict(tf) for tf in term_freqs],
        "lengths": lengths,
        "idf": idf,
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
    print(json.dumps({"index": str(args.out), "chunk_count": index["chunk_count"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
