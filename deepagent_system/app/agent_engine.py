import logging
from typing import Dict, Any, List
from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI
from app.config import settings
from app.mcp_client import load_mcp_tools
from app.prompts import (
    load_system_prompt,
    load_ha_patcher_prompt,
    load_fleet_patcher_prompt,
    load_diagnostics_prompt,
    load_single_host_prompt
)

logger = logging.getLogger("AgentEngine")

_GLOBAL_AGENT = None

async def init_deep_agent():
    """Initializes the Deep Agent harness with LangGraph create_deep_agent, subagents, and declarative skills."""
    global _GLOBAL_AGENT
    ollama_v1_url = f"{settings.ollama_host}/v1" if not str(settings.ollama_host).endswith("/v1") else str(settings.ollama_host)
    logger.info(f"Initializing ChatOpenAI model '{settings.ollama_model}' at '{ollama_v1_url}'...")
    
    llm = ChatOpenAI(
        base_url=ollama_v1_url,
        api_key="ollama",
        model=settings.ollama_model,
        temperature=settings.ollama_temperature
    )
    
    # Load domain FastMCP tools from :8000 and :8001 (FastMCP does not supply filesystem tools)
    tools = await load_mcp_tools()
    system_prompt = load_system_prompt()
    
    logger.info("Building Deep Agent harness with native create_deep_agent, declarative skills, and subagents...")
    agent = create_deep_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
        skills=["/app/skills/"],
        subagents=[
            {
                "name": "ha_cluster_patcher",
                "description": "Specialized subagent for Red Hat HA Pacemaker/Corosync cluster rolling updates per SOP 2059253.",
                "system_prompt": load_ha_patcher_prompt(),
                "tools": tools,
                "skills": ["/app/skills/"]
            },
            {
                "name": "fleet_patcher",
                "description": "Specialized subagent for enterprise fleet package updates, reboots, and IPMI console recoveries.",
                "system_prompt": load_fleet_patcher_prompt(),
                "tools": tools,
                "skills": ["/app/skills/"]
            },
            {
                "name": "rhel_diagnostician",
                "description": "Specialized subagent for cluster health pre-checks, node inspections, and triage.",
                "system_prompt": load_diagnostics_prompt(),
                "tools": tools,
                "skills": ["/app/skills/"]
            },
            {
                "name": "single_host_operator",
                "description": "Specialized subagent for ad-hoc single-server package installations, reboots, and volume expansions.",
                "system_prompt": load_single_host_prompt(),
                "tools": tools,
                "skills": ["/app/skills/"]
            }
        ]
    )
    logger.info("Deep Agent harness initialized successfully.")
    _GLOBAL_AGENT = agent
    return agent

async def get_agent():
    """Retrieves or initializes the singleton Deep Agent instance."""
    global _GLOBAL_AGENT
    if not _GLOBAL_AGENT:
        _GLOBAL_AGENT = await init_deep_agent()
    return _GLOBAL_AGENT
