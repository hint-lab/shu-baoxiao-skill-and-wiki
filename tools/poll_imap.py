#!/usr/bin/env python3
from __future__ import annotations

import argparse
import imaplib
import json
import ssl
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path("/Users/hao/Documents/自助报销Agent")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.build_reimbursement_package import OUTPUT_ROOT, build_package, export_package  # noqa: E402
from tools.ingest_eml import ingest_eml  # noqa: E402
from tools.mail_settings import poll_config  # noqa: E402

INBOX_ROOT = ROOT / "data/mail_inbox"
STATE_PATH = INBOX_ROOT / "state.json"


@dataclass
class MailPollResult:
    source: str
    message_id: str
    eml_path: str
    package_path: str
    reimbursement_type: str
    missing_required: list[str]
    processed_at: str


def load_state(path: Path = STATE_PATH) -> dict:
    if not path.exists():
        return {"processed": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(state: dict, path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def processed_set(state: dict) -> set[str]:
    return set(state.get("processed", []))


def remember(state: dict, message_id: str) -> None:
    state.setdefault("processed", [])
    if message_id not in state["processed"]:
        state["processed"].append(message_id)


def build_from_eml(eml_path: Path, source: str, message_id: str) -> MailPollResult:
    material_dir = INBOX_ROOT / "materials" / message_id
    metadata = ingest_eml(eml_path, material_dir)
    note = "\n".join(part for part in [metadata.subject, metadata.body_text] if part)
    package = build_package(Path(metadata.material_dir), note, metadata.subject or None)
    out_dir = OUTPUT_ROOT / package.id
    export_package(package, out_dir)
    return MailPollResult(
        source=source,
        message_id=message_id,
        eml_path=str(eml_path.resolve()),
        package_path=str(out_dir.resolve()),
        reimbursement_type=package.reimbursement_type_name,
        missing_required=[item.name for item in package.checklist if item.status == "missing"],
        processed_at=datetime.now(timezone.utc).isoformat(),
    )


def process_fixture(paths: Iterable[Path], state: dict, force: bool = False) -> list[MailPollResult]:
    results = []
    seen = processed_set(state)
    for path in paths:
        message_id = f"fixture:{path.resolve()}"
        if message_id in seen and not force:
            continue
        target = INBOX_ROOT / "raw" / (path.stem + ".eml")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
        result = build_from_eml(target, "fixture", safe_message_id(message_id))
        results.append(result)
        remember(state, message_id)
    return results


def safe_message_id(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in value)[:120]


def poll_imap(state: dict, limit: int, force: bool = False) -> list[MailPollResult]:
    config = poll_config()
    results = []
    seen = processed_set(state)
    context = ssl.create_default_context()
    with imaplib.IMAP4_SSL(config["host"], config["port"], ssl_context=context) as mailbox:
        mailbox.login(config["username"], config["password"])
        mailbox.select(config["mailbox"])
        status, data = mailbox.search(None, "ALL" if force else "UNSEEN")
        if status != "OK":
            raise RuntimeError(f"IMAP search failed: {status}")
        ids = data[0].split()[:limit]
        for raw_id in ids:
            uid = raw_id.decode("ascii", errors="ignore")
            message_id = f"imap:{config['username']}:{config['mailbox']}:{uid}"
            if message_id in seen and not force:
                continue
            status, fetched = mailbox.fetch(raw_id, "(RFC822)")
            if status != "OK" or not fetched:
                continue
            eml_bytes = None
            for item in fetched:
                if isinstance(item, tuple):
                    eml_bytes = item[1]
                    break
            if not eml_bytes:
                continue
            safe_id = safe_message_id(message_id)
            eml_path = INBOX_ROOT / "raw" / f"{safe_id}.eml"
            eml_path.parent.mkdir(parents=True, exist_ok=True)
            eml_path.write_bytes(eml_bytes)
            results.append(build_from_eml(eml_path, "imap", safe_id))
            remember(state, message_id)
            if config["mark_seen"]:
                mailbox.store(raw_id, "+FLAGS", "\\Seen")
        mailbox.close()
        mailbox.logout()
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Poll reimbursement email inbox and convert messages into reimbursement packages.")
    parser.add_argument("--fixture-eml", action="append", type=Path, default=[], help="Process local .eml fixture instead of connecting to IMAP.")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--force", action="store_true", help="Reprocess messages even if state says they were handled.")
    parser.add_argument("--state", type=Path, default=STATE_PATH)
    args = parser.parse_args()

    state = load_state(args.state)
    if args.fixture_eml:
        results = process_fixture(args.fixture_eml, state, args.force)
    else:
        results = poll_imap(state, args.limit, args.force)
    save_state(state, args.state)
    print(json.dumps({"processed": [asdict(result) for result in results], "count": len(results)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
