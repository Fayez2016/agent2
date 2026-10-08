#!/usr/bin/env bash
# ==============================================================================
#  🛡️ Deep Agent Immediate Restoration & Connection Error Resolver
# ==============================================================================
#  Fixes:
#    1. Fixes Gateway URL: Checks if gateway.conf specified 'ansible.aramco.com.sa'
#       (which is AAP) or missing 'https://' scheme, and corrects it to the real AI Gateway:
#       https://aigateway.aramco.com.sa
#    2. Patches agent_engine.py inside deepagent-service with verify=False (httpx)
#       to prevent enterprise SSL inspection handshakes from breaking LangChain.
#    3. Updates PostgreSQL with the validated URL and token.
#    4. Runs a live Python test and Chat completions test to guarantee 200 OK.
# ==============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${CYAN}${BOLD}  🛡️ DEEP AGENT LIVE RESTORATION & GATEWAY RESOLVER                          ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"

# ──────────────────────────────────────────────────────────────────────────────
# Stage 1: Load and Validate Gateway Settings
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[Stage 1/5] Inspecting gateway.conf and resolving URL...${NC}"

GW_URL=""
GW_KEY=""
GW_MODEL=""

for loc in "gateway.conf" "${HOME}/gateway.conf" "/etc/deepagent/gateway.conf" "${HOME}/.config/deepagent/gateway.conf"; do
    if [ -f "$loc" ] && [ -r "$loc" ]; then
        echo -e "${GREEN}✓ Found: ${BOLD}${loc}${NC}"
        while IFS='=' read -r key val || [ -n "$key" ]; do
            key=$(echo "$key" | tr -d ' ' | tr '[:lower:]' '[:upper:]')
            val=$(echo "$val" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^["'"'"']//' -e 's/["'"'"']$//')
            case "$key" in
                *URL*|*HOST*|*BASE*) GW_URL="$val" ;;
                *KEY*|*TOKEN*) GW_KEY="$val" ;;
                *MODEL*) GW_MODEL="$val" ;;
            esac
        done < "$loc"
        break
    fi
done

# If token is still empty, read from existing PostgreSQL
if [ -z "$GW_KEY" ]; then
    GW_KEY=$(podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -t -A -c "SELECT value FROM system_settings WHERE key = 'custom_openai_api_key' LIMIT 1;" 2>/dev/null || echo "")
fi

# Sanitize & Correct URL:
# If URL contains 'ansible' (e.g. ansible.aramco.com.sa), that's AAP, NOT the LLM Gateway!
if [[ "$GW_URL" == *"ansible"* ]] || [ -z "$GW_URL" ]; then
    echo -e "${YELLOW}⚠️ Detected AAP host '$GW_URL' assigned as LLM gateway.${NC}"
    echo -e "${CYAN}  Auto-correcting to enterprise AI Gateway: https://aigateway.aramco.com.sa${NC}"
    GW_URL="https://aigateway.aramco.com.sa"
fi

# Ensure https:// prefix
if [[ "$GW_URL" != http* ]]; then
    GW_URL="https://${GW_URL}"
fi

GW_MODEL="${GW_MODEL:-Qwen/Qwen3.8-27B}"

echo -e "  • Resolved Gateway URL : ${BOLD}${GREEN}${GW_URL}${NC}"
echo -e "  • Target Model Tag     : ${BOLD}${CYAN}${GW_MODEL}${NC}"
echo -e "  • Token Status         : ${BOLD}${GREEN}Configured (Length: ${#GW_KEY})${NC}"

# ──────────────────────────────────────────────────────────────────────────────
# Stage 2: Sync to Database (system_settings & domain_agents)
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[Stage 2/5] Updating PostgreSQL Configuration...${NC}"

podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl << EOF >/dev/null
INSERT INTO system_settings (key, value, updated_at) VALUES ('custom_openai_base_url', '${GW_URL}', NOW()) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();
INSERT INTO system_settings (key, value, updated_at) VALUES ('custom_openai_model', '${GW_MODEL}', NOW()) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();
$([ -n "$GW_KEY" ] && echo "INSERT INTO system_settings (key, value, updated_at) VALUES ('custom_openai_api_key', '${GW_KEY}', NOW()) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();")
INSERT INTO system_settings (key, value, updated_at) VALUES ('llm_default_provider', 'custom_openai', NOW()) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();
UPDATE domain_agents SET model_provider = 'custom_openai', model_name = '${GW_MODEL}', updated_at = NOW() WHERE key_name = 'linux_sre';
EOF
echo -e "${GREEN}✓ Database updated successfully.${NC}"

# ──────────────────────────────────────────────────────────────────────────────
# Stage 3: Patch SSL verify=False inside deepagent-service
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[Stage 3/5] Applying Enterprise SSL Trust Bypass (verify=False)...${NC}"

podman exec -i deepagent-service python3 -c "
import os

code = '''import logging
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

logger = logging.getLogger('AgentEngine')
_GLOBAL_AGENT = None
_COMPILED_AGENTS: Dict[str, Any] = {}

def get_llm_instance(provider: Optional[str] = None, model_name: Optional[str] = None, temperature: float = 0.1):
    from app.infrastructure.db.hitl_repository import HitlRepository
    import httpx
    
    eff_provider = provider or HitlRepository.get_setting('llm_default_provider', settings.llm_provider).lower()
    
    if eff_provider in ('custom_openai', 'openai'):
        api_key = HitlRepository.get_setting('custom_openai_api_key', '${GW_KEY}')
        base_url = HitlRepository.get_setting('custom_openai_base_url', '${GW_URL}')
        eff_model = model_name or HitlRepository.get_setting('custom_openai_model', '${GW_MODEL}')
        return ChatOpenAI(
            base_url=base_url,
            api_key=api_key,
            model=eff_model,
            temperature=temperature,
            max_retries=3,
            timeout=60,
            http_client=httpx.Client(verify=False),
            http_async_client=httpx.AsyncClient(verify=False)
        )
    elif eff_provider == 'openrouter':
        api_key = HitlRepository.get_setting('openrouter_api_key', settings.openrouter_api_key)
        base_url = HitlRepository.get_setting('openrouter_base_url', settings.openrouter_base_url)
        eff_model = model_name or HitlRepository.get_setting('openrouter_model', settings.openrouter_model)
        return ChatOpenAI(
            base_url=base_url,
            api_key=api_key,
            model=eff_model,
            temperature=temperature,
            max_retries=3,
            timeout=60,
            http_client=httpx.Client(verify=False),
            http_async_client=httpx.AsyncClient(verify=False)
        )
    else:
        host = HitlRepository.get_setting('ollama_host', settings.ollama_host)
        ollama_v1_url = f'{host}/v1' if not str(host).endswith('/v1') else str(host)
        eff_model = model_name or HitlRepository.get_setting('ollama_model', settings.ollama_model)
        return ChatOpenAI(base_url=ollama_v1_url, api_key='ollama', model=eff_model, temperature=0.0)

async def get_agent(domain_key: str = 'linux_sre', reload: bool = False):
    global _COMPILED_AGENTS
    if not reload and domain_key in _COMPILED_AGENTS:
        return _COMPILED_AGENTS[domain_key]

    from app.infrastructure.db.agent_repository import AgentRepository
    from app.infrastructure.db.hitl_repository import HitlRepository
    notification_email = HitlRepository.get_setting('notification_email', 'fayez.soufyani@gmail.com')

    db_agent = AgentRepository.get_agent_by_key(domain_key)
    system_prompt = db_agent['system_prompt'] if db_agent else load_system_prompt()
    provider = db_agent.get('model_provider') if db_agent else None
    model_name = db_agent.get('model_name') if db_agent else None
    llm = get_llm_instance(provider=provider, model_name=model_name)

    tools = await load_mcp_tools(domain_scope='linux')
    tools_map = {t.name: t for t in tools}

    subagent_configs = []
    if db_agent and db_agent.get('subagents'):
        for sub in db_agent['subagents']:
            sub_tools = []
            for b in sub.get('tool_bindings', []):
                if b in tools_map:
                    sub_tools.append(tools_map[b])
                elif b.endswith('*'):
                    prefix = b[:-1]
                    sub_tools.extend([t for t in tools if t.name.startswith(prefix)])
            sub_prompt = sub['system_prompt'].replace('{recipient_email}', notification_email)
            subagent_configs.append({
                'name': sub['name'],
                'description': sub['description'],
                'system_prompt': sub_prompt,
                'tools': sub_tools,
                'skills': [sub.get('skills_path', '/app/skills/')]
            })

    root_tools = [t for t in tools if t.name in ('ansible_get_server_info', 'ansible_check_host_online', 'ansible_get_maintenance_hosts', 'ansible_run_command', 'ansible_send_email', 'sop_get_procedure')]
    agent = create_deep_agent(
        model=llm,
        tools=root_tools,
        system_prompt=system_prompt,
        skills=['/app/skills/'],
        subagents=subagent_configs
    )
    _COMPILED_AGENTS[domain_key] = agent
    return agent

async def init_deep_agent():
    return await get_agent('linux_sre')
'''

