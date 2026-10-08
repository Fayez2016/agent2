import logging
from typing import Dict, Any, List, Optional
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

_COMPILED_AGENTS: Dict[str, Any] = {}

def get_llm_instance(provider: Optional[str] = None, model_name: Optional[str] = None, temperature: float = 0.1):
    """
    Initializes an OpenAI-compliant LLM instance dynamically from PostgreSQL system_settings
    or agent-specific model parameters.
    """
    from app.infrastructure.db.hitl_repository import HitlRepository
    
    # 1. Resolve Provider
    eff_provider = provider or HitlRepository.get_setting("llm_default_provider", settings.llm_provider).lower()
    
    if eff_provider == "openrouter":
        api_key = HitlRepository.get_setting("openrouter_api_key", settings.openrouter_api_key)
        base_url = HitlRepository.get_setting("openrouter_base_url", settings.openrouter_base_url)
        eff_model = model_name or HitlRepository.get_setting("openrouter_model", settings.openrouter_model)
        return ChatOpenAI(
            base_url=base_url,
            api_key=api_key,
            model=eff_model,
            temperature=temperature,
            max_retries=5,
            timeout=60,
        )
    elif eff_provider == "groq":
        api_key = HitlRepository.get_setting("groq_api_key", settings.groq_api_key)
        base_url = HitlRepository.get_setting("groq_base_url", settings.groq_base_url)
        eff_model = model_name or HitlRepository.get_setting("groq_model", settings.groq_model)
        return ChatOpenAI(
            base_url=base_url,
            api_key=api_key,
            model=eff_model,
            temperature=temperature,
            max_retries=5,
            timeout=60,
        )
    elif eff_provider in ("custom_openai", "openai"):
        import httpx
        api_key = HitlRepository.get_setting("custom_openai_api_key", "sk-custom-secret")
        base_url = HitlRepository.get_setting("custom_openai_base_url", "https://api.openai.com/v1")
        eff_model = model_name or HitlRepository.get_setting("custom_openai_model", "gpt-4o")
        ssl_verify_setting = HitlRepository.get_setting("ssl_verify", "true").lower() in ("true", "1", "yes")
        ca_cert_path = HitlRepository.get_setting("ca_cert_path", "")
        verify_arg = ca_cert_path if (ca_cert_path and ssl_verify_setting) else ssl_verify_setting
        return ChatOpenAI(
            base_url=base_url,
            api_key=api_key,
            model=eff_model,
            temperature=temperature,
            max_retries=3,
            timeout=60,
            http_client=httpx.Client(verify=verify_arg),
            http_async_client=httpx.AsyncClient(verify=verify_arg),
        )
    else:  # ollama / local
        host = HitlRepository.get_setting("ollama_host", settings.ollama_host)
        ollama_v1_url = f"{host}/v1" if not str(host).endswith("/v1") else str(host)
        eff_model = model_name or HitlRepository.get_setting("ollama_model", settings.ollama_model)
        return ChatOpenAI(
            base_url=ollama_v1_url,
            api_key="ollama",
            model=eff_model,
            temperature=settings.ollama_temperature,
        )

