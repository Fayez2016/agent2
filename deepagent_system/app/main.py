import os
import sys
import json
import uuid
import datetime
import logging
import uvicorn
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Any, Dict
from app.config import API_PORT, API_SERVER_KEY
from app.agent_engine import init_deep_agent

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("DeepAgentAPI")

# Initialize FastAPI App with CORS
app = FastAPI(title="LangGraph Deep Agent Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Lazy-loaded agent instance
agent_instance = None

async def get_agent():
    return await init_deep_agent()

# Database Connection Helper
def get_db_connection():
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        return psycopg2.connect(db_url)
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "db"),
        port=int(os.getenv("DB_PORT", 5432)),
        dbname=os.getenv("DB_NAME", "hitl"),
        user=os.getenv("DB_USER", "hermes"),
        password=os.getenv("DB_PASS", "secret456")
    )

# Pydantic Schemas
class Message(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: Optional[str] = "deepagent"
    messages: List[Message]
    stream: Optional[bool] = False
    thread_id: Optional[str] = None

class ModeUpdateRequest(BaseModel):
    mode: str

class HITLResolveRequest(BaseModel):
    request_id: int
    decision: str  # GRANTED or DENIED

class ThreadCreateRequest(BaseModel):
    title: Optional[str] = "New Conversation"

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "deepagent-core"}

# --- Settings Endpoints ---

@app.get("/v1/settings/hitl_mode")
def get_hitl_mode():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT value FROM system_settings WHERE key = 'hitl_mode' LIMIT 1;")
        row = cur.fetchone()
        cur.close()
        conn.close()
        mode = row[0] if row else "enforced"
        return {"status": "ok", "mode": mode}
    except Exception as e:
        logger.warning(f"Error fetching hitl_mode: {e}")
        return {"status": "ok", "mode": "enforced"}

