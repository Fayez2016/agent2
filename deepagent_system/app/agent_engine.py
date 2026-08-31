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
    if settings.llm_provider == "openrouter":
        logger.info(f"Initializing ChatOpenAI with OpenRouter model '{settings.openrouter_model}' at '{settings.openrouter_base_url}'...")
        llm = ChatOpenAI(
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
            model=settings.openrouter_model,
            temperature=0.1,
            max_retries=5,
            timeout=60,
        )
    elif settings.llm_provider == "groq":
        logger.info(f"Initializing ChatOpenAI with Groq model '{settings.groq_model}' at '{settings.groq_base_url}'...")
        llm = ChatOpenAI(
            base_url=settings.groq_base_url,
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            temperature=0.1,
            max_retries=5,
            timeout=60,
        )
    else:
        # Fallback / Air-gapped offline mode
        ollama_v1_url = f"{settings.ollama_host}/v1" if not str(settings.ollama_host).endswith("/v1") else str(settings.ollama_host)
        logger.info(f"Initializing ChatOpenAI model '{settings.ollama_model}' at '{ollama_v1_url}'...")
        llm = ChatOpenAI(
            base_url=ollama_v1_url,
            api_key="ollama",
            model=settings.ollama_model,
            temperature=settings.ollama_temperature,
        )
    
    # Load domain FastMCP tools from dynamically registered database endpoints
    tools = await load_mcp_tools(domain_scope="linux")
    tools_map = {t.name: t for t in tools}

    # Dynamically fetch configured recipient email from DB
    from app.infrastructure.db.hitl_repository import HitlRepository
    from app.infrastructure.db.agent_repository import AgentRepository
    notification_email = HitlRepository.get_setting("notification_email", "fayez.soufyani@gmail.com")

    # 1. Load Main Agent Definition from PostgreSQL
    db_agent = AgentRepository.get_agent_by_key("linux_sre")
    system_prompt = db_agent["system_prompt"] if db_agent else load_system_prompt()

    # 2. Build Subagents Dynamically from Database
    subagent_configs = []
    if db_agent and db_agent.get("subagents"):
        for sub in db_agent["subagents"]:
            sub_tools = []
            bindings = sub.get("tool_bindings", [])
            for b in bindings:
                if b in tools_map:
                    sub_tools.append(tools_map[b])
                elif b.endswith("*"):
                    prefix = b[:-1]
                    sub_tools.extend([t for t in tools if t.name.startswith(prefix)])
            
            # Ensure email recipient dynamic injection if placeholder or standard
            sub_prompt = sub["system_prompt"]
            if "{recipient_email}" in sub_prompt:
                sub_prompt = sub_prompt.replace("{recipient_email}", notification_email)

            subagent_configs.append({
                "name": sub["name"],
                "description": sub["description"],
                "system_prompt": sub_prompt,
                "tools": sub_tools,
                "skills": [sub.get("skills_path", "/app/skills/")]
            })
        logger.info(f"Loaded {len(subagent_configs)} subagents dynamically from PostgreSQL for agent 'linux_sre'.")

    # Fallback to defaults if DB records unavailable
    if not subagent_configs:
        root_tools = [t for t in tools if t.name in ("ansible_get_server_info", "ansible_send_email", "sop_get_procedure")]
        ha_tools = [t for t in tools if t.name.startswith("ansible_pcs") or t.name in ("ansible_patch_fleet", "ansible_reboot_fleet", "ansible_reboot_host", "ansible_send_email", "hitl_request_approval")]
        fleet_tools = [t for t in tools if t.name in ("ansible_patch_fleet", "ansible_reboot_fleet", "ansible_reboot_host", "ansible_get_server_info", "ansible_send_email", "hitl_request_approval")]
        diag_tools = [t for t in tools if t.name.startswith("ansible_pcs") or t.name in ("ansible_get_server_info", "hitl_request_approval")]
        single_tools = [t for t in tools if t.name in ("ansible_install_package", "ansible_expand_fs", "ansible_reboot_host", "ansible_get_server_info", "hitl_request_approval")]

        subagent_configs = [
            {
                "name": "ha_cluster_patcher",
                "description": "Specialized subagent for Red Hat HA Pacemaker/Corosync cluster rolling updates per SOP 2059253.",
                "system_prompt": load_ha_patcher_prompt(recipient_email=notification_email),
                "tools": ha_tools,
                "skills": ["/app/skills/"]
            },
            {
                "name": "fleet_patcher",
                "description": "Specialized subagent for enterprise fleet package updates, reboots, and IPMI console recoveries.",
                "system_prompt": load_fleet_patcher_prompt(recipient_email=notification_email),
                "tools": fleet_tools,
                "skills": ["/app/skills/"]
            },
            {
                "name": "rhel_diagnostician",
                "description": "Specialized subagent for cluster health pre-checks, node inspections, and triage.",
                "system_prompt": load_diagnostics_prompt(),
                "tools": diag_tools,
                "skills": ["/app/skills/"]
            },
            {
                "name": "single_host_operator",
                "description": "Specialized subagent for ad-hoc single-server package installations, reboots, and volume expansions.",
                "system_prompt": load_single_host_prompt(),
                "tools": single_tools,
                "skills": ["/app/skills/"]
            }
        ]

    root_tools = [t for t in tools if t.name in ("ansible_get_server_info", "ansible_send_email", "sop_get_procedure")]

    logger.info(f"Building Deep Agent harness from DB records (Recipient: {notification_email})...")
    agent = create_deep_agent(
        model=llm,
        tools=root_tools,
        system_prompt=system_prompt,
        skills=["/app/skills/"],
        subagents=subagent_configs
    )
    logger.info("Deep Agent harness initialized successfully from PostgreSQL.")
    _GLOBAL_AGENT = agent
    return agent

async def get_agent():
    """Retrieves or initializes the singleton Deep Agent instance."""
    global _GLOBAL_AGENT
    if not _GLOBAL_AGENT:
        _GLOBAL_AGENT = await init_deep_agent()
    return _GLOBAL_AGENT
