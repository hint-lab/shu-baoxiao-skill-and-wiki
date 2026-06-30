#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader


ROOT = Path("/Users/hao/Documents/自助报销Agent")
DOCS_PATH = ROOT / "data/cwc/documents.jsonl"
DEFAULT_PDFS = [
    ROOT / "tmp/pdfs/上海大学智能报销操作手册2025年3月.pdf",
    Path("/Users/hao/Downloads/2018年新版常见业务费报销指南(文字版).pdf"),
]


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


def stable_id(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]


def clean_text(text: str) -> str:
    return "\n".join(line.strip() for line in text.replace("\xa0", " ").splitlines() if line.strip())


def pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = []
    for i, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(f"--- page {i} ---\n{clean_text(text)}")
    return "\n\n".join(pages)


def existing_ids(path: Path) -> set[str]:
    ids = set()
    if not path.exists():
        return ids
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                ids.add(json.loads(line)["id"])
    return ids


def main() -> None:
    parser = argparse.ArgumentParser(description="Append local PDF sources to the SHU finance RAG corpus.")
    parser.add_argument("pdf", nargs="*", type=Path)
    parser.add_argument("--docs", type=Path, default=DOCS_PATH)
    args = parser.parse_args()

    pdfs = args.pdf or DEFAULT_PDFS
    args.docs.parent.mkdir(parents=True, exist_ok=True)
    seen = existing_ids(args.docs)
    written = 0
    with args.docs.open("a", encoding="utf-8") as f:
        for pdf in pdfs:
            if not pdf.exists():
                continue
            doc_id = stable_id(str(pdf.resolve()))
            if doc_id in seen:
                continue
            doc = Document(
                id=doc_id,
                url=str(pdf.resolve()),
                title=pdf.stem,
                source_type="local_pdf",
                fetched_at=datetime.now(timezone.utc).isoformat(),
                status="local",
                content_type="application/pdf",
                text=pdf_text(pdf),
                links=[],
                attachments=[],
                metadata={"local_path": str(pdf.resolve())},
            )
            f.write(json.dumps(asdict(doc), ensure_ascii=False) + "\n")
            written += 1
    print(json.dumps({"appended": written, "docs_path": str(args.docs)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
