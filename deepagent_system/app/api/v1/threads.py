from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from app.infrastructure.db.thread_repository import ThreadRepository

router = APIRouter(prefix="/v1/threads", tags=["Threads"])

class ThreadCreateRequest(BaseModel):
    id: Optional[str] = None
    title: Optional[str] = "New Conversation"

@router.get("")
async def list_threads():
    """Lists all active conversation threads for the Web UI sidebar."""
    try:
        threads = ThreadRepository.get_all_threads()
        return {"threads": threads}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch threads: {e}")

@router.post("")
async def create_new_thread(req: ThreadCreateRequest):
    """Creates a new conversational thread."""
    import uuid
    thread_id = req.id or f"thread_{uuid.uuid4().hex[:12]}"
    title = req.title or "New Conversation"
    try:
        thread = ThreadRepository.create_thread(thread_id, title)
        return thread
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create thread: {e}")

@router.get("/{thread_id}/messages")
async def get_thread_messages(thread_id: str):
    """Retrieves all message history and JSONB tool traces for a thread."""
    try:
        messages = ThreadRepository.get_messages(thread_id)
        return {"messages": messages, "thread_id": thread_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load messages for thread {thread_id}: {e}")

@router.get("/{thread_id}/export")
async def export_thread(thread_id: str):
    """Generates a complete SRE Post-Mortem & Audit Report in Markdown for the thread."""
    try:
        messages = ThreadRepository.get_messages(thread_id)
        if not messages:
            return {"markdown": "# Deep Agent SRE Report\n\nNo execution history recorded for this session."}
            
        md_lines = [
            f"# 📋 Deep Agent Infrastructure Execution & Post-Mortem Report",
            f"**Session ID:** `{thread_id}`",
            f"**Export Timestamp:** `{messages[-1].get('created_at', 'N/A')}`\n",
            "---",
            "## 1. Conversational History & Operational Directives\n"
        ]
        
        for idx, m in enumerate(messages, 1):
            role_badge = "👤 **Operator Instruction**" if m["role"] == "user" else "🤖 **Deep Agent Response**"
            md_lines.append(f"### Step {idx}: {role_badge}")
            md_lines.append(m["content"])
            
            steps = m.get("intermediate_steps")
            if isinstance(steps, str):
                import json
                try:
                    steps = json.loads(steps)
                except Exception:
                    steps = []
                    
            if steps and len(steps) > 0:
                md_lines.append("\n#### FastMCP Execution & Subagent Audit Trail:")
                for s in steps:
                    t_name = s.get("tool_name") or s.get("target_subagent") or "Tool Call"
                    t_args = s.get("tool_args") or {}
                    hitl = f" [HITL: {s.get('hitl_status')}]" if s.get("hitl_status") else ""
                    md_lines.append(f"- **`{t_name}`**{hitl}: `{t_args}`")
            md_lines.append("\n---\n")
            
        return {"markdown": "\n".join(md_lines)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export thread: {e}")

@router.delete("/{thread_id}")
async def delete_thread(thread_id: str):
    """Deletes a thread and all associated messages."""
    try:
        deleted = ThreadRepository.delete_thread(thread_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Thread not found")
        return {"status": "success", "thread_id": thread_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete thread: {e}")
