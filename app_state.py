from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path("/Users/hao/Documents/自助报销Agent")
DB_PATH = ROOT / "data/app.db"

ALLOWED_STATUSES = {
    "collecting",
    "needs_materials",
    "ready_for_review",
    "ready_for_school",
    "submitted_by_user",
    "reimbursed",
}

STATUS_LABELS = {
    "collecting": "资料归集中",
    "needs_materials": "待补材料",
    "ready_for_review": "待本人复核",
    "ready_for_school": "等待代填",
    "submitted_by_user": "已提交",
    "reimbursed": "已报销",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS package_status (
              package_id TEXT PRIMARY KEY,
              status TEXT NOT NULL,
              note TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              ready_for_school_at TEXT,
              submitted_at TEXT,
              reimbursed_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS package_status_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              package_id TEXT NOT NULL,
              old_status TEXT,
              new_status TEXT NOT NULL,
              note TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL
            )
            """
        )


def derive_status(package: dict[str, Any]) -> str:
    missing = [item for item in package.get("checklist", []) if item.get("status") == "missing"]
    if missing:
        return "needs_materials"
    return "ready_for_review"


def ensure_package_status(package: dict[str, Any]) -> dict[str, Any]:
    init_db()
    package_id = package["id"]
    initial_status = derive_status(package)
    timestamp = now_iso()
    with connect() as conn:
        row = conn.execute("SELECT * FROM package_status WHERE package_id = ?", (package_id,)).fetchone()
        if row is None:
            conn.execute(
                """
                INSERT INTO package_status (package_id, status, note, created_at, updated_at)
                VALUES (?, ?, '', ?, ?)
                """,
                (package_id, initial_status, timestamp, timestamp),
            )
            conn.execute(
                """
                INSERT INTO package_status_events (package_id, old_status, new_status, note, created_at)
                VALUES (?, NULL, ?, '系统按材料完整度初始化状态', ?)
                """,
                (package_id, initial_status, timestamp),
            )
            row = conn.execute("SELECT * FROM package_status WHERE package_id = ?", (package_id,)).fetchone()
    return dict(row)


def get_package_status(package_id: str) -> dict[str, Any] | None:
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT * FROM package_status WHERE package_id = ?", (package_id,)).fetchone()
    return dict(row) if row else None


def set_package_status(package_id: str, status: str, note: str = "") -> dict[str, Any]:
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"Unsupported package status: {status}")
    init_db()
    timestamp = now_iso()
    note = note.strip()
    with connect() as conn:
        row = conn.execute("SELECT * FROM package_status WHERE package_id = ?", (package_id,)).fetchone()
        old_status = row["status"] if row else None
        ready_for_school_at = row["ready_for_school_at"] if row else None
        submitted_at = row["submitted_at"] if row else None
        reimbursed_at = row["reimbursed_at"] if row else None
        if status == "ready_for_school" and not ready_for_school_at:
            ready_for_school_at = timestamp
        if status == "submitted_by_user" and not submitted_at:
            submitted_at = timestamp
        if status == "reimbursed" and not reimbursed_at:
            reimbursed_at = timestamp
        if row:
            conn.execute(
                """
                UPDATE package_status
                SET status = ?, note = ?, updated_at = ?,
                    ready_for_school_at = ?, submitted_at = ?, reimbursed_at = ?
                WHERE package_id = ?
                """,
                (status, note, timestamp, ready_for_school_at, submitted_at, reimbursed_at, package_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO package_status (
                  package_id, status, note, created_at, updated_at,
                  ready_for_school_at, submitted_at, reimbursed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (package_id, status, note, timestamp, timestamp, ready_for_school_at, submitted_at, reimbursed_at),
            )
        conn.execute(
            """
            INSERT INTO package_status_events (package_id, old_status, new_status, note, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (package_id, old_status, status, note, timestamp),
        )
        updated = conn.execute("SELECT * FROM package_status WHERE package_id = ?", (package_id,)).fetchone()
    return dict(updated)


def reset_package_status_from_materials(package: dict[str, Any], note: str = "系统按补充材料重新计算状态") -> dict[str, Any]:
    return set_package_status(package["id"], derive_status(package), note)


def package_status_events(package_id: str, limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT package_id, old_status, new_status, note, created_at
            FROM package_status_events
            WHERE package_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (package_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def attach_status(package: dict[str, Any]) -> dict[str, Any]:
    status = ensure_package_status(package)
    package["workflow_status"] = status["status"]
    package["workflow_status_label"] = STATUS_LABELS.get(status["status"], status["status"])
    package["workflow_note"] = status["note"]
    package["workflow_updated_at"] = status["updated_at"]
    package["workflow_status_meta"] = status
    return package
