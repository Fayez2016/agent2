from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from app.infrastructure.db.event_repository import EventRepository

router = APIRouter(prefix="/v1/events", tags=["Events & Webhooks"])

class AlertEventRequest(BaseModel):
    host_target: str
    alert_type: str
    severity: str = "warning"
    domain: str = "linux"
    payload: Optional[Dict[str, Any]] = None

class BulkAlertEventRequest(BaseModel):
    events: List[AlertEventRequest]
    domain: str = "linux"

@router.post("/webhook")
async def ingest_webhook_alert(req: AlertEventRequest):
    """Ingests a high-frequency monitoring webhook alarm into the buffer."""
    try:
        ev = EventRepository.ingest_event(
            host_target=req.host_target,
            alert_type=req.alert_type,
            severity=req.severity,
            domain=req.domain,
            payload=req.payload
        )
        return {"status": "buffered", "event_id": ev["id"], "host_target": ev["host_target"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to buffer webhook event: {e}")

@router.post("/bulk")
async def ingest_bulk_alerts(req: BulkAlertEventRequest):
    """Ingests a flood of alerts concurrently in bulk."""
    try:
        events_dicts = [e.dict() for e in req.events]
        ingested = EventRepository.ingest_bulk_events(events_dicts, domain=req.domain)
        return {"status": "buffered", "count": ingested}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bulk ingestion error: {e}")

@router.get("/pending")
async def get_pending_buffer(domain: str = "linux"):
    """Returns currently buffered pending alerts."""
    try:
        pending = EventRepository.get_pending_events(domain=domain)
        return {"pending_count": len(pending), "events": pending}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to query event buffer: {e}")

@router.post("/process_batch")
async def trigger_event_batch_deduplication(domain: str = "linux"):
    """
    Executes the 5-Minute Event Deduplicator Subagent logic:
    Groups redundant alarms, suppresses storm flapping, and produces clean manifest.
    """
    try:
        manifest = EventRepository.process_and_deduplicate_batch(domain=domain)
        return {"status": "success", "manifest": manifest}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process event batch: {e}")
