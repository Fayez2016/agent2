from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List
from app.infrastructure.db.hitl_repository import HitlRepository

router = APIRouter(prefix="/v1/hitl", tags=["HITL"])

class ResolveRequest(BaseModel):
    request_id: int
    decision: str  # GRANTED or REJECTED

@router.get("/pending")
async def get_pending_hitl():
    """Returns all pending HITL authorization requests for the Web UI modal."""
    try:
        pending = HitlRepository.get_pending_requests()
        return {"pending": pending, "count": len(pending)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to query pending HITL requests: {e}")

@router.post("/resolve")
async def resolve_hitl(req: ResolveRequest):
    """Submits operator decision (GRANTED / REJECTED) for a high-risk tool call."""
    try:
        if req.decision.upper() not in ["GRANTED", "REJECTED"]:
            raise HTTPException(status_code=400, detail="Decision must be 'GRANTED' or 'REJECTED'")
            
        success = HitlRepository.resolve_request(req.request_id, req.decision)
        if not success:
            raise HTTPException(status_code=404, detail="Request not found or already resolved")
            
        return {"status": "success", "request_id": req.request_id, "decision": req.decision.upper()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to resolve HITL request: {e}")

@router.get("/request/{request_id}")
async def get_hitl_request(request_id: int):
    """Fetches details of a specific HITL request."""
    req = HitlRepository.get_request_by_id(request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    return req

@router.get("/history")
async def get_hitl_history():
    """Fetches full compliance audit history from PostgreSQL."""
    try:
        history = HitlRepository.get_audit_history(limit=150)
        return {"history": history, "count": len(history)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to query audit history: {e}")