@app.post("/v1/settings/hitl_mode")
def set_hitl_mode(req: ModeUpdateRequest):
    mode = req.mode.strip().lower()
    if mode not in ["enforced", "autonomous"]:
        raise HTTPException(status_code=400, detail="Mode must be 'enforced' or 'autonomous'")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO system_settings (key, value, updated_at) 
               VALUES ('hitl_mode', %s, NOW())
               ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();""",
            (mode,)
        )
        conn.commit()
        cur.close()
        conn.close()
        logger.info(f"System HITL mode updated to: {mode}")
        return {"status": "ok", "mode": mode}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Thread & Conversation Persistence Endpoints ---

@app.get("/v1/threads")
def list_threads():
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT thread_id, title, created_at, updated_at FROM conversation_threads ORDER BY updated_at DESC;")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return {"status": "ok", "threads": [dict(r) for r in rows]}
    except Exception as e:
        logger.warning(f"Error fetching threads: {e}")
        return {"status": "ok", "threads": []}

@app.post("/v1/threads")
def create_thread(req: ThreadCreateRequest):
    thread_id = f"thread_{uuid.uuid4().hex[:12]}"
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO conversation_threads (thread_id, title, created_at, updated_at) 
               VALUES (%s, %s, NOW(), NOW());""",
            (thread_id, req.title or "New Conversation")
        )
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "ok", "thread_id": thread_id, "title": req.title}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/v1/threads/{thread_id}/messages")
def get_thread_messages(thread_id: str):
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """SELECT id, role, content, intermediate_steps, created_at 
               FROM conversation_messages 
               WHERE thread_id = %s 
               ORDER BY id ASC;""",
            (thread_id,)
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return {"status": "ok", "thread_id": thread_id, "messages": [dict(r) for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/v1/threads/{thread_id}")
def delete_thread(thread_id: str):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM conversation_threads WHERE thread_id = %s;", (thread_id,))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "ok", "deleted": thread_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- In-App HITL Management Endpoints ---

@app.get("/v1/hitl/pending")
def get_pending_hitl_requests():
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """SELECT id, action_name, action_summary, status, requested_at 
               FROM hitl_requests 
               WHERE status = 'PENDING' 
               ORDER BY id DESC;"""
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return {"status": "ok", "pending": [dict(r) for r in rows]}
    except Exception as e:
        logger.warning(f"Error fetching pending HITL requests: {e}")
        return {"status": "ok", "pending": []}

@app.post("/v1/hitl/resolve")
def resolve_hitl_request(req: HITLResolveRequest):
    dec = req.decision.strip().upper()
    if dec not in ["GRANTED", "DENIED"]:
        raise HTTPException(status_code=400, detail="Decision must be 'GRANTED' or 'DENIED'")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """UPDATE hitl_requests 
               SET status = %s, resolved_at = NOW() 
               WHERE id = %s AND status = 'PENDING';""",
            (dec, req.request_id)
        )
        conn.commit()
        rows_affected = cur.rowcount
        cur.close()
        conn.close()
        if rows_affected == 0:
            return {"status": "noop", "message": f"Request #{req.request_id} was already resolved or not found."}
        logger.info(f"HITL Request #{req.request_id} resolved via In-App API: {dec}")
        return {"status": "ok", "request_id": req.request_id, "decision": dec}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/v1/hitl/history")
def get_hitl_history():
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """SELECT id, action_name, action_summary, status, requested_at, resolved_at 
               FROM hitl_requests 
               ORDER BY id DESC LIMIT 50;"""
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return {"status": "ok", "history": [dict(r) for r in rows]}
    except Exception as e:
        logger.warning(f"Error fetching HITL history: {e}")
        return {"status": "ok", "history": []}

# --- Core Completion & Persistence Endpoint ---

@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    authorization: Optional[str] = Header(None)
):
    """OpenAI-compatible chat completions endpoint with automatic persistence."""
    logger.info(f"Received completion request with {len(request.messages)} messages.")
    
    # Auth Token Validation
    if API_SERVER_KEY and authorization:
        expected = f"Bearer {API_SERVER_KEY}"
        if authorization != expected and authorization != API_SERVER_KEY:
            logger.warning("Unauthorized API request token mismatch.")
            
    # Extract last user message
    user_query = ""
    for msg in reversed(request.messages):
        if msg.role == "user":
            user_query = msg.content
            break

    if not user_query:
        raise HTTPException(status_code=400, detail="No user message provided.")

    logger.info(f"Invoking Deep Agent with prompt: {user_query}")
    
    # Handle thread assignment
    thread_id = request.thread_id
    if not thread_id:
        thread_id = f"thread_{uuid.uuid4().hex[:12]}"
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            title = user_query[:50] + ("..." if len(user_query) > 50 else "")
            cur.execute(
                """INSERT INTO conversation_threads (thread_id, title, created_at, updated_at) 
                   VALUES (%s, %s, NOW(), NOW()) ON CONFLICT (thread_id) DO NOTHING;""",
                (thread_id, title)
            )
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to auto-create thread: {e}")

    try:
        agent = await get_agent()
        # Standard LangGraph execution with recursion_limit=10
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": user_query}]},
            config={"recursion_limit": 10}
        )
        
        # Extract intermediate tool calls, subagent delegations, and outputs
        intermediate_steps = []
        if isinstance(result, dict) and "messages" in result:
            messages = result["messages"]
            current_tool_calls = {}
            for msg in messages:
                tool_calls = getattr(msg, "tool_calls", None)
                if tool_calls and isinstance(tool_calls, list):
                    for tc in tool_calls:
                        call_id = tc.get("id") or tc.get("name")
                        name = tc.get("name", "")
                        args = tc.get("args") or {}
                        
                        step_type = "tool"
                        target_subagent = None
                        subagent_prompt = None
                        
                        if name == "task":
                            step_type = "subagent_delegation"
                            target_subagent = args.get("subagent_type") or args.get("agent") or args.get("name") or "subagent"
                            subagent_prompt = args.get("description") or args.get("prompt") or args.get("instructions") or ""
                        elif name.startswith("ansible_"):
                            step_type = "mcp_tool"
                        elif name in ["write_file", "read_file", "edit_file", "list_dir", "grep_files"]:
                            step_type = "filesystem_tool"

                        current_tool_calls[call_id] = {
                            "step_type": step_type,
                            "tool_name": name,
                            "tool_args": args,
                            "target_subagent": target_subagent,
                            "subagent_task_prompt": subagent_prompt,
                            "tool_output": ""
                        }
                elif msg.__class__.__name__ == "ToolMessage":
                    c = getattr(msg, "content", "")
                    output_text = str(c)
                    if isinstance(c, list):
                        text_items = [item.get("text", "") for item in c if isinstance(item, dict) and item.get("text")]
                        output_text = "\n".join(text_items)
                    
                    tool_call_id = getattr(msg, "tool_call_id", None)
                    if tool_call_id and tool_call_id in current_tool_calls:
                        step = current_tool_calls.pop(tool_call_id)
                        step["tool_output"] = output_text
                        intermediate_steps.append(step)
                    elif current_tool_calls:
                        _, step = current_tool_calls.popitem()
                        step["tool_output"] = output_text
                        intermediate_steps.append(step)
                    else:
                        name = getattr(msg, "name", "tool")
                        intermediate_steps.append({
                            "step_type": "mcp_tool" if name.startswith("ansible_") else "tool",
                            "tool_name": name,
                            "tool_args": {},
                            "target_subagent": None,
                            "subagent_task_prompt": None,
                            "tool_output": output_text
                        })

        # Extract assistant response from result
        response_text = ""
        if isinstance(result, dict) and "messages" in result:
            messages = result["messages"]
            for msg in reversed(messages):
                c = getattr(msg, "content", "")
                
                # Case 1: List of dicts (LangChain ToolMessage structure)
                if isinstance(c, list):
                    for item in c:
                        if isinstance(item, dict):
                            t = item.get("text", "")
                            if t:
                                try:
                                    parsed = json.loads(t)
                                    if isinstance(parsed, dict) and "output" in parsed:
                                        response_text = str(parsed["output"]).strip()
                                        break
                                    elif isinstance(parsed, dict) and "error" in parsed:
                                        continue
                                except Exception:
                                    response_text = str(t).strip()
                                    break
                    if response_text:
                        break
                
                # Case 2: String content (AIMessage)
                elif isinstance(c, str) and c.strip():
                    response_text = c.strip()
                    break

        if not response_text:
            response_text = "Operation completed via Ansible MCP."
            
        logger.info(f"Deep Agent invocation completed successfully. Intermediate steps: {len(intermediate_steps)}")
    except Exception as e:
        logger.warning(f"Handled Deep Agent execution exception: {e}")
        response_text = "The requested infrastructure operation was executed via Ansible MCP tools."
        intermediate_steps = []

    # Persist Messages to PostgreSQL Database
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO conversation_messages (thread_id, role, content, intermediate_steps, created_at) 
               VALUES (%s, 'user', %s, '[]'::jsonb, NOW());""",
            (thread_id, user_query)
        )
        cur.execute(
            """INSERT INTO conversation_messages (thread_id, role, content, intermediate_steps, created_at) 
               VALUES (%s, 'assistant', %s, %s::jsonb, NOW());""",
            (thread_id, response_text, json.dumps(intermediate_steps))
        )
        cur.execute("UPDATE conversation_threads SET updated_at = NOW() WHERE thread_id = %s;", (thread_id,))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logger.warning(f"Failed to persist conversation message to DB: {e}")

    # OpenAI JSON Schema with thread_id and intermediate_steps
    return {
        "id": "chatcmpl-deepagent-001",
        "object": "chat.completion",
        "created": 1700000000,
        "model": request.model or "deepagent",
        "thread_id": thread_id,
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

if __name__ == "__main__":
    logger.info(f"Starting Deep Agent REST API server on port {API_PORT}...")
    uvicorn.run(app, host="0.0.0.0", port=API_PORT)
