#!/usr/bin/env bash
# ==============================================================================
# 🛠️ Deep Agent Fleet Config Manager (All-in-One Standalone Tool)
# ==============================================================================
# 100% Self-Contained. ZERO dependencies on external scripts or host packages.
# Embedded Python logic runs inside the deepagent-service container.
#
# Actions:
#   export    : Extracts current live configuration from PostgreSQL DB into YAML.
#               (Guarantees zero loss of active airgap model/gateway configurations).
#   customize : Customizes agents_fleet.yaml from gateway.conf or DB (airgap model).
#   sync      : Pushes agents_fleet.yaml into PostgreSQL and reloads service.
#
# Usage:
#   ./manage_fleet_config.sh export [output_yaml]
#   ./manage_fleet_config.sh customize [yaml_path] [gateway_conf_path]
#   ./manage_fleet_config.sh sync [yaml_path]
# ==============================================================================

set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACTION="${1:-help}"
YAML_FILE="${2:-${SCRIPT_DIR}/config/agents_fleet.yaml}"
GW_FILE="${3:-${SCRIPT_DIR}/gateway.conf}"

# Temporary container paths
CONTAINER_TARGET_YAML="/app/_fleet_mgr_target.yaml"
CONTAINER_GW_CONF="/app/_fleet_mgr_gateway.conf"
CONTAINER_PY_SCRIPT="/app/_fleet_mgr_embedded.py"

