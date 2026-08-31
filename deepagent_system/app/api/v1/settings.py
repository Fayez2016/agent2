from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.infrastructure.db.hitl_repository import HitlRepository

router = APIRouter(prefix="/v1/settings", tags=["Settings"])

class ModeUpdateRequest(BaseModel):
    mode: str  # enforced or autonomous

@router.get("/hitl_mode")
async def get_hitl_mode():
    """Returns current system guardrail mode ('enforced' vs 'autonomous')."""
    try:
        mode = HitlRepository.get_guardrail_mode()
        return {"mode": mode}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch hitl_mode: {e}")

@router.post("/hitl_mode")
async def update_hitl_mode(req: ModeUpdateRequest):
    """Updates system guardrail mode."""
    target_mode = req.mode.strip().lower()
    if target_mode not in ["enforced", "autonomous"]:
        raise HTTPException(status_code=400, detail="Mode must be 'enforced' or 'autonomous'")
        
    try:
        success = HitlRepository.set_guardrail_mode(target_mode)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to persist setting in DB")
        return {"status": "success", "mode": target_mode}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update hitl_mode: {e}")

class DBCleanupRequest(BaseModel):
    purge_threads: bool = True
    purge_hitl: bool = True
    keep_days: int = 0  # 0 means purge all

@router.post("/db/cleanup")
async def cleanup_database_endpoint(req: DBCleanupRequest):
    """Purges old threads, message history, and HITL authorization audits based on retention policy."""
    try:
        from app.infrastructure.db.thread_repository import ThreadRepository
        stats = {
            "deleted_messages": 0,
            "deleted_threads": 0,
            "deleted_hitl_requests": 0,
            "retention_days": req.keep_days
        }

        if req.purge_threads:
            if req.keep_days > 0:
                t_stats = ThreadRepository.purge_older_than(req.keep_days)
            else:
                t_stats = ThreadRepository.purge_all()
            stats["deleted_messages"] = t_stats["deleted_messages"]
            stats["deleted_threads"] = t_stats["deleted_threads"]

        if req.purge_hitl:
            if req.keep_days > 0:
                h_count = HitlRepository.purge_older_than(req.keep_days)
            else:
                h_count = HitlRepository.purge_all()
            stats["deleted_hitl_requests"] = h_count

        return {"status": "success", "stats": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database cleanup failed: {e}")
