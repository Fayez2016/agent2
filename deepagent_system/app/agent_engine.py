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
                "name": "ha-cluster-patcher",
                "description": "Specialized subagent for executing Red Hat Enterprise Linux High Availability (HA) Pacemaker/Corosync cluster rolling updates per Red Hat SOP (Article 2059253) across single and multi-cluster fleets.",
                "system_prompt": "You are the Red Hat HA Cluster Rolling Maintenance Subagent following SOP 2059253. For each cluster node: 1. Combine Pre-check & Evacuation (check health and standby node). 2. Patch node. 3. Reboot node. 4. Verify host online (if unresponsive, trigger out-of-band console power-on / VM reset). 5. Reintegrate node (unstandby). 6. Repeat across all nodes in the batch. 7. Generate a comprehensive per-cluster reboot matrix report and dispatch it via ansible_send_email to admin@enterprise.local."
            },
            {
                "name": "fleet-patcher",
                "description": "Specialized subagent for applying DNF updates, executing managed reboots, verifying host uptime, and recovering unreachable hosts via console power-on across enterprise server fleets.",
                "system_prompt": "You are the Enterprise Fleet Patching Subagent. 1. Apply package updates across the hostlist. 2. Execute managed reboots. 3. Verify hosts reach online state (if unresponsive, trigger console power-on or VM reset). 4. Dispatch the final execution summary to admin@enterprise.local via ansible_send_email."
            }
        ]
    )
    logger.info("Deep Agent harness initialized successfully.")
    return agent
