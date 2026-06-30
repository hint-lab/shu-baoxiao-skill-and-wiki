#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path("/Users/hao/Documents/自助报销Agent")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.build_cwc_index import DOCS_PATH, INDEX_PATH, MIN_INDEXABLE_CHARS, extract_keywords, load_docs  # noqa: E402

DATA_DIR = ROOT / "data/cwc"
PROCESSED_DOCS_PATH = DATA_DIR / "processed_documents.jsonl"
PROCESSED_CHUNKS_PATH = DATA_DIR / "processed_chunks.jsonl"
PROCESSED_MANIFEST_PATH = DATA_DIR / "processed_manifest.json"
RULES_PATH = ROOT / "data/rules/reimbursement_rules.json"
DB_PATH = ROOT / "data/app.db"
SCHEMA_VERSION = 1


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def load_rules(path: Path = RULES_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return list(payload.get("reimbursement_types", []))


def classify_reimbursement_types(text: str, rules: list[dict[str, Any]]) -> list[str]:
    lowered = text.lower()
    scores: Counter[str] = Counter()
    for rule in rules:
        name = str(rule.get("name") or "")
        candidates = [name, str(rule.get("school_form_hint") or "")]
        candidates.extend(str(item) for item in rule.get("aliases", []))
        for checklist in rule.get("checklist", []):
            candidates.append(str(checklist.get("name") or ""))
            candidates.extend(str(item) for item in checklist.get("keywords", []))
        for candidate in candidates:
            candidate = candidate.strip()
            if len(candidate) >= 2 and candidate.lower() in lowered:
                scores[name] += max(1, min(4, len(candidate) // 2))
    return [name for name, _ in scores.most_common(5)]


def ingestion_status(doc: dict[str, Any]) -> str:
    text = (doc.get("text") or "").strip()
    metadata = doc.get("metadata") or {}
    if len(text) >= MIN_INDEXABLE_CHARS:
        return "indexed"
    if metadata.get("requires_captcha"):
        return "blocked_captcha"
    if str(doc.get("status") or "").startswith("403"):
        return "blocked_forbidden"
    if str(doc.get("status") or "").startswith("404"):
        return "missing_remote"
    if metadata.get("downloaded") and not text:
        return "downloaded_no_extractable_text"
    if text:
        return "short_text"
    return "empty_text"


def source_labels(doc: dict[str, Any]) -> list[str]:
    labels = [str(doc.get("source_type") or "page")]
    metadata = doc.get("metadata") or {}
    if metadata.get("requires_captcha"):
        labels.append("requires_captcha")
    if metadata.get("downloaded"):
        labels.append("downloaded")
    if metadata.get("is_pdf"):
        labels.append("pdf")
    if metadata.get("local_path"):
        labels.append("local_file")
    return labels


def load_index(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build_processed_corpus(
    docs_path: Path = DOCS_PATH,
    index_path: Path = INDEX_PATH,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    docs = load_docs(docs_path)
    index = load_index(index_path)
    rules = load_rules()
    generated_at = now_iso()
    chunks_by_doc: dict[str, list[str]] = defaultdict(list)
    processed_chunks: list[dict[str, Any]] = []

    for chunk, length in zip(index.get("chunks", []), index.get("lengths", []), strict=False):
        chunk_id = str(chunk.get("id") or "")
        doc_id = str(chunk.get("doc_id") or "")
        chunk_index = 0
        if ":" in chunk_id:
            try:
                chunk_index = int(chunk_id.rsplit(":", 1)[1])
            except ValueError:
                chunk_index = 0
        chunks_by_doc[doc_id].append(chunk_id)
        processed_chunks.append(
            {
                "schema_version": SCHEMA_VERSION,
                "chunk_id": chunk_id,
                "doc_id": doc_id,
                "chunk_index": chunk_index,
                "title": chunk.get("title") or "",
                "url": chunk.get("url") or "",
                "source_type": chunk.get("source_type") or "page",
                "text": chunk.get("text") or "",
                "text_sha256": sha256_text(chunk.get("text") or ""),
                "text_length": len(chunk.get("text") or ""),
                "bm25_length": int(length or 0),
                "keywords": list(chunk.get("keywords") or extract_keywords(chunk.get("text") or "")),
                "metadata": chunk.get("metadata") or {},
                "generated_at": generated_at,
            }
        )

    processed_docs: list[dict[str, Any]] = []
    for doc in docs:
        text = doc.get("text") or ""
        doc_id = str(doc.get("id") or "")
        searchable = "\n".join([str(doc.get("title") or ""), text])
        tags = {
            "keywords": extract_keywords(searchable, limit=80),
            "reimbursement_types": classify_reimbursement_types(searchable, rules),
            "source_labels": source_labels(doc),
            "published_date": (doc.get("metadata") or {}).get("published_date") or "",
            "requires_captcha": bool((doc.get("metadata") or {}).get("requires_captcha")),
            "downloaded": bool((doc.get("metadata") or {}).get("downloaded")),
        }
        processed_docs.append(
            {
                "schema_version": SCHEMA_VERSION,
                "doc_id": doc_id,
                "url": doc.get("url") or "",
                "title": doc.get("title") or doc.get("url") or "",
                "source_type": doc.get("source_type") or "page",
                "fetched_at": doc.get("fetched_at") or "",
                "status": str(doc.get("status") or ""),
                "content_type": doc.get("content_type") or "",
                "text_sha256": sha256_text(text),
                "text_length": len(text),
                "indexable": doc_id in chunks_by_doc,
                "ingestion_status": ingestion_status(doc),
                "chunk_ids": chunks_by_doc.get(doc_id, []),
                "tags": tags,
                "metadata": doc.get("metadata") or {},
                "generated_at": generated_at,
            }
        )

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "source_documents_path": str(docs_path),
        "source_index_path": str(index_path),
        "processed_documents_path": str(PROCESSED_DOCS_PATH),
        "processed_chunks_path": str(PROCESSED_CHUNKS_PATH),
        "document_count": len(processed_docs),
        "chunk_count": len(processed_chunks),
        "ingestion_status_counts": dict(Counter(doc["ingestion_status"] for doc in processed_docs)),
        "source_type_counts": dict(Counter(doc["source_type"] for doc in processed_docs)),
        "index_version": index.get("version"),
        "tokenizer": index.get("tokenizer", ""),
    }
    return processed_docs, processed_chunks, manifest


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_processed_corpus(
    docs_path: Path = DOCS_PATH,
    index_path: Path = INDEX_PATH,
    processed_docs_path: Path = PROCESSED_DOCS_PATH,
    processed_chunks_path: Path = PROCESSED_CHUNKS_PATH,
    manifest_path: Path = PROCESSED_MANIFEST_PATH,
) -> dict[str, Any]:
    docs, chunks, manifest = build_processed_corpus(docs_path, index_path)
    write_jsonl(processed_docs_path, docs)
    write_jsonl(processed_chunks_path, chunks)
    manifest["processed_documents_path"] = str(processed_docs_path)
    manifest["processed_chunks_path"] = str(processed_chunks_path)
    manifest["processed_documents_sha256"] = file_sha256(processed_docs_path)
    manifest["processed_chunks_sha256"] = file_sha256(processed_chunks_path)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def ensure_knowledge_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_documents (
          doc_id TEXT PRIMARY KEY,
          title TEXT NOT NULL,
          url TEXT NOT NULL,
          source_type TEXT NOT NULL,
          status TEXT NOT NULL,
          content_type TEXT NOT NULL,
          fetched_at TEXT NOT NULL,
          text_sha256 TEXT NOT NULL,
          text_length INTEGER NOT NULL,
          indexable INTEGER NOT NULL,
          ingestion_status TEXT NOT NULL,
          tags_json TEXT NOT NULL,
          metadata_json TEXT NOT NULL,
          generated_at TEXT NOT NULL,
          imported_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_chunks (
          chunk_id TEXT PRIMARY KEY,
          doc_id TEXT NOT NULL,
          chunk_index INTEGER NOT NULL,
          title TEXT NOT NULL,
          url TEXT NOT NULL,
          source_type TEXT NOT NULL,
          text TEXT NOT NULL,
          text_sha256 TEXT NOT NULL,
          text_length INTEGER NOT NULL,
          bm25_length INTEGER NOT NULL,
          keywords_json TEXT NOT NULL,
          metadata_json TEXT NOT NULL,
          generated_at TEXT NOT NULL,
          imported_at TEXT NOT NULL,
          FOREIGN KEY(doc_id) REFERENCES knowledge_documents(doc_id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_documents_status ON knowledge_documents(ingestion_status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_documents_source ON knowledge_documents(source_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_doc ON knowledge_chunks(doc_id)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_seed_meta (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )
        """
    )


def seed_fingerprint(docs_path: Path, chunks_path: Path) -> str:
    return sha256_text(f"{file_sha256(docs_path)}:{file_sha256(chunks_path)}")


def import_processed_corpus(
    db_path: Path = DB_PATH,
    processed_docs_path: Path = PROCESSED_DOCS_PATH,
    processed_chunks_path: Path = PROCESSED_CHUNKS_PATH,
    force: bool = False,
) -> dict[str, Any]:
    if not processed_docs_path.exists() or not processed_chunks_path.exists():
        raise FileNotFoundError("Processed knowledge JSONL files are missing. Run with --build first.")

    fingerprint = seed_fingerprint(processed_docs_path, processed_chunks_path)
    imported_at = now_iso()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        ensure_knowledge_schema(conn)
        current = conn.execute("SELECT value FROM knowledge_seed_meta WHERE key = 'fingerprint'").fetchone()
        if current and current["value"] == fingerprint and not force:
            doc_count = conn.execute("SELECT COUNT(*) AS n FROM knowledge_documents").fetchone()["n"]
            chunk_count = conn.execute("SELECT COUNT(*) AS n FROM knowledge_chunks").fetchone()["n"]
            return {"imported": False, "document_count": doc_count, "chunk_count": chunk_count, "fingerprint": fingerprint}

        docs = read_jsonl(processed_docs_path)
        chunks = read_jsonl(processed_chunks_path)
        doc_ids = {row["doc_id"] for row in docs}
        chunk_ids = {row["chunk_id"] for row in chunks}
        conn.executemany(
            """
            INSERT OR REPLACE INTO knowledge_documents (
              doc_id, title, url, source_type, status, content_type, fetched_at,
              text_sha256, text_length, indexable, ingestion_status,
              tags_json, metadata_json, generated_at, imported_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["doc_id"],
                    row["title"],
                    row["url"],
                    row["source_type"],
                    row["status"],
                    row["content_type"],
                    row["fetched_at"],
                    row["text_sha256"],
                    int(row["text_length"]),
                    1 if row["indexable"] else 0,
                    row["ingestion_status"],
                    json.dumps(row["tags"], ensure_ascii=False, sort_keys=True),
                    json.dumps(row["metadata"], ensure_ascii=False, sort_keys=True),
                    row["generated_at"],
                    imported_at,
                )
                for row in docs
            ],
        )
        conn.executemany(
            """
            INSERT OR REPLACE INTO knowledge_chunks (
              chunk_id, doc_id, chunk_index, title, url, source_type, text,
              text_sha256, text_length, bm25_length, keywords_json,
              metadata_json, generated_at, imported_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["chunk_id"],
                    row["doc_id"],
                    int(row["chunk_index"]),
                    row["title"],
                    row["url"],
                    row["source_type"],
                    row["text"],
                    row["text_sha256"],
                    int(row["text_length"]),
                    int(row["bm25_length"]),
                    json.dumps(row["keywords"], ensure_ascii=False, sort_keys=True),
                    json.dumps(row["metadata"], ensure_ascii=False, sort_keys=True),
                    row["generated_at"],
                    imported_at,
                )
                for row in chunks
            ],
        )
        if doc_ids:
            placeholders = ",".join("?" for _ in doc_ids)
            conn.execute(f"DELETE FROM knowledge_documents WHERE doc_id NOT IN ({placeholders})", tuple(doc_ids))
        if chunk_ids:
            placeholders = ",".join("?" for _ in chunk_ids)
            conn.execute(f"DELETE FROM knowledge_chunks WHERE chunk_id NOT IN ({placeholders})", tuple(chunk_ids))
        conn.execute(
            """
            INSERT OR REPLACE INTO knowledge_seed_meta (key, value, updated_at)
            VALUES ('fingerprint', ?, ?)
            """,
            (fingerprint, imported_at),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO knowledge_seed_meta (key, value, updated_at)
            VALUES ('schema_version', ?, ?)
            """,
            (str(SCHEMA_VERSION), imported_at),
        )
    return {"imported": True, "document_count": len(docs), "chunk_count": len(chunks), "fingerprint": fingerprint}


def knowledge_db_status(db_path: Path = DB_PATH) -> dict[str, Any]:
    if not db_path.exists():
        return {"exists": False, "document_count": 0, "chunk_count": 0, "fingerprint": ""}
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            ensure_knowledge_schema(conn)
            doc_count = conn.execute("SELECT COUNT(*) AS n FROM knowledge_documents").fetchone()["n"]
            chunk_count = conn.execute("SELECT COUNT(*) AS n FROM knowledge_chunks").fetchone()["n"]
            fingerprint = conn.execute("SELECT value FROM knowledge_seed_meta WHERE key = 'fingerprint'").fetchone()
            schema_version = conn.execute("SELECT value FROM knowledge_seed_meta WHERE key = 'schema_version'").fetchone()
    except sqlite3.DatabaseError as exc:
        return {"exists": True, "error": str(exc), "document_count": 0, "chunk_count": 0, "fingerprint": ""}
    return {
        "exists": True,
        "document_count": doc_count,
        "chunk_count": chunk_count,
        "fingerprint": fingerprint["value"] if fingerprint else "",
        "schema_version": schema_version["value"] if schema_version else "",
    }


def initialize_knowledge_base(force: bool = False) -> dict[str, Any]:
    if not PROCESSED_DOCS_PATH.exists() or not PROCESSED_CHUNKS_PATH.exists():
        if DOCS_PATH.exists() and INDEX_PATH.exists():
            write_processed_corpus()
        else:
            return {"imported": False, "reason": "missing_processed_seed"}
    return import_processed_corpus(force=force)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build processed knowledge JSONL and import it into the local SQLite database.")
    parser.add_argument("--build", action="store_true", help="Write processed_documents.jsonl and processed_chunks.jsonl")
    parser.add_argument("--import-db", action="store_true", help="Import processed JSONL into data/app.db")
    parser.add_argument("--force", action="store_true", help="Force reimport even if the seed fingerprint is unchanged")
    args = parser.parse_args()

    build = args.build or not args.import_db
    import_db = args.import_db or not args.build
    result: dict[str, Any] = {}
    if build:
        result["build"] = write_processed_corpus()
    if import_db:
        result["import"] = import_processed_corpus(force=args.force)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
