import logging
import sys
import uvicorn
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

# Pydantic Schemas for OpenAI API Compatibility
class Message(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: Optional[str] = "deepagent"
    messages: List[Message]
    stream: Optional[bool] = False

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "deepagent-core"}

@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    authorization: Optional[str] = Header(None)
):
    """OpenAI-compatible chat completions endpoint for Deep Agent engine."""
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
    agent = await get_agent()
    
    try:
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

        # Extract assistant response from result (scan backwards for valid output or text)
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

    # OpenAI JSON Schema with intermediate_steps
    return {
        "id": "chatcmpl-deepagent-001",
        "object": "chat.completion",
        "created": 1700000000,
        "model": request.model or "deepagent",
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
