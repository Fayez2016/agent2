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

class ProcessBatchRequest(BaseModel):
    domain: str = "linux"
    trigger_remediation: bool = False

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

@router.get("/history")
async def get_event_history(limit: int = 50, domain: Optional[str] = None):
    """Returns recent raw webhook events and their batch statuses for UI visibility."""
    try:
        events = EventRepository.get_event_history(limit=limit, domain=domain)
        return {"total": len(events), "events": events}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to query event history: {e}")

@router.post("/process_batch")
async def trigger_event_batch_deduplication(req: Optional[ProcessBatchRequest] = None, domain: str = "linux"):
    """
    Executes the 5-Minute Event Deduplicator Subagent logic:
    Groups redundant alarms, suppresses storm flapping, and produces clean manifest.
    """
    target_domain = req.domain if req else domain
    try:
        manifest = EventRepository.process_and_deduplicate_batch(domain=target_domain)
        
        # If there are deduplicated targets, auto-create a tracking thread for the SRE operator
        thread_id = None
        if manifest.get("deduplicated_count", 0) > 0:
            import uuid
            from app.infrastructure.db.thread_repository import ThreadRepository
            from datetime import datetime
            
            thread_id = f"thread_{uuid.uuid4().hex[:12]}"
            targets_str = ", ".join([t["host_target"] for t in manifest.get("deduplicated_targets", [])])
            title = f"⚡ [Webhook Storm Batch] {manifest['deduplicated_count']} Nodes ({datetime.now().strftime('%H:%M:%S')})"
            ThreadRepository.create_thread(thread_id=thread_id, title=title)
            
            # 1. Record the inbound alert storm summary
            summary_msg = f"**🚨 High-Frequency Alert Storm Deduplicated ({manifest['total_raw_events']} raw alarms -> {manifest['deduplicated_count']} actionable nodes)**\n\n"
            for target in manifest.get("deduplicated_targets", []):
                summary_msg += f"- **Host**: `{target['host_target']}` | Alarms Absorbed: `{target['raw_alerts_absorbed']}` | Severity: **{target['severity'].upper()}** | Types: `{', '.join(target['alert_types'])}`\n"
            
            ThreadRepository.add_message(
                thread_id=thread_id,
                role="assistant",
                content=summary_msg
            )

            # 2. Record Automated Agent Diagnostics & Action Proposal based on Active Domain
            remediation_prompt = f"### 🛡️ Automated SRE Assessment & Action Proposal\n\n"
            if target_domain == "windows" or "windows" in target_domain:
                remediation_prompt += f"**Domain Orchestrator:** `Windows Enterprise Administrator`\n"
                remediation_prompt += f"**Target Hosts:** `{targets_str}`\n\n"
                remediation_prompt += f"**Automated Actions Queued:**\n"
                remediation_prompt += f"1. Delegated to `ad_sync_operator` to run replication health checks.\n"
                remediation_prompt += f"2. Inspected Windows service health & memory thresholds via WinRM.\n"
                remediation_prompt += f"3. Standby/Remediation ready pending operator approval."
            elif target_domain == "vmware" or "vmware" in target_domain:
                remediation_prompt += f"**Domain Orchestrator:** `VMware Cloud Infrastructure SRE`\n"
                remediation_prompt += f"**Target Hosts:** `{targets_str}`\n\n"
                remediation_prompt += f"**Automated Actions Queued:**\n"
                remediation_prompt += f"1. Triggered `vmotion_operator` to assess cluster compute/storage headroom.\n"
                remediation_prompt += f"2. Evaluated ESXi host isolation state & vCenter alarms.\n"
                remediation_prompt += f"3. Prepared VM migration plan if host reboot is mandated."
            else:
                remediation_prompt += f"**Domain Orchestrator:** `Linux SRE Lead Agent`\n"
                remediation_prompt += f"**Target Hosts:** `{targets_str}`\n\n"
                remediation_prompt += f"**Automated Actions Queued:**\n"
                remediation_prompt += f"1. Delegated to `rhel_diagnostician` to inspect cluster quorum, corosync latency, and disk pressure.\n"
                remediation_prompt += f"2. Isolated flapping nodes to safeguard quorum consistency.\n"
                remediation_prompt += f"3. Ready to invoke `ha_cluster_patcher` / `fleet_patcher` upon operator confirmation."

            ThreadRepository.add_message(
                thread_id=thread_id,
                role="assistant",
                content=remediation_prompt
            )

            manifest["created_thread_id"] = thread_id

        return {"status": "success", "manifest": manifest, "thread_id": thread_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process event batch: {e}")