async def get_agent(domain_key: str = "linux_sre", reload: bool = False):
    """
    Dynamically loads or compiles ANY Domain Agent from PostgreSQL on demand.
    Zero-code multi-domain agent instantiation with per-agent model settings.
    """
    global _COMPILED_AGENTS
    if not reload and domain_key in _COMPILED_AGENTS:
        return _COMPILED_AGENTS[domain_key]

    from app.infrastructure.db.hitl_repository import HitlRepository
    from app.infrastructure.db.agent_repository import AgentRepository

    # 1. Fetch Agent Record from DB
    db_agent = AgentRepository.get_agent_by_key(domain_key)
    domain_scope = db_agent.get("domain_category", "linux") if db_agent else "linux"
    model_provider = db_agent.get("model_provider") if db_agent else None
    model_name = db_agent.get("model_name") if db_agent else None

    llm = get_llm_instance(provider=model_provider, model_name=model_name)
    notification_email = HitlRepository.get_setting("notification_email", "fayez.soufyani@gmail.com")

    # 1. Fetch Agent Record from DB
    db_agent = AgentRepository.get_agent_by_key(domain_key)
    domain_scope = db_agent.get("domain_category", "linux") if db_agent else "linux"

    # 2. Discover FastMCP Tools bound to this domain scope
    tools = await load_mcp_tools(domain_scope=domain_scope)
    tools_map = {t.name: t for t in tools}

    # 3. System Prompt
    system_prompt = db_agent["system_prompt"] if db_agent else load_system_prompt()
    if "{recipient_email}" in system_prompt:
        system_prompt = system_prompt.replace("{recipient_email}", notification_email)

    # 4. Build Subagents Dynamically
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
        logger.info(f"Loaded {len(subagent_configs)} subagents dynamically from PostgreSQL for domain agent '{domain_key}'.")

    # Fallback to default Linux SRE subagents if first launch on fresh DB
    if not subagent_configs and domain_key == "linux_sre":
        pcs_tools = [t for t in tools if t.name.startswith("ansible_pcs") or t.name in ("ansible_get_maintenance_hosts", "ansible_run_command", "sop_get_procedure", "ansible_send_email", "ansible_fix_pcs", "hitl_request_approval", "ansible_check_host_online")]
        fleet_tools = [t for t in tools if t.name in ("ansible_get_maintenance_hosts", "ansible_patch_fleet", "ansible_reboot_fleet", "ansible_reboot_host", "ansible_check_host_online", "ansible_get_server_info", "ansible_send_email", "ansible_run_command", "hitl_request_approval")]
        diag_tools = [t for t in tools if t.name in ("ansible_get_server_info", "ansible_check_host_online", "ansible_run_command", "ansible_expand_fs", "ansible_console_power_on", "ansible_vmware_reset", "ansible_install_package", "ansible_send_email", "hitl_request_approval")]
        batcher_tools = [t for t in tools if t.name in ("ansible_get_maintenance_hosts", "ansible_get_server_info", "ansible_check_host_online", "ansible_pcs_status", "ansible_expand_fs", "ansible_run_command", "ansible_send_email", "hitl_request_approval")]

        subagent_configs = [
            {
                "name": "pcs_cluster_specialist",
                "description": "Specialized subagent for Red Hat HA Pacemaker/Corosync cluster maintenance, quorum preservation, node standby/unstandby, and SOP 2059253 HA rolling updates.",
                "system_prompt": load_ha_patcher_prompt(recipient_email=notification_email),
                "tools": pcs_tools,
                "skills": ["/app/skills/"]
            },
            {
                "name": "fleet_patcher",
                "description": "Specialized subagent for enterprise fleet package updates, DNF security patching, managed reboots, and post-reboot verification.",
                "system_prompt": load_fleet_patcher_prompt(recipient_email=notification_email),
                "tools": fleet_tools,
                "skills": ["/app/skills/"]
            },
            {
                "name": "rhel_diagnostician",
                "description": "Specialized subagent for host telemetry, log inspection (journalctl), storage expansion (/var), out-of-band IPMI recovery, and ad-hoc troubleshooting commands.",
                "system_prompt": load_diagnostics_prompt(),
                "tools": diag_tools,
                "skills": ["/app/skills/"]
            },
            {
                "name": "event_batcher",
                "description": "Autonomous event batching, alarm deduplication, and initial triage subagent. Ingests monitoring alarms, verifies reachability, expands storage, and dispatches remediations.",
                "system_prompt": "You are the Autonomous Event Batcher & Alarm Triage Daemon. You analyze incoming monitoring events, deduplicate alarm storms over 5-minute rolling windows, execute automated non-disruptive triage (ansible_get_server_info, ansible_expand_fs, ansible_check_host_online), and delegate complex remediations to specialized subagents. Always summarize results via ansible_send_email.",
                "tools": batcher_tools,
                "skills": ["/app/skills/"]
            }
        ]

    # Root Orchestrator Tools:
    # Main agent can execute ad-hoc requests, run commands, reboots, inspection, and SOP queries.
    # The patching process (ansible_patch_fleet) MUST be delegated to fleet_patcher subagent.
    root_tools = [t for t in tools if t.name in (
        "ansible_get_maintenance_hosts",
        "ansible_get_server_info",
        "ansible_check_host_online",
        "sop_get_procedure",
        "ansible_run_command",
        "ansible_reboot_host",
        "ansible_reboot_fleet",
        "hitl_request_approval"
    )]

    logger.info(f"Compiling Deep Agent harness for domain '{domain_key}'...")
    agent = create_deep_agent(
        model=llm,
        tools=root_tools,
        system_prompt=system_prompt,
        skills=["/app/skills/"],
        subagents=subagent_configs
    )

    _COMPILED_AGENTS[domain_key] = agent
    return agent

async def init_deep_agent():
    """Initializes primary Linux SRE agent harness."""
    return await get_agent("linux_sre")

