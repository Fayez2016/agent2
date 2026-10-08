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
        import json
        messages = ThreadRepository.get_messages(thread_id)
        if not messages:
            return {"markdown": "# Deep Agent SRE Report\n\nNo execution history recorded for this session."}
            
        md_lines = [
            f"# 📋 Deep Agent Infrastructure Execution & Post-Mortem Report",
            f"**Session ID:** `{thread_id}`",
            f"**Export Timestamp:** `{messages[-1].get('created_at', 'N/A')}`",
            f"**Total Operational Turns:** `{len(messages)}`\n",
            "---",
            "## 1. Conversational History & Operational Directives\n"
        ]
        
        for idx, m in enumerate(messages, 1):
            role_badge = "👤 **Operator Instruction**" if m.get("role") == "user" else "🤖 **Deep Agent Response & Tool Execution**"
            md_lines.append(f"### Step {idx}: {role_badge}")
            content_str = str(m.get("content") or "")
            md_lines.append(f"\n{content_str}\n")
            
            steps = m.get("intermediate_steps")
            if isinstance(steps, str):
                try:
                    steps = json.loads(steps)
                except Exception:
                    steps = []
            elif not isinstance(steps, list):
                steps = []
                    
            if steps and len(steps) > 0:
                md_lines.append("#### 🛠️ Executed Operations & FastMCP Tool Audit Trail:\n")
                for s_idx, s in enumerate(steps, 1):
                    if not isinstance(s, dict):
                        continue
                    t_name = s.get("tool_name") or s.get("target_subagent") or "Tool Call"
                    t_args = s.get("tool_args") or {}
                    hitl = f" `[HITL: {s.get('hitl_status')}]`" if s.get("hitl_status") else ""
                    step_type = str(s.get("step_type", "mcp_tool")).upper()
                    
                    md_lines.append(f"##### {s_idx}. `[{step_type}]` **`{t_name}`**{hitl}")
                    md_lines.append(f"- **Parameters:** `{json.dumps(t_args)}`")
                    if s.get("tool_output"):
                        out_snippet = str(s.get("tool_output")).strip()
                        md_lines.append(f"- **Output:**\n```text\n{out_snippet}\n```")
                    md_lines.append("")
            md_lines.append("\n---\n")
            
        return {"markdown": "\n".join(md_lines)}
    except Exception as e:
        logger.error(f"Failed to export thread {thread_id}: {e}", exc_info=True)
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
