#!/usr/bin/env python3
"""
Database Maintenance and Cleanup Script
Purges stale conversational threads, message traces, and historical HITL test requests.
Can be run via CLI or imported into API endpoints.
"""

import os
import sys
import logging
from typing import Dict, Any

# Ensure app directory is on Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.infrastructure.db.database import DatabasePool

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("DBCleanup")

def cleanup_database(
    purge_threads: bool = True,
    purge_messages: bool = True,
    purge_hitl: bool = True,
    keep_days: int = 0
) -> Dict[str, Any]:
    """
    Purges records from conversation_messages, conversation_threads, and hitl_requests.
    If keep_days > 0, deletes records older than keep_days.
    If keep_days == 0, truncates / purges all historical operational test data while preserving users and system settings.
    """
    stats = {
        "deleted_messages": 0,
        "deleted_threads": 0,
        "deleted_hitl_requests": 0
    }
    
    with DatabasePool.get_cursor(commit=True) as cursor:
        if keep_days > 0:
            logger.info(f"Purging operational records older than {keep_days} days...")
            if purge_messages:
                cursor.execute(
                    "DELETE FROM conversation_messages WHERE created_at < NOW() - (INTERVAL '1 day' * %s);",
                    (keep_days,)
                )
                stats["deleted_messages"] = cursor.rowcount

            if purge_threads:
                cursor.execute(
                    "DELETE FROM conversation_threads WHERE updated_at < NOW() - (INTERVAL '1 day' * %s);",
                    (keep_days,)
                )
                stats["deleted_threads"] = cursor.rowcount

            if purge_hitl:
                cursor.execute(
                    "DELETE FROM hitl_requests WHERE requested_at < NOW() - (INTERVAL '1 day' * %s);",
                    (keep_days,)
                )
                stats["deleted_hitl_requests"] = cursor.rowcount
        else:
            logger.info("Purging all previous conversational threads, traces, and test HITL requests...")
            if purge_messages:
                cursor.execute("DELETE FROM conversation_messages;")
                stats["deleted_messages"] = cursor.rowcount

            if purge_threads:
                cursor.execute("DELETE FROM conversation_threads;")
                stats["deleted_threads"] = cursor.rowcount

            if purge_hitl:
                cursor.execute("DELETE FROM hitl_requests;")
                stats["deleted_hitl_requests"] = cursor.rowcount
                # Reset sequence for clean request IDs
                cursor.execute("ALTER SEQUENCE hitl_requests_id_seq RESTART WITH 1;")

    logger.info(f"Database cleanup completed successfully: {stats}")
    return stats

if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    res = cleanup_database(keep_days=days)
    print("\n--- Cleanup Results ---")
    for k, v in res.items():
        print(f" {k}: {v}")
