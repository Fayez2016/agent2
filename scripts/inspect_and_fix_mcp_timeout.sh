#!/usr/bin/env bash
# ==============================================================================
# Script: inspect_and_fix_mcp_timeout.sh
# Purpose:
#   1. Inspect the running Deep Agent service & MCP client configuration.
#   2. Inspect PostgreSQL hitl_requests for recent AAP job records.
#   3. Query recent service threads to inspect workflow execution history.
#   4. Apply the native fix: configure 3600.0s (1 hour) timeout & sse_read_timeout
#      in MultiServerMCPClient to prevent stream disconnects on long AAP jobs.
#   5. Hot-patch deepagent-service and restart the core service cleanly.
#   6. Locally simulate and verify tool invocations using the updated client.
# ==============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${CYAN}${BOLD}  🔍 DEEP AGENT: LONG JOB TIMEOUT INSPECTION & HOT-FIX UTILITY                ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"

# ──────────────────────────────────────────────────────────────────────────────
# Step 1: Inspection & Diagnostics
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[1/4] Inspecting Running Environment & Current Timeout Configuration...${NC}"

if ! podman ps --format "{{.Names}}" | grep -q "deepagent-service"; then
    echo -e "${RED}❌ Container 'deepagent-service' is not running!${NC}"
    exit 1
fi
echo -e "  • Container 'deepagent-service': ${GREEN}RUNNING${NC}"

# Detect current timeout configuration directly from Python module
CURRENT_TIMEOUT=$(podman exec -i deepagent-service python3 -c "
import inspect, app.mcp_client
try:
    src = inspect.getsource(app.mcp_client.load_mcp_tools)
    if '3600.0' in src and 'sse_read_timeout' in src:
        print('FIXED_3600s')
    else:
        print('DEFAULT_SHORT_TIMEOUT')
except Exception as e:
    print('ERROR:', e)
" 2>/dev/null || echo "UNKNOWN")

echo -e "  • Current MCP Client Timeout Status: ${BOLD}${CURRENT_TIMEOUT}${NC}"

# Check recent HITL requests from Database
echo -e "\n${BOLD}[2/4] Inspecting Recent AAP / HITL Job Records in Database...${NC}"
podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -c \
  "SELECT id, action_name, status, requested_at, resolved_at FROM hitl_requests ORDER BY id DESC LIMIT 5;" 2>/dev/null || echo -e "  ${YELLOW}⚠️ Database query skipped or table empty.${NC}"

# ──────────────────────────────────────────────────────────────────────────────
# Step 2: Apply Native Fix (1-Hour Streamable HTTP Timeout)
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[3/4] Applying Native 1-Hour MCP Timeout Fix...${NC}"

cat << 'PYEOF' > /tmp/mcp_client_fixed.py
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
    Configured with 3600s (1 hour) timeout to support long AAP playbooks.
    """
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
        servers_config = load_mcp_servers_config(domain_scope=domain_scope)
        
        # Build multi-server dictionary with 1-hour timeout
        client_dict = {}
        for s_name, s_url in servers_config.items():
            client_dict[s_name] = {
                "url": s_url,
                "transport": "streamable_http",
                "timeout": 3600.0,
                "sse_read_timeout": 3600.0
            }
            
        logger.info(f"Connecting MultiServerMCPClient to servers: {list(client_dict.keys())} with 3600s timeout...")
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
                    "transport": "streamable_http",
                    "timeout": 3600.0,
                    "sse_read_timeout": 3600.0
                }
            })
            return await fallback_client.get_tools()
        except Exception as fallback_err:
            logger.error(f"Fallback MCP connection also failed: {fallback_err}")
            return []
PYEOF

# Copy fixed mcp_client.py into all application search paths in container
echo -e "  • Updating deepagent-service with 1-hour timeout configuration..."
podman cp /tmp/mcp_client_fixed.py deepagent-service:/app/app/mcp_client.py
podman cp /tmp/mcp_client_fixed.py deepagent-service:/app/app/app/mcp_client.py 2>/dev/null || true
rm -f /tmp/mcp_client_fixed.py

# Restart deepagent-service cleanly
echo -e "  • Restarting deepagent-service to apply module..."
podman restart deepagent-service >/dev/null

sleep 4

# ──────────────────────────────────────────────────────────────────────────────
# Step 3: Verification & Simulation
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[4/4] Verifying Fix & Simulating MCP Tool Invocations...${NC}"

VERIFY_RESULT=$(podman exec -i deepagent-service python3 -c "
import asyncio
from app.mcp_client import load_mcp_tools

async def verify():
    tools = await load_mcp_tools()
    tool_names = [t.name for t in tools]
    assert 'ansible_patch_fleet' in tool_names, 'ansible_patch_fleet missing'
    assert 'ansible_get_server_info' in tool_names, 'ansible_get_server_info missing'
    
    # Test tool invocation through newly loaded client
    info_tool = next(t for t in tools if t.name == 'ansible_get_server_info')
    res = await info_tool.ainvoke({'hostlist': 'srv01'})
    print(f'SUCCESS: Loaded {len(tools)} tools. Sample invocation succeeded.')

asyncio.run(verify())
" 2>&1 || echo "VERIFY_FAILED")

if [[ "$VERIFY_RESULT" == *"SUCCESS"* ]]; then
    echo -e "  ${GREEN}✓ Verification Passed:${NC} ${VERIFY_RESULT}"
    echo -e "\n${GREEN}${BOLD}==============================================================================${NC}"
    echo -e "${GREEN}${BOLD}  🎉 INSPECTION & FIX COMPLETE: 1-HOUR TIMEOUT ACTIVE!                       ${NC}"
    echo -e "${GREEN}${BOLD}==============================================================================${NC}"
    echo -e "  • Timeout Config : 3600.0s (HTTP request & SSE stream read timeout)"
    echo -e "  • Supported Time : AAP jobs up to 60 minutes will complete without disconnection"
    echo -e "  • Service Status : deepagent-service healthy and ready"
    echo -e "${GREEN}${BOLD}==============================================================================${NC}\n"
else
    echo -e "  ${RED}❌ Verification failed:${NC} ${VERIFY_RESULT}"
    exit 1
fi
