#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass, asdict
from email import policy
from email.message import Message
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

ROOT = Path("/Users/hao/Documents/自助报销Agent")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.build_reimbursement_package import OUTPUT_ROOT, build_package, export_package  # noqa: E402

MAIL_INGEST_ROOT = ROOT / "data/mail_ingest"


@dataclass
class IngestedEmail:
    eml_path: str
    subject: str
    from_addr: str
    date: str
    body_text: str
    attachment_paths: list[str]
    material_dir: str


def safe_filename(name: str, fallback: str) -> str:
    name = Path(name or fallback).name
    cleaned = "".join(ch if ch.isalnum() or ch in "._-（）()[] " or "\u4e00" <= ch <= "\u9fff" else "-" for ch in name)
    return cleaned.strip(" .-_") or fallback


def read_message(path: Path) -> Message:
    with path.open("rb") as f:
        return BytesParser(policy=policy.default).parse(f)


def body_text(message: Message) -> str:
    parts = []
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_disposition() == "attachment":
                continue
            if part.get_content_type() == "text/plain":
                try:
                    parts.append(part.get_content())
                except Exception:
                    payload = part.get_payload(decode=True) or b""
                    parts.append(payload.decode(part.get_content_charset() or "utf-8", errors="ignore"))
    elif message.get_content_type() == "text/plain":
        try:
            parts.append(message.get_content())
        except Exception:
            payload = message.get_payload(decode=True) or b""
            parts.append(payload.decode(message.get_content_charset() or "utf-8", errors="ignore"))
    return "\n".join(p.strip() for p in parts if p and p.strip())


def save_attachments(message: Message, material_dir: Path) -> list[Path]:
    saved = []
    counter = 1
    for part in message.walk():
        if part.get_content_disposition() != "attachment":
            continue
        filename = safe_filename(part.get_filename() or "", f"attachment-{counter}.bin")
        target = material_dir / filename
        while target.exists():
            counter += 1
            target = material_dir / f"{counter}-{filename}"
        payload = part.get_payload(decode=True)
        if payload is None:
            content = part.get_content()
            payload = content.encode("utf-8") if isinstance(content, str) else bytes(content)
        target.write_bytes(payload)
        saved.append(target)
        counter += 1
    return saved


def ingest_eml(eml_path: Path, material_dir: Path | None = None) -> IngestedEmail:
    message = read_message(eml_path)
    subject = str(message.get("subject", "")).strip()
    from_addr = str(message.get("from", "")).strip()
    date_header = str(message.get("date", "")).strip()
    try:
        date_value = parsedate_to_datetime(date_header).isoformat() if date_header else ""
    except Exception:
        date_value = date_header

    using_default_dir = material_dir is None
    material_dir = material_dir or MAIL_INGEST_ROOT / safe_filename(eml_path.stem, "email")
    if using_default_dir and material_dir.exists():
        shutil.rmtree(material_dir)
    material_dir.mkdir(parents=True, exist_ok=True)
    body = body_text(message)
    if body:
        (material_dir / "邮件正文.txt").write_text(body, encoding="utf-8")
    attachments = save_attachments(message, material_dir)

    metadata = IngestedEmail(
        eml_path=str(eml_path.resolve()),
        subject=subject,
        from_addr=from_addr,
        date=date_value,
        body_text=body,
        attachment_paths=[str(p.resolve()) for p in attachments],
        material_dir=str(material_dir.resolve()),
    )
    (material_dir / "email_metadata.json").write_text(json.dumps(asdict(metadata), ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest an .eml reimbursement email and build a reimbursement package from its body and attachments.")
    parser.add_argument("eml", type=Path)
    parser.add_argument("--title", default="")
    parser.add_argument("--note", default="")
    parser.add_argument("--material-dir", type=Path, default=None)
    args = parser.parse_args()

    metadata = ingest_eml(args.eml, args.material_dir)
    note_parts = [metadata.subject, metadata.body_text, args.note]
    note = "\n".join(part for part in note_parts if part)
    package = build_package(Path(metadata.material_dir), note, args.title or metadata.subject or None)
    out_dir = OUTPUT_ROOT / package.id
    export_package(package, out_dir)
    print(
        json.dumps(
            {
                "email": asdict(metadata),
                "package": str(out_dir),
                "type": package.reimbursement_type_name,
                "missing_required": [item.name for item in package.checklist if item.status == "missing"],
                "documents": [doc.file_name for doc in package.documents],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
