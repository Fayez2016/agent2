#!/usr/bin/env python3
"""
sync_agents.py
Reads config/agents_fleet.yaml and synchronizes:
1. domain_agents (Main Lead Agent prompt, model, metadata)
2. domain_subagents (Subagents, system prompts, tool bindings)
3. domain_skills (Declarative SOP markdown)
into PostgreSQL (deepagent-hitl-db).
"""

import sys
import os
import json
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
        cursor_factory=RealDictCursor
    )

def sync_configuration(yaml_path: str):
    if not os.path.exists(yaml_path):
        print(f"❌ Error: Configuration file '{yaml_path}' not found.")
        sys.exit(1)

    with open(yaml_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # 1. Sync Main Agent
        main_cfg = cfg.get("main_agent", {})
        key_name = main_cfg.get("key_name", "linux_sre")
        display_name = main_cfg.get("display_name", "Linux SRE Lead Agent")
        domain_category = main_cfg.get("domain_category", "linux")
        description = main_cfg.get("description", "")
        model_provider = main_cfg.get("model_provider", "openrouter")
        model_name = main_cfg.get("model_name", "qwen/qwen-2.5-72b-instruct")
        system_prompt = main_cfg.get("system_prompt", "").strip()

        print(f"[1/3] Syncing Main Agent: {key_name} ('{display_name}')...")
        cur.execute(
            """
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
            """,
            (key_name, display_name, domain_category, description, model_provider, model_name, system_prompt)
        )
        parent_agent_id = cur.fetchone()["id"]
        print(f"  ✓ Main Agent updated (ID: {parent_agent_id})")

        # 2. Sync Subagents
        subagents = cfg.get("subagents", {})
        print(f"\n[2/3] Syncing {len(subagents)} Subagents...")
        for sub_name, s_data in subagents.items():
            s_display = s_data.get("display_name", sub_name)
            s_desc = s_data.get("description", "")
            s_prompt = s_data.get("system_prompt", "").strip()
            s_tools = s_data.get("tools", [])
            s_skills_path = s_data.get("skills_path", "/app/skills/")

            cur.execute(
                """
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
                """,
                (parent_agent_id, sub_name, s_display, s_desc, s_prompt, json.dumps(s_tools), s_skills_path)
            )
            sub_id = cur.fetchone()["id"]
            print(f"  ✓ Subagent '{sub_name}' synced ({len(s_tools)} tools, ID: {sub_id})")

        # 3. Sync Declarative Skills / SOPs
        skills = cfg.get("skills", {})
        print(f"\n[3/3] Syncing {len(skills)} Declarative Skills / SOPs...")
        for skill_name, sk_data in skills.items():
            sk_display = sk_data.get("display_name", skill_name)
            sk_domain = sk_data.get("domain_category", "linux")
            sk_desc = sk_data.get("description", "")
            sk_content = sk_data.get("content_markdown", "").strip()

            cur.execute(
                """
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
                """,
                (skill_name, sk_display, sk_domain, sk_desc, sk_content)
            )
            sk_id = cur.fetchone()["id"]
            print(f"  ✓ Skill '{skill_name}' synced (ID: {sk_id})")

        conn.commit()
        print("\n✅ Database synchronization completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"❌ Error syncing to database: {e}")
        sys.exit(1)
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    yaml_file = sys.argv[1] if len(sys.argv) > 1 else "/app/config/agents_fleet.yaml"
    sync_configuration(yaml_file)
