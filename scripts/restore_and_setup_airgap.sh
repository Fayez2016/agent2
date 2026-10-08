#!/usr/bin/env bash
# ==============================================================================
# Script: restore_and_setup_airgap.sh
# Purpose: All-in-one setup & restore for DeepAgent Air-Gapped Environment:
#          - Uses working base directory: /opt/td-agent (falls back to PWD if not writable)
#          - Avoids /tmp completely (uses ./staging_restore directory)
#          - Restores clean agent_engine.py into deepagent-service
#          - Performs pre-restart Python syntax & import validation
#          - Restarts deepagent-service cleanly
#          - Creates check_integrity.sh and pod_snapshot_and_test.sh
#          - Executes a full post-restore validation test
# ==============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${BLUE}====================================================================${NC}"
echo -e "${BLUE}    DeepAgent Air-Gap Restore, Tools Setup & Health Verification    ${NC}"
echo -e "${BLUE}====================================================================${NC}"

# Detect base working directory
if [ -d "/opt/td-agent" ] && [ -w "/opt/td-agent" ]; then
    BASE_DIR="/opt/td-agent"
elif [ -d "/home/fayez/agent2" ]; then
    BASE_DIR="/home/fayez/agent2"
else
    BASE_DIR="$(pwd)"
fi

echo -e "${CYAN}Working Directory Base: ${BASE_DIR}${NC}"

STAGING_DIR="${BASE_DIR}/staging_restore"
SCRIPTS_DIR="${BASE_DIR}/scripts"

mkdir -p "${STAGING_DIR}" "${SCRIPTS_DIR}"

# ------------------------------------------------------------------------------
# STEP 1: Restore clean agent_engine.py into deepagent-service
# ------------------------------------------------------------------------------
echo -e "\n${YELLOW}>>> [1/4] Restoring clean agent_engine.py into deepagent-service...${NC}"

TARGET_FILE="${STAGING_DIR}/agent_engine.py"

cat << 'AGENT_ENGINE_EOF' > "${TARGET_FILE}"
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
        return ChatOpenAI(
            base_url=base_url,
            api_key=api_key,
            model=eff_model,
            temperature=temperature,
            max_retries=5,
            timeout=60,
            http_client=httpx.Client(verify=False)
        )
    else:
        logger.warning(f"Unknown LLM provider '{eff_provider}', falling back to default config.")
        return ChatOpenAI(
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
            model=settings.openrouter_model,
            temperature=temperature,
            max_retries=5,
            timeout=60,
        )

async def build_specialized_subagent(
    name: str,
    description: str,
    system_prompt: str,
    allowed_tools: List[str],
    all_tools: List[Any],
    llm: Any
) -> Dict[str, Any]:
    """Compiles an isolated LangGraph Deep Agent and formats it for task delegation."""
    subagent_tools = [t for t in all_tools if t.name in allowed_tools]
    
    agent = create_deep_agent(
        name=name,
        system_prompt=system_prompt,
        model=llm,
        tools=subagent_tools
    )
    return {
        "name": name,
        "description": description,
        "agent": agent
    }

