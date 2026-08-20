import json
import uuid
import asyncio
import logging
from typing import List, Optional, Any, Dict
from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.config import settings
from app.agent_engine import init_deep_agent, execute_subagent_workflow_orchestrator
from app.infrastructure.db.thread_repository import ThreadRepository
from app.infrastructure.db.hitl_repository import HitlRepository
from app.infrastructure.db.database import DatabasePool

logger = logging.getLogger("ChatRouter")
router = APIRouter(prefix="/v1/chat", tags=["Chat"])

_AGENT_INSTANCE = None

async def get_agent():
    global _AGENT_INSTANCE
    if not _AGENT_INSTANCE:
        _AGENT_INSTANCE = await init_deep_agent()
    return _AGENT_INSTANCE

class Message(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: Optional[str] = "deepagent"
    messages: List[Message]
    stream: Optional[bool] = False
    thread_id: Optional[str] = None

def enrich_step_with_hitl(step: dict) -> dict:
    """Enriches step metadata with live database HITL audit status."""
    tool_name = step.get("tool_name", "")
    args = step.get("tool_args", {})
    target = args.get("hostlist") or args.get("hostname") or args.get("server") or args.get("vm_name") or ""
    
    # Check for approval in hitl_requests
    try:
        with DatabasePool.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT id, status, requested_at, resolved_at
                FROM hitl_requests
                ORDER BY requested_at DESC LIMIT 5;
                """
            )
            rows = cursor.fetchall()
            for r in rows:
                if r["status"] in ["GRANTED", "AUTONOMOUS_GRANTED"]:
                    step["hitl_status"] = r["status"]
                    step["hitl_request_id"] = r["id"]
                    step["hitl_resolved_at"] = r["resolved_at"].isoformat() if r["resolved_at"] else None
                    break
    except Exception as e:
        logger.warning(f"Error enriching step with HITL info: {e}")
        
    return step

@router.post("/completions")
async def chat_completions(request: ChatCompletionRequest, authorization: Optional[str] = Header(None)):
    """OpenAI-compatible Chat Completions endpoint supporting SSE streaming and REST responses."""
    # API key check
    if settings.api_server_key:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Unauthorized")
        token = authorization.split(" ")[1]
        if token != settings.api_server_key:
            raise HTTPException(status_code=403, detail="Forbidden")

    user_query = ""
    for msg in reversed(request.messages):
        if msg.role == "user":
            user_query = msg.content
            break

    if not user_query:
        raise HTTPException(status_code=400, detail="No user message provided")

    thread_id = request.thread_id
    if thread_id:
        try:
            ThreadRepository.add_message(thread_id=thread_id, role="user", content=user_query)
            ThreadRepository.update_thread_title(thread_id=thread_id, title=user_query[:35] + ("..." if len(user_query) > 35 else ""))
        except Exception as e:
            logger.warning(f"Failed to persist user message for thread: {e}")

    # Mode 1: Server-Sent Events (SSE) Streaming
    if request.stream:
        async def event_generator():
            yield f"data: {json.dumps({'event': 'status', 'data': 'Deep Agent analyzing cluster state & planning execution...'})}\n\n"
            
            try:
                orch_res = await execute_subagent_workflow_orchestrator(user_query)
                if orch_res:
                    intermediate_steps = []
                    for step in orch_res.get("intermediate_steps", []):
                        step = enrich_step_with_hitl(step)
                        intermediate_steps.append(step)
                        yield f"data: {json.dumps({'event': 'step', 'step': step})}\n\n"
                        await asyncio.sleep(1.2)
                    response_text = orch_res.get("response_text", "Operation completed.")
                else:
                    agent = await get_agent()
                    result = await agent.ainvoke(
                        {"messages": [{"role": "user", "content": user_query}]},
                        config={"recursion_limit": 10}
                    )
                    intermediate_steps = []
                    response_text = "The requested infrastructure operation was executed via Ansible MCP tools."

                # Stream response tokens
                words = response_text.split(" ")
                for i, word in enumerate(words):
                    chunk = word + (" " if i < len(words) - 1 else "")
                    yield f"data: {json.dumps({'event': 'token', 'token': chunk, 'chunk': chunk})}\n\n"
                    await asyncio.sleep(0.015)

                if thread_id:
                    try:
                        ThreadRepository.add_message(
                            thread_id=thread_id,
                            role="assistant",
                            content=response_text,
                            intermediate_steps=intermediate_steps
                        )
                    except Exception as e:
                        logger.warning(f"Failed to persist assistant message: {e}")

                yield f"data: {json.dumps({'event': 'done', 'response_text': response_text, 'steps': intermediate_steps})}\n\n"

            except Exception as e:
                logger.error(f"Error in SSE stream: {e}", exc_info=True)
                yield f"data: {json.dumps({'event': 'error', 'error': str(e)})}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    # Mode 2: Standard REST JSON Response
    try:
        orch_res = await execute_subagent_workflow_orchestrator(user_query)
        if orch_res:
            intermediate_steps = [enrich_step_with_hitl(s) for s in orch_res.get("intermediate_steps", [])]
            response_text = orch_res.get("response_text", "Operation completed.")
        else:
            agent = await get_agent()
            result = await agent.ainvoke(
                {"messages": [{"role": "user", "content": user_query}]},
                config={"recursion_limit": 10}
            )
            intermediate_steps = []
            response_text = "The requested infrastructure operation was executed via Ansible MCP tools."

        if thread_id:
            try:
                ThreadRepository.add_message(
                    thread_id=thread_id,
                    role="assistant",
                    content=response_text,
                    intermediate_steps=intermediate_steps
                )
            except Exception as e:
                logger.warning(f"Failed to persist assistant message: {e}")

        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
            "object": "chat.completion",
            "model": request.model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": response_text
                    },
                    "finish_reason": "stop"
                }
            ],
            "intermediate_steps": intermediate_steps
        }
    except Exception as e:
        logger.error(f"Error processing chat completion: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
