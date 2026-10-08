import logging
from typing import List, Dict, Any
from langchain_core.tools import BaseTool
from app.mcp_client import load_mcp_tools

logger = logging.getLogger("AnsibleMCPTools")

_CACHED_MCP_TOOLS: List[BaseTool] = []

async def get_ansible_mcp_tools() -> List[BaseTool]:
    """Returns aggregated tools from Ansible (:8000) and SOP (:8001) FastMCP servers."""
    global _CACHED_MCP_TOOLS
    if not _CACHED_MCP_TOOLS:
        _CACHED_MCP_TOOLS = await load_mcp_tools()
    return _CACHED_MCP_TOOLS

async def get_tools_map() -> Dict[str, BaseTool]:
    """Returns dictionary mapping tool name to tool instance."""
    tools = await get_ansible_mcp_tools()
    return {t.name: t for t in tools}
