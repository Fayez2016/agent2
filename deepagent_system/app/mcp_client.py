import os
import json
import asyncio
import logging
from typing import List, Any, Dict
from app.config import settings

logger = logging.getLogger("MCPClient")

def load_mcp_servers_config() -> Dict[str, str]:
    """
    Discovers all MCP server endpoints from .mcp.json or uses settings defaults.
    Supports MultiServerMCPClient topology (Ansible Execution + SOP Knowledge).
    """
    servers = {
        "ansible": settings.ansible_mcp_url,
        "sop": settings.sop_mcp_url
    }
    
    mcp_config_path = "/app/.mcp.json" if os.path.exists("/app/.mcp.json") else ".mcp.json"
    if os.path.exists(mcp_config_path):
        try:
            with open(mcp_config_path, "r") as f:
                data = json.load(f)
                configured_servers = data.get("mcpServers", {})
                for name, s_cfg in configured_servers.items():
                    url = s_cfg.get("url")
                    if url:
                        key = "ansible" if "ansible" in name else ("sop" if "sop" in name else name)
                        servers[key] = url
                        logger.info(f"Discovered MCP server '{key}' -> '{url}' from .mcp.json")
        except Exception as e:
            logger.warning(f"Error reading .mcp.json: {e}")
            
    return servers

async def load_mcp_tools(server_url: str = None) -> List[Any]:
    """
    Loads tools from multiple specialized FastMCP servers simultaneously
    using official MultiServerMCPClient over streamable HTTP transport.
    """
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
        servers_config = load_mcp_servers_config()
        
        # Build multi-server dictionary
        client_dict = {}
        for s_name, s_url in servers_config.items():
            client_dict[s_name] = {
                "url": s_url,
                "transport": "streamable_http"
            }
            
        logger.info(f"Connecting MultiServerMCPClient to servers: {list(client_dict.keys())}...")
        client = MultiServerMCPClient(client_dict)
        
        tools = await client.get_tools()
        logger.info(f"Loaded {len(tools)} native tools across {len(client_dict)} MCP servers successfully.")
        return tools
    except Exception as e:
        logger.error(f"Error loading tools via MultiServerMCPClient: {e}", exc_info=True)
        # Fallback to single Ansible server if SOP server is unreachable
        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient
            fallback_url = server_url or settings.ansible_mcp_url
            fallback_client = MultiServerMCPClient({
                "ansible": {
                    "url": fallback_url,
                    "transport": "streamable_http"
                }
            })
            return await fallback_client.get_tools()
        except Exception as fallback_err:
            logger.error(f"Fallback MCP connection also failed: {fallback_err}")
            return []
