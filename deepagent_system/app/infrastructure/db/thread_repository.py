import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.infrastructure.db.database import DatabasePool

logger = logging.getLogger("ThreadRepository")

class ThreadRepository:
    """Repository for managing conversational threads, message persistence, and JSONB traces."""

    @staticmethod
    def get_all_threads() -> List[Dict[str, Any]]:
        with DatabasePool.get_cursor() as cursor:
            cursor.execute("SELECT thread_id, title, created_at, updated_at FROM conversation_threads ORDER BY updated_at DESC;")
            rows = cursor.fetchall()
            threads = []
            for r in rows:
                t = {
                    "id": r["thread_id"],
                    "thread_id": r["thread_id"],
                    "title": r["title"],
                    "created_at": r["created_at"].isoformat() if isinstance(r.get("created_at"), datetime) else r.get("created_at"),
                    "updated_at": r["updated_at"].isoformat() if isinstance(r.get("updated_at"), datetime) else r.get("updated_at")
                }
                threads.append(t)
            return threads

    @staticmethod
    def create_thread(thread_id: str, title: str) -> Dict[str, Any]:
        with DatabasePool.get_cursor(commit=True) as cursor:
            cursor.execute(
                """
                INSERT INTO conversation_threads (thread_id, title, created_at, updated_at)
                VALUES (%s, %s, NOW(), NOW())
                ON CONFLICT (thread_id) DO UPDATE SET updated_at = NOW()
                RETURNING thread_id, title, created_at, updated_at;
                """,
                (thread_id, title)
            )
            row = cursor.fetchone()
            return {
                "id": row["thread_id"],
                "thread_id": row["thread_id"],
                "title": row["title"],
                "created_at": row["created_at"].isoformat() if isinstance(row.get("created_at"), datetime) else row.get("created_at"),
                "updated_at": row["updated_at"].isoformat() if isinstance(row.get("updated_at"), datetime) else row.get("updated_at")
            }

    @staticmethod
    def update_thread_title(thread_id: str, title: str):
        with DatabasePool.get_cursor(commit=True) as cursor:
            cursor.execute(
                "UPDATE conversation_threads SET title = %s, updated_at = NOW() WHERE thread_id = %s;",
                (title, thread_id)
            )

    @staticmethod
    def delete_thread(thread_id: str) -> bool:
        with DatabasePool.get_cursor(commit=True) as cursor:
            cursor.execute("DELETE FROM conversation_messages WHERE thread_id = %s;", (thread_id,))
            cursor.execute("DELETE FROM conversation_threads WHERE thread_id = %s;", (thread_id,))
            return cursor.rowcount > 0

    @staticmethod
    def purge_all() -> Dict[str, int]:
        with DatabasePool.get_cursor(commit=True) as cursor:
            cursor.execute("DELETE FROM conversation_messages;")
            msg_count = cursor.rowcount
            cursor.execute("DELETE FROM conversation_threads;")
            thr_count = cursor.rowcount
            return {"deleted_messages": msg_count, "deleted_threads": thr_count}

    @staticmethod
    def purge_older_than(days: int) -> Dict[str, int]:
        with DatabasePool.get_cursor(commit=True) as cursor:
            cursor.execute("DELETE FROM conversation_messages WHERE created_at < NOW() - (INTERVAL '1 day' * %s);", (days,))
            msg_count = cursor.rowcount
            cursor.execute("DELETE FROM conversation_threads WHERE updated_at < NOW() - (INTERVAL '1 day' * %s);", (days,))
            thr_count = cursor.rowcount
            return {"deleted_messages": msg_count, "deleted_threads": thr_count}

    @staticmethod
    def get_messages(thread_id: str) -> List[Dict[str, Any]]:
        with DatabasePool.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT id, thread_id, role, content, intermediate_steps, created_at
                FROM conversation_messages
                WHERE thread_id = %s
                ORDER BY created_at ASC;
                """,
                (thread_id,)
            )
            rows = cursor.fetchall()
            messages = []
            for r in rows:
                m = dict(r)
                if isinstance(m.get("created_at"), datetime):
                    m["created_at"] = m["created_at"].isoformat()
                messages.append(m)
            return messages

    @staticmethod
    def add_message(
        thread_id: str,
        role: str,
        content: str,
        intermediate_steps: Optional[Any] = None
    ) -> int:
        with DatabasePool.get_cursor(commit=True) as cursor:
            cursor.execute(
                """
                INSERT INTO conversation_messages (thread_id, role, content, intermediate_steps, created_at)
                VALUES (%s, %s, %s, %s, NOW())
                RETURNING id;
                """,
                (
                    thread_id,
                    role,
                    content,
                    json.dumps(intermediate_steps) if intermediate_steps else json.dumps([])
                )
            )
            row = cursor.fetchone()
            cursor.execute("UPDATE conversation_threads SET updated_at = NOW() WHERE thread_id = %s;", (thread_id,))
            return row["id"] if row else 0
