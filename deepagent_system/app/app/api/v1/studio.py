import json
import logging
import httpx
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.infrastructure.db.agent_repository import AgentRepository

logger = logging.getLogger("StudioRouter")
router = APIRouter(prefix="/v1/studio", tags=["Agent & MCP Studio"])

# --- Models ---
class MCPServerCreateRequest(BaseModel):
    name: str
    display_name: Optional[str] = None
    domain_scope: str = "linux"
    url: str
    transport: str = "streamable_http"
    headers: Optional[Dict[str, Any]] = None

class SkillCreateRequest(BaseModel):
    name: str
    display_name: Optional[str] = None
    domain_category: str = "linux"
    description: Optional[str] = ""
    content_markdown: str

class AgentCreateRequest(BaseModel):
    key_name: str
    display_name: str
    domain_category: str
    description: Optional[str] = ""
    model_provider: str = "openrouter"
    model_name: str = "qwen/qwen-2.5-72b-instruct"
    system_prompt: str

class SubagentCreateRequest(BaseModel):
    parent_agent_id: int
    name: str
    display_name: Optional[str] = None
    description: str
    system_prompt: str
    tool_bindings: Optional[List[str]] = None
    skills_path: str = "/app/skills/"

# --- MCP Endpoints ---
@router.get("/mcp_servers")
async def list_mcp_servers():
    """Returns all registered MCP servers from PostgreSQL."""
    try:
        servers = AgentRepository.get_all_mcp_servers(only_active=False)
        return {"servers": servers, "count": len(servers)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to query MCP servers: {e}")

@router.post("/mcp_servers")
async def save_mcp_server(req: MCPServerCreateRequest):
    """Registers or updates an MCP server endpoint."""
    try:
        server_id = AgentRepository.upsert_mcp_server(
            name=req.name.strip().lower(),
            display_name=req.display_name or req.name,
            domain_scope=req.domain_scope.strip().lower(),
            url=req.url.strip(),
            transport=req.transport,
            headers=req.headers
        )
        return {"status": "success", "id": server_id, "name": req.name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to register MCP server: {e}")

@router.post("/mcp_servers/{server_name}/ping")
async def ping_mcp_server(server_name: str):
    """Live test probe to connect to an MCP server and list available exposed tools."""
    try:
        servers = AgentRepository.get_all_mcp_servers(only_active=False)
        target = next((s for s in servers if s["name"] == server_name), None)
        if not target:
            raise HTTPException(status_code=404, detail=f"MCP server '{server_name}' not found")

        # Test socket HTTP probe
        url = target["url"]
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Probe endpoint
            res = await client.get(url if not url.endswith("/mcp") else url.replace("/mcp", "/docs"), follow_redirects=True)
            status_code = res.status_code

        # Attempt to load tools via MultiServerMCPClient
        from app.mcp_client import load_mcp_tools
        tools = await load_mcp_tools(domain_scope=target.get("domain_scope"))
        tool_names = [t.name for t in tools]

        return {
            "status": "connected",
            "server": server_name,
            "url": url,
            "http_status": status_code,
            "live_tools_count": len(tool_names),
            "tools": tool_names
        }
    except HTTPException:
        raise
    except Exception as e:
        return {
            "status": "unreachable",
            "server": server_name,
            "error": str(e)
        }

# --- Skills Endpoints ---
@router.get("/skills")
async def list_skills():
    """Returns all domain skills & SOPs from PostgreSQL."""
    try:
        skills = AgentRepository.get_all_skills(only_enabled=False)
        return {"skills": skills, "count": len(skills)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list skills: {e}")

@router.post("/skills")
async def save_skill(req: SkillCreateRequest):
    """Creates or updates a markdown skill/SOP."""
    try:
        skill_id = AgentRepository.upsert_skill(
            name=req.name.strip().lower(),
            display_name=req.display_name or req.name,
            domain_category=req.domain_category.strip().lower(),
            description=req.description,
            content_markdown=req.content_markdown
        )
        return {"status": "success", "id": skill_id, "name": req.name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save skill: {e}")

# --- Domain Agents & Subagents Endpoints ---
@router.get("/agents")
async def list_agents():
    """Returns all domain main agents and their subagents from PostgreSQL."""
    try:
        agents = AgentRepository.get_all_agents(only_active=False)
        return {"agents": agents, "count": len(agents)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list agents: {e}")

@router.post("/agents")
async def save_agent(req: AgentCreateRequest):
    """Creates or updates a Main Domain Agent."""
    try:
        agent_id = AgentRepository.upsert_agent(
            key_name=req.key_name.strip().lower(),
            display_name=req.display_name,
            domain_category=req.domain_category.strip().lower(),
            description=req.description or "",
            model_provider=req.model_provider,
            model_name=req.model_name,
            system_prompt=req.system_prompt
        )
        return {"status": "success", "id": agent_id, "key_name": req.key_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save agent: {e}")

@router.post("/subagents")
async def save_subagent(req: SubagentCreateRequest):
    """Creates or updates a Subagent bound to a Main Agent."""
    try:
        sub_id = AgentRepository.upsert_subagent(
            parent_agent_id=req.parent_agent_id,
            name=req.name.strip().lower(),
            display_name=req.display_name or req.name,
            description=req.description,
            system_prompt=req.system_prompt,
            tool_bindings=req.tool_bindings or [],
            skills_path=req.skills_path
        )
        return {"status": "success", "id": sub_id, "name": req.name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save subagent: {e}")

@router.delete("/mcp_servers/{name}")
async def delete_mcp_server(name: str):
    """Deletes an MCP server registry from PostgreSQL."""
    try:
        success = AgentRepository.delete_mcp_server(name)
        if not success:
            raise HTTPException(status_code=404, detail=f"MCP server '{name}' not found")
        return {"status": "success", "deleted": name}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete MCP server: {e}")

@router.delete("/agents/{key_name}")
async def delete_agent(key_name: str):
    """Deletes a Domain Main Agent and its subagents from PostgreSQL."""
    try:
        success = AgentRepository.delete_agent(key_name)
        if not success:
            raise HTTPException(status_code=404, detail=f"Agent '{key_name}' not found")
        return {"status": "success", "deleted": key_name}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete agent: {e}")

@router.delete("/skills/{name}")
async def delete_skill(name: str):
    """Deletes a declarative skill/SOP from PostgreSQL."""
    try:
        success = AgentRepository.delete_skill(name)
        if not success:
            raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
        return {"status": "success", "deleted": name}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete skill: {e}")