async def get_agent(domain: str = "linux_sre", force_refresh: bool = False):
    """
    Dynamically constructs or fetches the primary Deep Agent for the specified domain
    using declarative agent, subagent, and skill schemas stored in PostgreSQL.
    """
    global _COMPILED_AGENTS
    if not force_refresh and domain in _COMPILED_AGENTS:
        return _COMPILED_AGENTS[domain]

    from app.infrastructure.db.hitl_repository import HitlRepository
    
    agent_record = HitlRepository.get_agent_by_id(domain)
    if not agent_record or not agent_record.get("is_active", True):
        logger.warning(f"No active agent definition found in DB for domain '{domain}', creating fallback.")
        agent_record = {
            "agent_id": domain,
            "display_name": "Linux SRE Lead",
            "model_provider": settings.llm_provider,
            "model_name": settings.openrouter_model,
            "temperature": 0.1,
            "system_prompt": load_system_prompt(),
            "tools": [
                "ansible_get_server_info",
                "ansible_check_host_online",
                "ansible_run_command",
                "ansible_reboot_host",
                "ansible_reboot_fleet",
                "hitl_request_approval"
            ]
        }

    llm = get_llm_instance(
        provider=agent_record.get("model_provider"),
        model_name=agent_record.get("model_name"),
        temperature=float(agent_record.get("temperature", 0.1))
    )

    all_tools = await load_mcp_tools()
    
    # 1. Main Agent Tools
    assigned_tool_names = set(agent_record.get("tools") or [])
    primary_tools = [t for t in all_tools if t.name in assigned_tool_names]
    
    # Strictly exclude ansible_patch_fleet from Main Agent (must delegate to fleet_patcher)
    primary_tools = [t for t in primary_tools if t.name != "ansible_patch_fleet"]
    
    # Ensure ad-hoc capabilities are present
    root_tool_names = {t.name for t in primary_tools}
    for req in ("ansible_run_command", "ansible_reboot_host", "ansible_reboot_fleet", "hitl_request_approval"):
        if req not in root_tool_names:
            matching = [t for t in all_tools if t.name == req]
            if matching:
                primary_tools.append(matching[0])

    # 2. Build Subagents
    subagents_specs = []
    db_subagents = HitlRepository.get_subagents_for_agent(domain)
    
    if db_subagents:
        for sub in db_subagents:
            if not sub.get("is_active", True):
                continue
            sub_spec = await build_specialized_subagent(
                name=sub["subagent_name"],
                description=sub["description"],
                system_prompt=sub["system_prompt"],
                allowed_tools=sub.get("tools", []),
                all_tools=all_tools,
                llm=llm
            )
            subagents_specs.append(sub_spec)
    else:
        # Fallback subagents
        fleet_patcher_spec = await build_specialized_subagent(
            name="fleet_patcher",
            description="Autonomous RHEL Fleet Patching subagent. Executes rolling non-HA host updates.",
            system_prompt=load_fleet_patcher_prompt(),
            allowed_tools=["ansible_get_server_info", "ansible_check_host_online", "ansible_patch_fleet", "hitl_request_approval"],
            all_tools=all_tools,
            llm=llm
        )
        subagents_specs.append(fleet_patcher_spec)

    # 3. Create Root Agent
    agent = create_deep_agent(
        name=agent_record.get("display_name", "Linux SRE Specialist"),
        system_prompt=agent_record.get("system_prompt") or load_system_prompt(),
        model=llm,
        tools=primary_tools,
        subagents=subagents_specs
    )

    _COMPILED_AGENTS[domain] = agent
    logger.info(f"✓ Successfully compiled Deep Agent for domain '{domain}' with {len(primary_tools)} root tools and {len(subagents_specs)} subagents.")
    return agent

async def init_deep_agent():
    """Initializes primary Linux SRE agent harness."""
    return await get_agent("linux_sre")
AGENT_ENGINE_EOF

restored_hash=$(sha256sum "${TARGET_FILE}" | awk '{print $1}')
echo "Restored agent_engine.py SHA256: ${restored_hash}"

# Copy into container
podman cp "${TARGET_FILE}" deepagent-service:/app/app/agent_engine.py
echo -e "${GREEN}✓ Successfully copied clean agent_engine.py into deepagent-service.${NC}"

# Pre-flight syntax and import check inside container
echo -n "Pre-flight syntax & module import check ... "
check_output=$(podman exec -i deepagent-service python3 -c "import app.agent_engine; print('SYNTAX_VALID')" 2>&1)
if [[ "$check_output" =~ "SYNTAX_VALID" ]]; then
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${RED}FAILED${NC}"
    echo "$check_output"
    exit 1
fi

# Clean container restart
echo -e "\n${YELLOW}>>> [2/4] Restarting deepagent-service...${NC}"
podman restart deepagent-service >/dev/null
echo "Waiting 5 seconds for service initialization..."
sleep 5
echo -e "${GREEN}✓ deepagent-service is restarted and running.${NC}"

