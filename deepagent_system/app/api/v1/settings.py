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
