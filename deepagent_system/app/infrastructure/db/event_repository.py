import json
import logging
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from app.infrastructure.db.database import DatabasePool

logger = logging.getLogger("EventRepository")

class EventRepository:
    """Repository for storing, buffering, and deduplicating high-frequency alert events."""

    @staticmethod
    def ingest_event(host_target: str, alert_type: str, severity: str = "warning", domain: str = "linux", payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Ingests a raw monitoring alert event into the buffer."""
        payload_json = json.dumps(payload or {})
        with DatabasePool.get_cursor(commit=True) as cursor:
            cursor.execute(
                """
                INSERT INTO collected_events (domain, host_target, alert_type, severity, payload, received_at, status)
                VALUES (%s, %s, %s, %s, %s, NOW(), 'PENDING')
                RETURNING id, domain, host_target, alert_type, severity, received_at, status;
                """,
                (domain, host_target.strip(), alert_type.strip(), severity.strip(), payload_json)
            )
            row = cursor.fetchone()
            return dict(row)

    @staticmethod
    def ingest_bulk_events(events: List[Dict[str, Any]], domain: str = "linux") -> int:
        """Bulk ingests a list of alert events."""
        if not events:
            return 0
        count = 0
        with DatabasePool.get_cursor(commit=True) as cursor:
            for ev in events:
                payload_json = json.dumps(ev.get("payload", {}))
                cursor.execute(
                    """
                    INSERT INTO collected_events (domain, host_target, alert_type, severity, payload, received_at, status)
                    VALUES (%s, %s, %s, %s, %s, NOW(), 'PENDING');
                    """,
                    (
                        ev.get("domain", domain),
                        ev.get("host_target", "unknown").strip(),
                        ev.get("alert_type", "generic_alarm").strip(),
                        ev.get("severity", "warning").strip(),
                        payload_json
                    )
                )
                count += 1
        return count

    @staticmethod
    def get_pending_events(domain: str = "linux") -> List[Dict[str, Any]]:
        """Retrieves all unprocessed pending events in the buffer."""
        with DatabasePool.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT id, domain, host_target, alert_type, severity, payload, received_at, status
                FROM collected_events
                WHERE status = 'PENDING' AND domain = %s
                ORDER BY received_at ASC;
                """,
                (domain,)
            )
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def process_and_deduplicate_batch(domain: str = "linux") -> Dict[str, Any]:
        """
        Deduplicates all buffered pending events over the rolling window:
        - Groups alarms by host_target and cluster root.
        - Suppresses redundant alarms on the same node.
        - Marks buffered events as BATCHED.
        - Generates a consolidated execution manifest.
        """
        batch_id = f"batch_{uuid.uuid4().hex[:10]}"
        with DatabasePool.get_cursor(commit=True) as cursor:
            # 1. Fetch pending rows
            cursor.execute(
                """
                SELECT id, domain, host_target, alert_type, severity, received_at
                FROM collected_events
                WHERE status = 'PENDING' AND domain = %s
                ORDER BY received_at ASC
                FOR UPDATE;
                """,
                (domain,)
            )
            rows = cursor.fetchall()
            if not rows:
                return {
                    "batch_id": batch_id,
                    "total_raw_events": 0,
                    "deduplicated_targets": [],
                    "summary": "No pending events to process."
                }

            event_ids = [r["id"] for r in rows]
            raw_count = len(rows)

            # 2. Deduplicate host targets and alert types
            target_map = {}
            for r in rows:
                target = r["host_target"]
                alert = r["alert_type"]
                sev = r["severity"]
                if target not in target_map:
                    target_map[target] = {
                        "host_target": target,
                        "alert_count": 0,
                        "alert_types": set(),
                        "max_severity": sev
                    }
                target_map[target]["alert_count"] += 1
                target_map[target]["alert_types"].add(alert)
                if sev == "critical":
                    target_map[target]["max_severity"] = "critical"

            # Format deduplicated manifest
            deduped_targets = []
            for t, data in target_map.items():
                deduped_targets.append({
                    "host_target": t,
                    "raw_alerts_absorbed": data["alert_count"],
                    "alert_types": list(data["alert_types"]),
                    "severity": data["max_severity"]
                })

            # 3. Mark processed in DB
            cursor.execute(
                """
                UPDATE collected_events
                SET status = 'PROCESSED', batch_id = %s, processed_at = NOW()
                WHERE id = ANY(%s);
                """,
                (batch_id, event_ids)
            )

            return {
                "batch_id": batch_id,
                "total_raw_events": raw_count,
                "deduplicated_count": len(deduped_targets),
                "deduplicated_targets": deduped_targets,
                "summary": f"Absorbed {raw_count} raw alarms into {len(deduped_targets)} distinct actionable targets."
            }

    @staticmethod
    def get_event_history(limit: int = 50, domain: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns recent raw webhook events with their batching and timestamp details."""
        with DatabasePool.get_cursor() as cursor:
            if domain:
                cursor.execute(
                    """
                    SELECT id, domain, host_target, alert_type, severity, payload, received_at, status, batch_id, processed_at
                    FROM collected_events
                    WHERE domain = %s
                    ORDER BY received_at DESC
                    LIMIT %s;
                    """,
                    (domain, limit)
                )
            else:
                cursor.execute(
                    """
                    SELECT id, domain, host_target, alert_type, severity, payload, received_at, status, batch_id, processed_at
                    FROM collected_events
                    ORDER BY received_at DESC
                    LIMIT %s;
                    """,
                    (limit,)
                )
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

