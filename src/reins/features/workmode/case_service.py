from __future__ import annotations

import json
import sqlite3
from typing import Any

from reins.features.workmode.db import DB_PATH, init_db


def get_conn() -> sqlite3.Connection:
    """
    Open a SQLite connection for WorkMode case history.
    """
    init_db()

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _decode_json(value: Any) -> Any:
    """
    Decode JSON strings stored in SQLite.

    If decoding fails, keep the raw value safely.
    """
    if value is None:
        return None

    if not isinstance(value, str):
        return value

    if not value.strip():
        return {}

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {"raw": value}


def _decode_event(row: sqlite3.Row) -> dict[str, Any]:
    """
    Convert an event DB row into UI/replay-friendly dict.
    """
    event = dict(row)
    event["data"] = _decode_json(event.get("data")) or {}
    return event


def _decode_artifact(row: sqlite3.Row) -> dict[str, Any]:
    """
    Convert an artifact DB row into UI-friendly dict.
    """
    artifact = dict(row)

    if "content" in artifact:
        artifact["content"] = _decode_json(artifact.get("content"))
        if isinstance(artifact["content"], dict):
            artifact = {
                **artifact["content"],
                "id": artifact.get("id"),
                "case_id": artifact.get("case_id"),
                "created_at": artifact.get("created_at"),
                "db_type": artifact.get("type"),
                "db_title": artifact.get("title"),
            }

    return artifact


class CaseService:
    # LIST CASES
    def list_cases(self, limit: int = 50) -> list[dict[str, Any]]:
        conn = get_conn()

        try:
            cur = conn.execute(
                """
                SELECT *
                FROM cases
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            )

            rows = cur.fetchall()
            return [dict(row) for row in rows]

        finally:
            conn.close()

    # GET CASE
    def get_case(self, case_id: str) -> dict[str, Any] | None:
        conn = get_conn()

        try:
            cur = conn.execute(
                """
                SELECT *
                FROM cases
                WHERE case_id = ?
                """,
                (case_id,),
            )

            row = cur.fetchone()
            return dict(row) if row else None

        finally:
            conn.close()

    # GET EVENTS / TIMELINE
    def get_events(self, case_id: str) -> list[dict[str, Any]]:
        conn = get_conn()

        try:
            cur = conn.execute(
                """
                SELECT *
                FROM events
                WHERE case_id = ?
                ORDER BY id ASC
                """,
                (case_id,),
            )

            rows = cur.fetchall()
            return [_decode_event(row) for row in rows]

        finally:
            conn.close()

    # GET ARTIFACTS
    def get_artifacts(self, case_id: str) -> list[dict[str, Any]]:
        conn = get_conn()

        try:
            cur = conn.execute(
                """
                SELECT *
                FROM artifacts
                WHERE case_id = ?
                ORDER BY id ASC
                """,
                (case_id,),
            )

            rows = cur.fetchall()
            return [_decode_artifact(row) for row in rows]

        finally:
            conn.close()

    # FULL CASE TIMELINE
    def get_case_timeline(self, case_id: str) -> dict[str, Any]:
        case = self.get_case(case_id)

        if not case:
            return {
                "ok": False,
                "error": "case_not_found",
                "case_id": case_id,
            }

        return {
            "ok": True,
            "case": case,
            "events": self.get_events(case_id),
            "artifacts": self.get_artifacts(case_id),
        }

    # FULL CASE REPLAY
    def replay_case(self, case_id: str) -> dict[str, Any]:
        """
        Backward-compatible replay method.

        Keeps your existing P4 API shape:
        {
            "case": ...,
            "timeline": ...,
            "artifacts": ...
        }
        """
        case = self.get_case(case_id)

        return {
            "case": case,
            "timeline": self.get_events(case_id),
            "artifacts": self.get_artifacts(case_id),
        }