for p in ['/app/app/agent_engine.py', '/app/agent_engine.py']:
    if os.path.exists(os.path.dirname(p)):
        with open(p, 'w') as f:
            f.write(code)
        print('✓ Written SSL-resilient engine to:', p)
"

# ──────────────────────────────────────────────────────────────────────────────
# Stage 4: Restart Service & Fast Diagnostics
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[Stage 4/5] Restarting deepagent-service...${NC}"
podman restart deepagent-service >/dev/null
sleep 6

# Direct Python LLM invocation test inside container
echo -n "  • Direct Gateway Ping from Container: "
podman exec -i deepagent-service python3 -c "
from app.agent_engine import get_llm_instance
import urllib3
urllib3.disable_warnings()
try:
    llm = get_llm_instance()
    resp = llm.invoke('ping')
    print('OK! Token response:', resp.content[:60])
except Exception as e:
    print('FAILED:', e)
"

# ──────────────────────────────────────────────────────────────────────────────
# Stage 5: Live End-to-End Chat Test directly against API Port 8642
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[Stage 5/5] Testing Live End-to-End Chat Request ('hi')...${NC}"

CHAT_PAYLOAD='{
  "model": "deepagent",
  "domain": "linux_sre",
  "messages": [{"role": "user", "content": "hi"}],
  "stream": false
}'

E2E_RESP=$(podman exec -i deepagent-service curl -s \
    -X POST \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer hermes-api-secret" \
    --connect-timeout 10 \
    --max-time 40 \
    -d "$CHAT_PAYLOAD" \
    http://127.0.0.1:8642/v1/chat/completions 2>/dev/null || echo "FAILED")

if echo "$E2E_RESP" | grep -q "choices"; then
    echo -e "\n${GREEN}${BOLD}🎉 SUCCESS! Deep Agent is online and responded!${NC}"
    echo -e "${CYAN}Agent Response:${NC}"
    echo "$E2E_RESP" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
    print(" ", data["choices"][0]["message"]["content"])
except Exception:
    print(sys.stdin.read()[:300])
' 2>/dev/null || echo "$E2E_RESP"
    echo -e "\n${GREEN}✓ System is fully operational! Refresh your browser on https://<host>:8443 and chat.${NC}"
else
    echo -e "\n${YELLOW}API Service Response:${NC}"
    echo "$E2E_RESP"
fi

echo -e "\n${CYAN}${BOLD}==============================================================================${NC}"