# ------------------------------------------------------------------------------
# STEP 2: Create check_integrity.sh script
# ------------------------------------------------------------------------------
echo -e "\n${YELLOW}>>> [3/4] Creating check_integrity.sh script in ${SCRIPTS_DIR}...${NC}"

cat << 'CHECK_INTEGRITY_EOF' > "${SCRIPTS_DIR}/check_integrity.sh"
#!/usr/bin/env bash
# ==============================================================================
# Script: check_integrity.sh
# Purpose: Comprehensive Diagnostic & Integrity Verification for DeepAgent
# ==============================================================================
set -o pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}====================================================================${NC}"
echo -e "${BLUE}        DeepAgent Air-Gap Diagnostic & Integrity Verification       ${NC}"
echo -e "${BLUE}====================================================================${NC}"

issues_found=0

echo -e "\n${YELLOW}>>> [1/7] Checking Podman Container Statuses...${NC}"
podman ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

REQUIRED_CONTAINERS=(
    "deepagent-hitl-db"
    "deepagent-aap-server"
    "deepagent-ansible-mcp"
    "deepagent-sop-mcp"
    "deepagent-service"
    "deepagent-webui"
    "deepagent-proxy"
)

for c in "${REQUIRED_CONTAINERS[@]}"; do
    c_status=$(podman inspect -f '{{.State.Status}}' "$c" 2>/dev/null || echo "not_found")
    if [ "$c_status" == "running" ]; then
        echo -e "${GREEN}[RUNNING]${NC} $c"
    elif [ "$c_status" == "not_found" ]; then
        echo -e "${RED}[MISSING]${NC} Container $c does not exist!"
        issues_found=$((issues_found + 1))
    else
        echo -e "${RED}[STOPPED/CRASHED]${NC} $c status is: $c_status"
        issues_found=$((issues_found + 1))
        podman logs --tail 20 "$c"
    fi
done

echo -e "\n${YELLOW}>>> [2/7] Checking Rootless Podman Storage Configuration...${NC}"
STORAGE_CONF="$HOME/.config/containers/storage.conf"
if [ -f "$STORAGE_CONF" ]; then
    if grep -q 'ignore_chown_errors.*=.*"true"' "$STORAGE_CONF"; then
        echo -e "${GREEN}[OK]${NC} storage.conf contains ignore_chown_errors = \"true\""
    else
        echo -e "${YELLOW}[WARNING]${NC} ignore_chown_errors is missing or false in $STORAGE_CONF"
    fi
else
    echo -e "${YELLOW}[INFO]${NC} No custom storage.conf found at $STORAGE_CONF"
fi

echo -e "\n${YELLOW}>>> [3/7] Verifying File Checksums (Code & Config Consistency)...${NC}"
check_file() {
    local container="$1"
    local file_path="$2"
    local expected_hash="$3"

    local c_status
    c_status=$(podman inspect -f '{{.State.Status}}' "$container" 2>/dev/null)
    if [ "$c_status" != "running" ]; then
        echo -e "${RED}[SKIPPED]${NC} $container is down; cannot verify $file_path"
        return 1
    fi

    local actual_hash
    actual_hash=$(podman exec -i "$container" sha256sum "$file_path" 2>/dev/null | awk '{print $1}')
    if [ -z "$actual_hash" ]; then
        echo -e "${RED}[NOT FOUND]${NC} $container:$file_path"
        issues_found=$((issues_found + 1))
    elif [ "$actual_hash" == "$expected_hash" ]; then
        echo -e "${GREEN}[OK]${NC}       $container:$file_path"
    else
        echo -e "${RED}[MISMATCH]${NC} $container:$file_path"
        echo -e "   Expected: ${GREEN}$expected_hash${NC}"
        echo -e "   Actual:   ${RED}$actual_hash${NC}"
        issues_found=$((issues_found + 1))
    fi
}