# Function to write and execute embedded Python script inside container
run_container_python() {
    local py_action="$1"
    
    # Generate the embedded Python script inside the container
    podman exec -i deepagent-service python3 -c '
import sys

script_code = """
import os
import sys
import json
import re
import yaml
import psycopg2
from psycopg2.extras import RealDictCursor

def get_db_connection():
    return psycopg2.connect(
        host="127.0.0.1",
        port=5432,
        user="hermes",
        password=os.environ.get("PGPASSWORD", "secret456"),
        dbname="hitl",
        cursor_factory=RealDictCursor,
        connect_timeout=5
    )

def read_gateway_conf(conf_paths):
    for path in conf_paths:
        if path and os.path.exists(path):
            config = {}
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        config[k.strip()] = v.strip().strip(\"\\\"\").strip(\"\\x27\")
            if config.get("GATEWAY_URL") or config.get("MODEL_NAME"):
                return config, path
    return None, None

def do_export(output_path):
    print(f"📥 Exporting live configuration from PostgreSQL to: {output_path}")
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT key, value FROM system_settings;")
        sys_settings = {r[\"key\"]: r[\"value\"] for r in cur.fetchall()}

        cur.execute("SELECT * FROM domain_agents WHERE key_name = \\x27linux_sre\\x27 LIMIT 1;")
        main_agent = cur.fetchone()
        if not main_agent:
            print("❌ Error: domain_agent \\x27linux_sre\\x27 not found in DB.")
            sys.exit(1)

        parent_id = main_agent[\"id\"]

        cur.execute("SELECT * FROM domain_subagents WHERE parent_agent_id = %s AND is_active = TRUE ORDER BY id ASC;", (parent_id,))
        subagents_rows = cur.fetchall()

        cur.execute("SELECT * FROM domain_skills WHERE is_enabled = TRUE ORDER BY id ASC;")
        skills_rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    eff_provider = main_agent.get(\"model_provider\") or sys_settings.get(\"llm_default_provider\", \"custom_openai\")
    if eff_provider == \"custom_openai\":
        eff_model = sys_settings.get(\"custom_openai_model\") or main_agent.get(\"model_name\", \"qwen2.5-72b-instruct\")
    elif eff_provider == \"openrouter\":
        eff_model = sys_settings.get(\"openrouter_model\") or main_agent.get(\"model_name\", \"qwen/qwen-2.5-72b-instruct\")
    else:
        eff_model = main_agent.get(\"model_name\", \"custom-model\")

    subagents_dict = {}
    for sub in subagents_rows:
        name = sub[\"name\"]
        tools = sub[\"tool_bindings\"] if isinstance(sub[\"tool_bindings\"], list) else json.loads(sub.get(\"tool_bindings\") or \"[]\")
        subagents_dict[name] = {
            \"display_name\": sub.get(\"display_name\", name),
            \"description\": sub.get(\"description\", \"\"),
            \"tools\": tools,
            \"system_prompt\": sub.get(\"system_prompt\", \"\")
        }

    skills_dict = {}
    for sk in skills_rows:
        name = sk[\"name\"]
        skills_dict[name] = {
            \"display_name\": sk.get(\"display_name\", name),
            \"domain_category\": sk.get(\"domain_category\", \"linux\"),
            \"description\": sk.get(\"description\", \"\"),
            \"content_markdown\": sk.get(\"content_markdown\", \"\")
        }

    config_data = {
        \"version\": \"1.0\",
        \"domain\": \"linux_sre\",
        \"main_agent\": {
            \"key_name\": main_agent[\"key_name\"],
            \"display_name\": main_agent[\"display_name\"],
            \"domain_category\": main_agent[\"domain_category\"],
            \"description\": main_agent[\"description\"],
            \"model_provider\": eff_provider,
            \"model_name\": eff_model,
            \"system_prompt\": main_agent[\"system_prompt\"]
        },
        \"subagents\": subagents_dict,
        \"skills\": skills_dict
    }

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, \"w\", encoding=\"utf-8\") as f:
        yaml.dump(config_data, f, sort_keys=False, default_flow_style=False, allow_unicode=True)

    print(f"✅ Successfully exported DB configuration!")
    print(f"   • Active Model Provider : {eff_provider}")
    print(f"   • Active Model Name     : {eff_model}")
    print(f"   • Subagents Exported    : {len(subagents_dict)}")
    print(f"   • Skills Exported       : {len(skills_dict)}")

def do_customize(yaml_path, gw_conf_path):
    print(f"🔍 Customizing \\x27{yaml_path}\\x27 based on gateway.conf or PostgreSQL...")
    target_provider = None
    target_model = None
    source_name = \"\"

    candidates = [gw_conf_path, \"/app/_fleet_mgr_gateway.conf\", \"/app/gateway.conf\"]
    gw_data, found_path = read_gateway_conf(candidates)

    if gw_data and (gw_data.get(\"MODEL_NAME\") or gw_data.get(\"GATEWAY_URL\")):
        target_provider = \"custom_openai\"
        target_model = gw_data.get(\"MODEL_NAME\", \"custom-model\")
        source_name = f\"gateway.conf ({found_path})\"
    else:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(\"SELECT key, value FROM system_settings WHERE key IN (\\x27llm_default_provider\\x27, \\x27custom_openai_model\\x27, \\x27custom_openai_base_url\\x27);\");
            rows = {r[\"key\"]: r[\"value\"] for r in cur.fetchall()}
            cur.execute(\"SELECT model_provider, model_name FROM domain_agents WHERE key_name = \\x27linux_sre\\x27;\");
            agent_row = cur.fetchone()
            cur.close()
            conn.close()

            if rows.get(\"custom_openai_model\"):
                target_provider = \"custom_openai\"
                target_model = rows[\"custom_openai_model\"]
                source_name = \"PostgreSQL system_settings\"
            elif agent_row and agent_row.get(\"model_name\"):
                target_provider = agent_row.get(\"model_provider\", \"custom_openai\")
                target_model = agent_row[\"model_name\"]
                source_name = \"PostgreSQL domain_agents\"
        except Exception as e:
            print(f\"  ⚠️ Could not read DB: {e}\")

    if not target_model:
        print(\"  ℹ️ No external gateway.conf or custom DB model detected. Retaining current values.\")
        return

    with open(yaml_path, \"r\", encoding=\"utf-8\") as f:
        content = f.read()

    new_content = content
    if target_provider:
        new_content = re.sub(r\"(\\bmodel_provider:\\s*)[^\\n]+\", rf\"\\g<1>\\\"{target_provider}\\\"\", new_content, count=1)
    if target_model:
        new_content = re.sub(r\"(\\bmodel_name:\\s*)[^\\n]+\", rf\"\\g<1>\\\"{target_model}\\\"\", new_content, count=1)

    if new_content != content:
        with open(yaml_path, \"w\", encoding=\"utf-8\") as f:
            f.write(new_content)
        print(f\"✅ Updated \\x27{yaml_path}\\x27 from {source_name}: {target_provider} / {target_model}\")
    else:
        print(f\"✓ \\x27{yaml_path}\\x27 is already aligned with {source_name} ({target_provider} / {target_model}).\")

def do_sync(yaml_path):
    print(f\"🔄 Synchronizing \\x27{yaml_path}\\x27 to PostgreSQL...\")
    if not os.path.exists(yaml_path):
        print(f\"❌ Error: YAML file \\x27{yaml_path}\\x27 not found.\")
        sys.exit(1)

    with open(yaml_path, \"r\", encoding=\"utf-8\") as f:
        cfg = yaml.safe_load(f)

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        main_cfg = cfg.get(\"main_agent\", {})
        key_name = main_cfg.get(\"key_name\", \"linux_sre\")
        display_name = main_cfg.get(\"display_name\", \"Linux SRE Lead Agent\")
        domain_category = main_cfg.get(\"domain_category\", \"linux\")
        description = main_cfg.get(\"description\", \"\")
        model_provider = main_cfg.get(\"model_provider\", \"custom_openai\")
        model_name = main_cfg.get(\"model_name\", \"qwen/qwen-2.5-72b-instruct\")
        system_prompt = main_cfg.get(\"system_prompt\", \"\").strip()

        print(f\"[1/3] Syncing Main Agent: {key_name} ({model_provider} / {model_name})...\")
        cur.execute(
            \"\"\"
            INSERT INTO domain_agents (key_name, display_name, domain_category, description, model_provider, model_name, system_prompt, is_active, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, NOW())
            ON CONFLICT (key_name) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                domain_category = EXCLUDED.domain_category,
                description = EXCLUDED.description,
                model_provider = EXCLUDED.model_provider,
                model_name = EXCLUDED.model_name,
                system_prompt = EXCLUDED.system_prompt,
                is_active = TRUE,
                updated_at = NOW()
            RETURNING id;
            \"\"\",
            (key_name, display_name, domain_category, description, model_provider, model_name, system_prompt)
        )
        parent_agent_id = cur.fetchone()[\"id\"]
        print(f\"  ✓ Main Agent updated (ID: {parent_agent_id})\")

        subagents = cfg.get(\"subagents\", {})
        print(f\"\\n[2/3] Syncing {len(subagents)} Subagents...\")
        for sub_name, s_data in subagents.items():
            s_display = s_data.get(\"display_name\", sub_name)
            s_desc = s_data.get(\"description\", \"\")
            s_prompt = s_data.get(\"system_prompt\", \"\").strip()
            s_tools = s_data.get(\"tools\", [])
            s_skills_path = s_data.get(\"skills_path\", \"/app/skills/\")

            cur.execute(
                \"\"\"
                INSERT INTO domain_subagents (parent_agent_id, name, display_name, description, system_prompt, tool_bindings, skills_path, is_active, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, NOW())
                ON CONFLICT (parent_agent_id, name) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    description = EXCLUDED.description,
                    system_prompt = EXCLUDED.system_prompt,
                    tool_bindings = EXCLUDED.tool_bindings,
                    skills_path = EXCLUDED.skills_path,
                    is_active = TRUE,
                    updated_at = NOW()
                RETURNING id;
                \"\"\",
                (parent_agent_id, sub_name, s_display, s_desc, s_prompt, json.dumps(s_tools), s_skills_path)
            )
            sub_id = cur.fetchone()[\"id\"]
            print(f\"  ✓ Subagent \\x27{sub_name}\\x27 synced ({len(s_tools)} tools, ID: {sub_id})\")

        skills = cfg.get(\"skills\", {})
        print(f\"\\n[3/3] Syncing {len(skills)} Declarative Skills / SOPs...\")
        for skill_name, sk_data in skills.items():
            sk_display = sk_data.get(\"display_name\", skill_name)
            sk_domain = sk_data.get(\"domain_category\", \"linux\")
            sk_desc = sk_data.get(\"description\", \"\")
            sk_content = sk_data.get(\"content_markdown\", \"\").strip()

            cur.execute(
                \"\"\"
                INSERT INTO domain_skills (name, display_name, domain_category, description, content_markdown, is_enabled, updated_at)
                VALUES (%s, %s, %s, %s, %s, TRUE, NOW())
                ON CONFLICT (name) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    domain_category = EXCLUDED.domain_category,
                    description = EXCLUDED.description,
                    content_markdown = EXCLUDED.content_markdown,
                    is_enabled = TRUE,
                    updated_at = NOW()
                RETURNING id;
                \"\"\",
                (skill_name, sk_display, sk_domain, sk_desc, sk_content)
            )
            sk_id = cur.fetchone()[\"id\"]
            print(f\"  ✓ Skill \\x27{skill_name}\\x27 synced (ID: {sk_id})\")

        conn.commit()
        print(\"\\n✅ Database synchronization completed successfully!\")
    except Exception as e:
        conn.rollback()
        print(f\"❌ Error syncing to database: {e}\")
        sys.exit(1)
    finally:
        cur.close()
        conn.close()

if __name__ == \"__main__\":
    act = sys.argv[1].lower() if len(sys.argv) > 1 else \"help\"
    y_file = sys.argv[2] if len(sys.argv) > 2 else \"/app/_fleet_mgr_target.yaml\"
    gw = sys.argv[3] if len(sys.argv) > 3 else \"/app/_fleet_mgr_gateway.conf\"

    if act == \"export\":
        do_export(y_file)
    elif act == \"customize\":
        do_customize(y_file, gw)
    elif act == \"sync\":
        do_sync(y_file)
"""

with open("/app/_fleet_mgr_embedded.py", "w") as f:
    f.write(script_code)
'
}

