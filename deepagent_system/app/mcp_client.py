import os
import json
import asyncio
import logging
from typing import List, Any
from app.config import MCP_SERVER_URL

logger = logging.getLogger("MCPClient")

def load_mcp_config_url() -> str:
    """Discovers MCP server URL from .mcp.json or returns default MCP_SERVER_URL."""
    mcp_config_path = "/app/.mcp.json" if os.path.exists("/app/.mcp.json") else ".mcp.json"
    if os.path.exists(mcp_config_path):
        try:
            with open(mcp_config_path, "r") as f:
                data = json.load(f)
                servers = data.get("mcpServers", {})
                if "ansible-mcp" in servers:
                    url = servers["ansible-mcp"].get("url")
                    if url:
                        logger.info(f"Discovered MCP URL '{url}' from .mcp.json config.")
                        return url
        except Exception as e:
            logger.warning(f"Error reading .mcp.json: {e}")
    return MCP_SERVER_URL

async def load_mcp_tools(server_url: str = None) -> List[Any]:
    """Loads all Ansible tools directly from Ansible MCP server using MultiServerMCPClient."""
    if not server_url:
        server_url = load_mcp_config_url()
        
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
        logger.info(f"Connecting MultiServerMCPClient to {server_url}...")
        
        client = MultiServerMCPClient({
            "ansible": {
                "url": server_url,
                "transport": "streamable_http"
            }
        })
        
        tools = await client.get_tools()
        logger.info(f"Loaded {len(tools)} native MCP tools successfully.")
        return tools
    except Exception as e:
        logger.error(f"Error loading tools via MultiServerMCPClient: {e}", exc_info=True)
        return []
