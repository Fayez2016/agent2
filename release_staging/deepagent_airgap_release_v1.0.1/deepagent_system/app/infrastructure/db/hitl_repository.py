import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.infrastructure.db.database import DatabasePool

logger = logging.getLogger("HitlRepository")

class HitlRepository:
    """Repository for Human-in-the-Loop approval requests, decisions, and guardrail modes."""

    @staticmethod
    def get_setting(key: str, default: str = "") -> str:
        try:
            with DatabasePool.get_cursor() as cursor:
                cursor.execute("SELECT value FROM system_settings WHERE key = %s;", (key,))
                row = cursor.fetchone()
                return row["value"] if row and "value" in row else default
        except Exception as e:
            logger.warning(f"Failed to fetch setting '{key}' from DB: {e}")
            return default

    @staticmethod
    def set_setting(key: str, value: str) -> bool:
        try:
            with DatabasePool.get_cursor(commit=True) as cursor:
                cursor.execute(
                    """
                    INSERT INTO system_settings (key, value, updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();
                    """,
                    (key, value)
                )
            return True
        except Exception as e:
            logger.error(f"Failed to update setting '{key}' in DB: {e}")
            return False

    @staticmethod
    def get_guardrail_mode() -> str:
        return HitlRepository.get_setting("hitl_mode", "enforced")

    @staticmethod
    def set_guardrail_mode(mode: str) -> bool:
        return HitlRepository.set_setting("hitl_mode", mode)

    @staticmethod
    def get_pending_requests() -> List[Dict[str, Any]]:
        with DatabasePool.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT id, action_name, action_summary, status, requested_at
                FROM hitl_requests
                WHERE status = 'PENDING'
                ORDER BY requested_at DESC;
                """
            )
            rows = cursor.fetchall()
            pending = []
            for r in rows:
                p = {
                    "id": r["id"],
                    "action_name": r["action_name"],
                    "action_summary": r["action_summary"],
                    "description": r["action_summary"],
                    "status": r["status"],
                    "requested_at": r["requested_at"].isoformat() if isinstance(r.get("requested_at"), datetime) else r.get("requested_at")
                }
                pending.append(p)
            return pending

    @staticmethod
    def resolve_request(request_id: int, decision: str) -> bool:
        with DatabasePool.get_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE hitl_requests
                SET status = %s, resolved_at = NOW()
                WHERE id = %s AND status = 'PENDING';
                """,
                (decision.upper(), request_id)
            )
            return cursor.rowcount > 0

    @staticmethod
    def get_request_by_id(request_id: int) -> Optional[Dict[str, Any]]:
        with DatabasePool.get_cursor() as cursor:
            cursor.execute(
                "SELECT id, action_name, action_summary, status, requested_at, resolved_at FROM hitl_requests WHERE id = %s;",
                (request_id,)
            )
            row = cursor.fetchone()
            if row:
                res = {
                    "id": row["id"],
                    "action_name": row["action_name"],
                    "action_summary": row["action_summary"],
                    "description": row["action_summary"],
                    "status": row["status"],
                    "requested_at": row["requested_at"].isoformat() if isinstance(row.get("requested_at"), datetime) else row.get("requested_at"),
                    "resolved_at": row["resolved_at"].isoformat() if isinstance(row.get("resolved_at"), datetime) else row.get("resolved_at")
                }
                return res
            return None

    @staticmethod
    def get_audit_history(limit: int = 100) -> List[Dict[str, Any]]:
        with DatabasePool.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT id, action_name, action_summary, status, requested_at, resolved_at
                FROM hitl_requests
                ORDER BY id DESC
                LIMIT %s;
                """,
                (limit,)
            )
            rows = cursor.fetchall()
            history = []
            for r in rows:
                h = {
                    "id": r["id"],
                    "action_name": r["action_name"] or "System Operation",
                    "action_summary": r["action_summary"],
                    "status": r["status"],
                    "requested_at": r["requested_at"].isoformat() if isinstance(r.get("requested_at"), datetime) else (str(r.get("requested_at")) if r.get("requested_at") else ""),
                    "resolved_at": r["resolved_at"].isoformat() if isinstance(r.get("resolved_at"), datetime) else (str(r.get("resolved_at")) if r.get("resolved_at") else "")
                }
                history.append(h)
            return history

    @staticmethod
    def purge_all() -> int:
        with DatabasePool.get_cursor(commit=True) as cursor:
            cursor.execute("DELETE FROM hitl_requests;")
            count = cursor.rowcount
            cursor.execute("ALTER SEQUENCE hitl_requests_id_seq RESTART WITH 1;")
            return count

    @staticmethod
    def purge_older_than(days: int) -> int:
        with DatabasePool.get_cursor(commit=True) as cursor:
            cursor.execute("DELETE FROM hitl_requests WHERE requested_at < NOW() - (INTERVAL '1 day' * %s);", (days,))
            return cursor.rowcount