check_file "deepagent-service" "/app/app/agent_engine.py" "734a6e63eaa9ed88767f30e84d13bd8e3c12a43b4713e70c58eeafaf7c14af07"
check_file "deepagent-service" "/app/app/main.py" "aa62d3524f3460e83f7c7106c6f52e8232e7ca461488a67f35201abb3c40eccb"
check_file "deepagent-service" "/app/app/supervisor.py" "c3f0b7bff30b156a955cff46496558ab50090a3437965ee280805ea68caa19fd"
check_file "deepagent-service" "/app/app/api/v1/auth.py" "186e074ca8b8485aac7ccb42aa601ab6130b2b2622ffee3edb33a88e71c10035"
check_file "deepagent-service" "/app/app/api/v1/chat.py" "ba017382b2e9ecaba55daaf19901d1bc06b50074d3ad6d822cf7bdc7f2366770"
check_file "deepagent-service" "/app/app/api/v1/settings.py" "ea0d7e196f19e9d4e96b2191aaf54fb4533e7f685cd6933c62ed83351229980e"
check_file "deepagent-service" "/app/app/api/v1/studio.py" "b5edaffe7e56d10fd727c7c44f6bda21bf1abdc0343e21060885a527aab0693b"
check_file "deepagent-proxy" "/etc/nginx/nginx.conf" "c08103fea3e6ce20bd69d098c4bfe917862b5b56a71e7a0cf58e35e67415130a"
check_file "deepagent-webui" "/app/index.html" "e6742bbcbadb9fdfcd25ac8833f0402903d0718958ea61b86e2545103d765575"
check_file "deepagent-webui" "/app/app.js" "8762b8c55a908802ee4a75bfb005505f89e7e0ab3e7880c2faf87022f1770f2d"
check_file "deepagent-webui" "/app/style.css" "77d5c85f24e8cf6da2c6b1b82519b19ce4502dc047529d82289559f08b4b5cdc"
check_file "deepagent-ansible-mcp" "/app/ansible_mcp_server.py" "1dbdd173282516c168a79ca088e149f71c0daffc570899e346ab41247c78f401"

echo -e "\n${YELLOW}>>> [4/7] Checking PostgreSQL Database & Agent Definitions...${NC}"
db_check=$(podman exec -i deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -c "\dt" 2>&1)
if [[ $? -eq 0 && "$db_check" =~ "domain_agents" || "$db_check" =~ "users" ]]; then
    echo -e "${GREEN}[OK]${NC} Database tables exist."
    agent_count=$(podman exec -i deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -t -c "SELECT count(*) FROM domain_agents;" 2>/dev/null | tr -d ' ')
    echo -e "${GREEN}[OK]${NC} Configured domain agents in DB: ${agent_count:-0}"
else
    echo -e "${RED}[ERROR]${NC} Database tables missing or DB not reachable!"
    issues_found=$((issues_found + 1))
fi

echo -e "\n${YELLOW}>>> [5/7] Probing FastMCP Ports (8000 Ansible, 8001 SOP)...${NC}"
mcp_probe_script="
import urllib.request, urllib.error
def test_probe(url):
    try:
        req = urllib.request.Request(url, headers={'Accept': 'application/json, text/event-stream'})
        with urllib.request.urlopen(req, timeout=4) as r: return r.status
    except urllib.error.HTTPError as e: return e.code
    except Exception as e: return f'fail: {e}'

print('ansible:', test_probe('http://127.0.0.1:8000/mcp'))
print('sop:    ', test_probe('http://127.0.0.1:8001/mcp'))
"
mcp_results=$(podman exec -i deepagent-service python3 -c "$mcp_probe_script" 2>&1)
ansible_res=$(echo "$mcp_results" | grep 'ansible:' | awk '{print $2}')
sop_res=$(echo "$mcp_results" | grep 'sop:' | awk '{print $2}')

if [ "$ansible_res" == "400" ] || [ "$ansible_res" == "200" ] || [ "$ansible_res" == "406" ]; then
    echo -e "${GREEN}[OK]${NC} Ansible MCP (Port 8000) is responding (HTTP $ansible_res)."
