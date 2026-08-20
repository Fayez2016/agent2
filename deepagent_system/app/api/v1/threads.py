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
