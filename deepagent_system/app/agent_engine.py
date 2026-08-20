import logging
from typing import Dict, Any, List
from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI
from app.config import settings
from app.mcp_client import load_mcp_tools
from app.prompts import load_system_prompt
from app.domain.orchestrators.workflow_dispatcher import WorkflowDispatcher

logger = logging.getLogger("AgentEngine")

_GLOBAL_TOOLS = None

async def init_deep_agent():
    """Initializes the Deep Agent harness with LangGraph create_deep_agent."""
    global _GLOBAL_TOOLS
    ollama_v1_url = f"{settings.ollama_host}/v1" if not str(settings.ollama_host).endswith("/v1") else str(settings.ollama_host)
    logger.info(f"Initializing ChatOpenAI model '{settings.ollama_model}' at '{ollama_v1_url}'...")
    
    llm = ChatOpenAI(
        base_url=ollama_v1_url,
        api_key="ollama",
        model=settings.ollama_model,
        temperature=settings.ollama_temperature
    )
    
    tools = await load_mcp_tools()
    _GLOBAL_TOOLS = tools
    system_prompt = load_system_prompt()
    
    logger.info("Building Deep Agent harness with native create_deep_agent & subagents...")
    agent = create_deep_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
        subagents=[
            {
                "name": "rhel-diagnostics",
                "description": "Specialized subagent for cluster health pre-checks and node inspections",
                "system_prompt": "You are the RHEL Cluster Diagnostics Subagent."
            },
            {
                "name": "ha-cluster-patcher",
                "description": "Specialized subagent for Red Hat HA Pacemaker/Corosync cluster rolling updates per SOP 2059253.",
                "system_prompt": "You are the Red Hat HA Cluster Rolling Maintenance Subagent following SOP 2059253."
            },
            {
                "name": "fleet-patcher",
                "description": "Specialized subagent for enterprise fleet package updates, reboots, and IPMI console recoveries.",
                "system_prompt": "You are the Enterprise Fleet Patching Subagent."
            }
        ]
    )
    logger.info("Deep Agent harness initialized successfully.")
    return agent

async def execute_subagent_workflow_orchestrator(user_query: str) -> Dict[str, Any]:
    """
    Entrypoint for orchestrating user queries through the decoupled domain workflow layer.
    """
    global _GLOBAL_TOOLS
    if not _GLOBAL_TOOLS:
        _GLOBAL_TOOLS = await load_mcp_tools()
        
    tools_dict = {t.name: t for t in _GLOBAL_TOOLS}
    return await WorkflowDispatcher.dispatch(user_query=user_query, tools_dict=tools_dict)