else
    echo -e "${RED}[ERROR]${NC} Ansible MCP (Port 8000) unreachable (Response: $ansible_res)"
    issues_found=$((issues_found + 1))
fi

if [ "$sop_res" == "400" ] || [ "$sop_res" == "200" ] || [ "$sop_res" == "406" ]; then
    echo -e "${GREEN}[OK]${NC} SOP MCP (Port 8001) is responding (HTTP $sop_res)."
else
    echo -e "${RED}[ERROR]${NC} SOP MCP (Port 8001) unreachable (Response: $sop_res)"
    issues_found=$((issues_found + 1))
fi

echo -e "\n${YELLOW}>>> [6/7] Checking Internal Port 8642 Backend Directly...${NC}"
svc_direct=$(podman exec -i deepagent-service python3 -c "
import urllib.request
try:
    with urllib.request.urlopen('http://127.0.0.1:8642/health', timeout=5) as r:
        print(r.status)
except Exception:
    print('fail')
" 2>/dev/null || echo "fail")

if [ "$svc_direct" == "200" ]; then
    echo -e "${GREEN}[OK]${NC} Internal backend (127.0.0.1:8642/health) is UP (HTTP 200 OK)."
else
    echo -e "${RED}[CRITICAL 502 CAUSE]${NC} Internal backend (127.0.0.1:8642) returned: $svc_direct"
    issues_found=$((issues_found + 1))
    podman logs --tail 25 deepagent-service
fi

echo -e "\n${YELLOW}>>> [7/7] Testing External HTTPS Endpoint (https://127.0.0.1:8443/health)...${NC}"
health_response=$(curl -k -s -w "\n%{http_code}" https://127.0.0.1:8443/health 2>&1)
http_code=$(echo "$health_response" | tail -n1)
body=$(echo "$health_response" | head -n -1)

if [ "$http_code" == "200" ]; then
    echo -e "${GREEN}[HEALTH CHECK PASSED] HTTP 200 OK${NC}"
    echo "Payload: $body"
else
    echo -e "${RED}[HEALTH CHECK FAILED] HTTP Status: $http_code${NC}"
    echo "Payload: $body"
    issues_found=$((issues_found + 1))
fi

echo -e "\n${BLUE}====================================================================${NC}"
if [ $issues_found -eq 0 ]; then
    echo -e "${GREEN}🎉 ALL CHECKS PASSED: The air-gap system is completely healthy.${NC}"
else
    echo -e "${RED}⚠️  $issues_found ISSUE(S) DETECTED!${NC}"
fi
echo -e "${BLUE}====================================================================${NC}"
CHECK_INTEGRITY_EOF

chmod +x "${SCRIPTS_DIR}/check_integrity.sh"
echo -e "${GREEN}✓ Created and made executable: ${SCRIPTS_DIR}/check_integrity.sh${NC}"

# ------------------------------------------------------------------------------
# STEP 3: Create pod_snapshot_and_test.sh script
# ------------------------------------------------------------------------------
echo -e "\n${YELLOW}>>> [4/4] Creating pod_snapshot_and_test.sh script in ${SCRIPTS_DIR}...${NC}"

cat << 'SNAPSHOT_TEST_EOF' > "${SCRIPTS_DIR}/pod_snapshot_and_test.sh"
#!/usr/bin/env bash
# ==============================================================================
# Script: pod_snapshot_and_test.sh
# Purpose: Instant container snapshotting, smoke testing, and rollback.
# Usage:
#   ./pod_snapshot_and_test.sh snapshot [label]   -> Take backup
#   ./pod_snapshot_and_test.sh test               -> Run 5-point smoke test
#   ./pod_snapshot_and_test.sh rollback [label]   -> Restore from backup
#   ./pod_snapshot_and_test.sh list               -> List backups
# ==============================================================================
set -o pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

CRITICAL_CONTAINERS=(
    "deepagent-service"
    "deepagent-proxy"
    "deepagent-webui"
    "deepagent-ansible-mcp"
    "deepagent-sop-mcp"
)

run_smoke_test() {
    echo -e "\n${BLUE}====================================================${NC}"
    echo -e "${YELLOW}>>> Running DeepAgent Smoke Test...${NC}"
    echo -e "${BLUE}====================================================${NC}"

    local errors=0

    echo -n " [1/5] Checking container states ... "
    for c in "${CRITICAL_CONTAINERS[@]}"; do
        status=$(podman inspect -f '{{.State.Status}}' "$c" 2>/dev/null || echo "down")
        if [ "$status" != "running" ]; then
            echo -e "${RED}FAILED${NC} ($c is $status)"
            return 1
        fi
    done
    echo -e "${GREEN}PASS (All 5 containers running)${NC}"

    echo -n " [2/5] Verifying deepagent-service Python imports ... "
    import_err=$(podman exec -i deepagent-service python3 -c "import app.agent_engine, app.main; print('OK')" 2>&1)
    if [[ "$import_err" =~ "OK" ]]; then
        echo -e "${GREEN}PASS${NC}"
    else
        echo -e "${RED}FAILED${NC} ($import_err)"
        errors=$((errors + 1))
    fi

    echo -n " [3/5] Checking FastMCP listeners (Ports 8000 & 8001) ... "
    mcp_test=$(podman exec -i deepagent-service python3 -c "
import urllib.request, urllib.error
for p in [8000, 8001]:
    try:
        req = urllib.request.Request(f'http://127.0.0.1:{p}/mcp', headers={'Accept': 'application/json, text/event-stream'})
        with urllib.request.urlopen(req, timeout=3) as r: pass
    except urllib.error.HTTPError as e:
        if e.code not in (400, 200, 406): raise Exception(f'Port {p} code {e.code}')
    except Exception as e:
        raise Exception(f'Port {p} failed: {e}')
print('OK')
" 2>&1)
    if [[ "$mcp_test" =~ "OK" ]]; then
        echo -e "${GREEN}PASS${NC}"
    else
        echo -e "${RED}FAILED${NC} ($mcp_test)"
        errors=$((errors + 1))
    fi

    echo -n " [4/5] Checking internal API backend (Port 8642) ... "
    svc_test=$(podman exec -i deepagent-service python3 -c "
import urllib.request
with urllib.request.urlopen('http://127.0.0.1:8642/health', timeout=3) as r:
    print('OK' if r.status == 200 else 'FAIL')
" 2>/dev/null || echo "FAIL")
    if [ "$svc_test" == "OK" ]; then
        echo -e "${GREEN}PASS${NC}"
    else
        echo -e "${RED}FAILED (Port 8642 not responding 200)${NC}"
        errors=$((errors + 1))
    fi

    echo -n " [5/5] Checking External HTTPS Endpoint (Port 8443) ... "
    http_code=$(curl -k -s -o /dev/null -w "%{http_code}" https://127.0.0.1:8443/health 2>/dev/null || echo "000")
    if [ "$http_code" == "200" ]; then
        echo -e "${GREEN}PASS (HTTP 200 OK)${NC}"
    else
        echo -e "${RED}FAILED (HTTP $http_code)${NC}"
        errors=$((errors + 1))
    fi

    echo -e "${BLUE}====================================================${NC}"
    if [ $errors -eq 0 ]; then
        echo -e "${GREEN}🎉 SMOKE TEST PASSED: System is completely healthy.${NC}"
        return 0
    else
        echo -e "${RED}❌ SMOKE TEST FAILED with $errors error(s).${NC}"
        return 1
    fi
}

create_snapshot() {
    local label="${1:-$(date +%Y%m%d_%H%M%S)}"
    echo -e "\n${BLUE}====================================================${NC}"
    echo -e "${YELLOW}>>> Creating Snapshot: [backup-${label}]...${NC}"
    echo -e "${BLUE}====================================================${NC}"

    for c in "${CRITICAL_CONTAINERS[@]}"; do
        local img_tag="localhost/${c}:backup-${label}"
        echo -n "  📸 Snapshotting $c -> $img_tag ... "
        podman commit "$c" "$img_tag" >/dev/null
        echo -e "${GREEN}✓ Done${NC}"
    done

    mkdir -p "$HOME/.deepagent_snapshots"
    echo "$label" > "$HOME/.deepagent_snapshots/latest"
    echo "$(date '+%Y-%m-%d %H:%M:%S') | Label: backup-${label}" >> "$HOME/.deepagent_snapshots/history.log"
    echo -e "\n${GREEN}✓ Snapshot [backup-${label}] created successfully.${NC}"
}

rollback_snapshot() {
    local label="$1"
    if [ -z "$label" ]; then
        if [ -f "$HOME/.deepagent_snapshots/latest" ]; then
            label=$(cat "$HOME/.deepagent_snapshots/latest")
        else
            echo -e "${RED}Error: No snapshot label specified.${NC}"
            exit 1
        fi
    fi

    echo -e "\n${BLUE}====================================================${NC}"
    echo -e "${YELLOW}>>> Rolling Back to Snapshot: [backup-${label}]...${NC}"
    echo -e "${BLUE}====================================================${NC}"

    for c in "${CRITICAL_CONTAINERS[@]}"; do
        local original_img="localhost/${c}:backup-${label}"
        podman stop -t 2 "$c" >/dev/null 2>&1 || true
        podman rm "$c" >/dev/null 2>&1 || true

        if [ "$c" == "deepagent-service" ]; then
            podman run -d --name deepagent-service --pod deepagent-prod-pod "$original_img" python -m app.main >/dev/null
        elif [ "$c" == "deepagent-proxy" ]; then
            podman run -d --name deepagent-proxy --pod deepagent-prod-pod "$original_img" nginx -g "daemon off;" >/dev/null
        elif [ "$c" == "deepagent-webui" ]; then
            podman run -d --name deepagent-webui --pod deepagent-prod-pod "$original_img" python -m http.server 3000 >/dev/null
        elif [ "$c" == "deepagent-ansible-mcp" ]; then
            podman run -d --name deepagent-ansible-mcp --pod deepagent-prod-pod "$original_img" python ansible_mcp_server.py >/dev/null
        elif [ "$c" == "deepagent-sop-mcp" ]; then
            podman run -d --name deepagent-sop-mcp --pod deepagent-prod-pod "$original_img" python server.py >/dev/null
        fi
        echo -e "${GREEN}✓ Restored $c${NC}"
    done

    echo "Waiting 5 seconds for services to initialize..."
    sleep 5
    run_smoke_test
}

list_snapshots() {
    echo -e "\n${BLUE}====================================================${NC}"
    echo -e "${YELLOW}>>> Existing DeepAgent Container Snapshots:${NC}"
    echo -e "${BLUE}====================================================${NC}"
    podman images | grep "backup-" || echo "No snapshots found."
}

case "${1:-test}" in
    snapshot) create_snapshot "$2" ;;
    test) run_smoke_test ;;
    rollback) rollback_snapshot "$2" ;;
    list) list_snapshots ;;
    *) echo "Usage: $0 {snapshot [label] | test | rollback [label] | list}" ; exit 1 ;;
esac
SNAPSHOT_TEST_EOF

chmod +x "${SCRIPTS_DIR}/pod_snapshot_and_test.sh"
echo -e "${GREEN}✓ Created and made executable: ${SCRIPTS_DIR}/pod_snapshot_and_test.sh${NC}"

# ------------------------------------------------------------------------------
# Post-setup Smoke Test
# ------------------------------------------------------------------------------
echo -e "\n${YELLOW}>>> Running initial post-restore smoke test...${NC}"
"${SCRIPTS_DIR}/pod_snapshot_and_test.sh" test

echo -e "\n${GREEN}====================================================================${NC}"
echo -e "${GREEN}🎉 SETUP & RESTORE COMPLETE: All scripts are ready and tested!     ${NC}"
echo -e "${GREEN}====================================================================${NC}"
