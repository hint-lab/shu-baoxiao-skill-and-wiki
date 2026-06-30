from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


ROOT = Path("/Users/hao/Documents/自助报销Agent")
CONFIG_PATH = ROOT / "data/settings/imap.json"


def read_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def env_config() -> dict[str, Any]:
    return {
        "enabled": bool(os.getenv("REIMBURSEMENT_IMAP_HOST") and os.getenv("REIMBURSEMENT_IMAP_USERNAME")),
        "host": os.getenv("REIMBURSEMENT_IMAP_HOST", ""),
        "port": os.getenv("REIMBURSEMENT_IMAP_PORT", "993"),
        "username": os.getenv("REIMBURSEMENT_IMAP_USERNAME", ""),
        "password": os.getenv("REIMBURSEMENT_IMAP_PASSWORD", ""),
        "mailbox": os.getenv("REIMBURSEMENT_IMAP_MAILBOX", "INBOX"),
        "mark_seen": os.getenv("REIMBURSEMENT_IMAP_MARK_SEEN", "false").lower() == "true",
    }


def effective_config() -> dict[str, Any]:
    saved = read_config()
    env = env_config()
    config = {
        "enabled": bool(saved.get("enabled", env.get("enabled", False))),
        "host": str(saved.get("host") or env.get("host") or "").strip(),
        "port": str(saved.get("port") or env.get("port") or "993").strip(),
        "username": str(saved.get("username") or env.get("username") or "").strip(),
        "password": str(saved.get("password") or env.get("password") or ""),
        "mailbox": str(saved.get("mailbox") or env.get("mailbox") or "INBOX").strip() or "INBOX",
        "mark_seen": bool(saved.get("mark_seen", env.get("mark_seen", False))),
    }
    return config


def status() -> dict[str, Any]:
    config = effective_config()
    configured = bool(config["enabled"] and config["host"] and config["username"] and config["password"])
    return {
        "enabled": config["enabled"],
        "configured": configured,
        "ready": configured,
        "host": config["host"],
        "port": config["port"],
        "username": config["username"],
        "mailbox": config["mailbox"],
        "mark_seen": config["mark_seen"],
        "has_password": bool(config["password"]),
        "config_path": str(CONFIG_PATH),
    }


def poll_config() -> dict[str, Any]:
    config = effective_config()
    missing = [
        key
        for key in ("host", "username", "password")
        if not str(config.get(key) or "").strip()
    ]
    if not config.get("enabled"):
        missing.append("enabled")
    if missing:
        raise RuntimeError("Missing IMAP settings: " + ", ".join(missing))
    return {
        "host": config["host"],
        "port": int(str(config["port"] or "993")),
        "username": config["username"],
        "password": config["password"],
        "mailbox": config["mailbox"] or "INBOX",
        "mark_seen": bool(config["mark_seen"]),
    }


def save_config(
    host: str,
    port: str,
    username: str,
    password: str,
    mailbox: str,
    enabled: bool,
    mark_seen: bool,
    clear_password: bool = False,
    path: Path = CONFIG_PATH,
) -> dict[str, Any]:
    current = read_config(path)
    next_password = ""
    if clear_password:
        next_password = ""
    elif password.strip():
        next_password = password.strip()
    else:
        next_password = str(current.get("password") or "")
    payload = {
        "enabled": bool(enabled),
        "host": host.strip(),
        "port": str(port or "993").strip() or "993",
        "username": username.strip(),
        "password": next_password,
        "mailbox": mailbox.strip() or "INBOX",
        "mark_seen": bool(mark_seen),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return status()
