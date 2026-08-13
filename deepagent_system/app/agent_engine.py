import logging
import os
from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI
from app.config import OLLAMA_HOST, OLLAMA_MODEL, MCP_SERVER_URL
from app.mcp_client import load_mcp_tools
from app.prompts import load_system_prompt

logger = logging.getLogger("AgentEngine")

async def init_deep_agent():
    """Initializes the Deep Agent harness following official deepagents documentation and examples."""
    ollama_v1_url = f"{OLLAMA_HOST}/v1" if not OLLAMA_HOST.endswith("/v1") else OLLAMA_HOST
    logger.info(f"Initializing ChatOpenAI model '{OLLAMA_MODEL}' at '{ollama_v1_url}'...")
    
    llm = ChatOpenAI(
        base_url=ollama_v1_url,
        api_key="ollama",
        model=OLLAMA_MODEL,
        temperature=0.0
    )
    
    tools = await load_mcp_tools(MCP_SERVER_URL)
    system_prompt = load_system_prompt()
    
    logger.info("Building Deep Agent harness with native create_deep_agent...")
    agent = create_deep_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
        subagents=[
            {
                "name": "rhel-diagnostics",
                "description": "Specialized subagent for executing pre-patch cluster checks and node health inspections",
                "system_prompt": "You are a RHEL Cluster Diagnostic Subagent. Run checks and return a concise summary."
            },
            {
                "name": "fleet-patcher",
                "description": "Specialized subagent for applying DNF updates and cluster node patching",
                "system_prompt": "You are a RHEL Fleet Patching Subagent. Apply patch updates via Ansible and verify service restoration."
            }
        ]
    )
    logger.info("Deep Agent harness initialized successfully.")
    return agent