case "${ACTION}" in
    export)
        echo -e "${CYAN}${BOLD}📥 [1/2] Exporting live configuration from database...${NC}"
        run_container_python "export"
        podman exec -i deepagent-service python3 "${CONTAINER_PY_SCRIPT}" export "${CONTAINER_TARGET_YAML}"
        podman cp "deepagent-service:${CONTAINER_TARGET_YAML}" "${YAML_FILE}"
        podman exec -i deepagent-service rm -f "${CONTAINER_TARGET_YAML}" "${CONTAINER_PY_SCRIPT}"
        echo -e "${GREEN}${BOLD}✓ [2/2] Successfully exported live database configuration to: ${YAML_FILE}${NC}"
        ;;

    customize)
        echo -e "${CYAN}${BOLD}🔍 [1/3] Customizing configuration from gateway or DB...${NC}"
        if [ ! -f "${YAML_FILE}" ]; then
            echo -e "${YELLOW}⚠️ Target YAML '${YAML_FILE}' does not exist. Exporting current DB configuration first...${NC}"
            "$0" export "${YAML_FILE}"
        fi

        run_container_python "customize"
        podman cp "${YAML_FILE}" "deepagent-service:${CONTAINER_TARGET_YAML}"
        
        if [ -f "${GW_FILE}" ]; then
            podman cp "${GW_FILE}" "deepagent-service:${CONTAINER_GW_CONF}"
            podman exec -i deepagent-service python3 "${CONTAINER_PY_SCRIPT}" customize "${CONTAINER_TARGET_YAML}" "${CONTAINER_GW_CONF}"
            podman exec -i deepagent-service rm -f "${CONTAINER_GW_CONF}"
        else
            podman exec -i deepagent-service python3 "${CONTAINER_PY_SCRIPT}" customize "${CONTAINER_TARGET_YAML}" ""
        fi

        podman cp "deepagent-service:${CONTAINER_TARGET_YAML}" "${YAML_FILE}"
        podman exec -i deepagent-service rm -f "${CONTAINER_TARGET_YAML}" "${CONTAINER_PY_SCRIPT}"
        echo -e "${GREEN}${BOLD}✓ [2/3] Configuration customized cleanly in: ${YAML_FILE}${NC}"
        echo -e "${YELLOW}ℹ️  [3/3] To apply these changes to the live agent, run:${NC}"
        echo -e "   ${BOLD}$0 sync ${YAML_FILE}${NC}"
        ;;

    sync)
        echo -e "${CYAN}${BOLD}🔄 [1/3] Synchronizing ${YAML_FILE} to database...${NC}"
        if [ ! -f "${YAML_FILE}" ]; then
            echo -e "${RED}❌ Error: Configuration file not found at: ${YAML_FILE}${NC}"
            exit 1
        fi

        run_container_python "sync"
        podman cp "${YAML_FILE}" "deepagent-service:${CONTAINER_TARGET_YAML}"
        podman exec -i deepagent-service python3 "${CONTAINER_PY_SCRIPT}" sync "${CONTAINER_TARGET_YAML}"
        podman exec -i deepagent-service rm -f "${CONTAINER_TARGET_YAML}" "${CONTAINER_PY_SCRIPT}"

        echo -e "\n${BOLD}[2/3] Gracefully reloading deepagent-service...${NC}"
        podman restart deepagent-service >/dev/null
        echo -e "${GREEN}✓ deepagent-service reloaded.${NC}"

        echo -e "\n${CYAN}${BOLD}==============================================================================${NC}"
        echo -e "${GREEN}${BOLD} 🎉 [3/3] Synchronization Complete! Live Agent is 100% Up to Date.            ${NC}"
        echo -e "${CYAN}${BOLD}==============================================================================${NC}"
        ;;

    *)
        echo -e "${CYAN}${BOLD}==============================================================================${NC}"
        echo -e "${CYAN}${BOLD} 🛠️ DEEP AGENT FLEET CONFIG MANAGER (ALL-IN-ONE STANDALONE)                   ${NC}"
        echo -e "${CYAN}${BOLD}==============================================================================${NC}"
        echo "Usage: $0 {export|customize|sync} [yaml_path] [gateway_conf_path]"
        echo ""
        echo "Commands:"
        echo "  export    : Export current live DB configuration to YAML (avoids overwriting airgap models)"
        echo "  customize : Align YAML model_provider & model_name from gateway.conf or DB"
        echo "  sync      : Synchronize YAML into PostgreSQL and reload service"
        echo ""
        echo "Examples:"
        echo "  $0 export config/agents_fleet.yaml"
        echo "  $0 customize config/agents_fleet.yaml gateway.conf"
        echo "  $0 sync config/agents_fleet.yaml"
        exit 1
        ;;
esac
