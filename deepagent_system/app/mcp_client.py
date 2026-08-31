import os
import json
import asyncio
import logging
from typing import List, Any, Dict, Optional
from app.config import settings

logger = logging.getLogger("MCPClient")

def load_mcp_servers_config(domain_scope: Optional[str] = None) -> Dict[str, str]:
    """
    Discovers all MCP server endpoints dynamically from PostgreSQL database (mcp_servers table),
    falling back to .mcp.json or environment settings.
    """
    servers = {}

    # 1. Primary Source: PostgreSQL mcp_servers table
    try:
        from app.infrastructure.db.agent_repository import AgentRepository
        db_servers = AgentRepository.get_all_mcp_servers(domain_scope=domain_scope, only_active=True)
        for s in db_servers:
            servers[s["name"]] = s["url"]
            logger.info(f"Loaded active MCP server from DB: '{s['name']}' ({s.get('domain_scope', 'global')}) -> '{s['url']}'")
    except Exception as e:
        logger.warning(f"Could not load MCP servers from database: {e}")

    # 2. Fallback / Defaults if DB query empty
    if not servers:
        servers = {
            "ansible": settings.ansible_mcp_url,
            "sop": settings.sop_mcp_url
        }

    return servers

async def load_mcp_tools(server_url: str = None, domain_scope: Optional[str] = None) -> List[Any]:
    """
    Loads tools from multiple specialized FastMCP servers simultaneously
    using official MultiServerMCPClient over streamable HTTP transport.
    """
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
        servers_config = load_mcp_servers_config(domain_scope=domain_scope)
        
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
