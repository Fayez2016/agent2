import json
import logging
from typing import List, Dict, Any, Optional
from app.infrastructure.db.database import DatabasePool

logger = logging.getLogger("AgentRepository")

class AgentRepository:
    """Repository for managing dynamic Domain Agents, Subagents, MCP Servers, and Skills in PostgreSQL."""

    # --- MCP SERVERS ---
    @staticmethod
    def get_all_mcp_servers(domain_scope: Optional[str] = None, only_active: bool = True) -> List[Dict[str, Any]]:
        with DatabasePool.get_cursor() as cursor:
            query = "SELECT id, name, display_name, domain_scope, url, transport, is_active, headers FROM mcp_servers WHERE 1=1"
            params = []
            if only_active:
                query += " AND is_active = TRUE"
            if domain_scope:
                query += " AND (domain_scope = %s OR domain_scope = 'global')"
                params.append(domain_scope)
            query += " ORDER BY id ASC;"
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def upsert_mcp_server(name: str, url: str, domain_scope: str = "linux", display_name: Optional[str] = None, transport: str = "streamable_http", headers: Optional[dict] = None) -> int:
        with DatabasePool.get_cursor(commit=True) as cursor:
            cursor.execute(
                """
                INSERT INTO mcp_servers (name, display_name, domain_scope, url, transport, headers, is_active, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, TRUE, NOW())
                ON CONFLICT (name) DO UPDATE SET 
                    url = EXCLUDED.url,
                    display_name = COALESCE(EXCLUDED.display_name, mcp_servers.display_name),
                    domain_scope = EXCLUDED.domain_scope,
                    transport = EXCLUDED.transport,
                    headers = EXCLUDED.headers,
                    is_active = TRUE,
                    updated_at = NOW()
                RETURNING id;
                """,
                (name, display_name or name, domain_scope, url, transport, json.dumps(headers or {}))
            )
            return cursor.fetchone()["id"]

    # --- DOMAIN SKILLS ---
    @staticmethod
    def get_all_skills(domain_category: Optional[str] = None, only_enabled: bool = True) -> List[Dict[str, Any]]:
        with DatabasePool.get_cursor() as cursor:
            query = "SELECT id, name, display_name, domain_category, description, content_markdown, is_enabled FROM domain_skills WHERE 1=1"
            params = []
            if only_enabled:
                query += " AND is_enabled = TRUE"
            if domain_category:
                query += " AND (domain_category = %s OR domain_category = 'general')"
                params.append(domain_category)
            query += " ORDER BY id ASC;"
            cursor.execute(query, tuple(params))
            return [dict(r) for r in cursor.fetchall()]

    @staticmethod
    def upsert_skill(name: str, content_markdown: str, domain_category: str = "linux", display_name: Optional[str] = None, description: Optional[str] = None) -> int:
        with DatabasePool.get_cursor(commit=True) as cursor:
            cursor.execute(
                """
                INSERT INTO domain_skills (name, display_name, domain_category, description, content_markdown, is_enabled, updated_at)
                VALUES (%s, %s, %s, %s, %s, TRUE, NOW())
                ON CONFLICT (name) DO UPDATE SET 
                    display_name = COALESCE(EXCLUDED.display_name, domain_skills.display_name),
                    domain_category = EXCLUDED.domain_category,
                    description = EXCLUDED.description,
                    content_markdown = EXCLUDED.content_markdown,
                    is_enabled = TRUE,
                    updated_at = NOW()
                RETURNING id;
                """,
                (name, display_name or name, domain_category, description or "", content_markdown)
            )
            return cursor.fetchone()["id"]

    # --- DOMAIN MAIN AGENTS ---
    @staticmethod
    def get_all_agents(only_active: bool = True) -> List[Dict[str, Any]]:
        with DatabasePool.get_cursor() as cursor:
            query = "SELECT id, key_name, display_name, domain_category, description, model_provider, model_name, system_prompt, is_active FROM domain_agents"
            if only_active:
                query += " WHERE is_active = TRUE"
            query += " ORDER BY id ASC;"
            cursor.execute(query)
            agents = [dict(r) for r in cursor.fetchall()]
            for ag in agents:
                ag["subagents"] = AgentRepository.get_subagents_by_parent(ag["id"])
            return agents

    @staticmethod
    def get_agent_by_key(key_name: str) -> Optional[Dict[str, Any]]:
        with DatabasePool.get_cursor() as cursor:
            cursor.execute(
                """SELECT id, key_name, display_name, domain_category, description, model_provider, model_name, system_prompt, is_active 
                   FROM domain_agents WHERE key_name = %s LIMIT 1;""",
                (key_name,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            agent = dict(row)
            agent["subagents"] = AgentRepository.get_subagents_by_parent(agent["id"])
            return agent

    @staticmethod
    def upsert_agent(key_name: str, display_name: str, domain_category: str, system_prompt: str, description: str = "", model_provider: str = "openrouter", model_name: str = "qwen/qwen-2.5-72b-instruct") -> int:
        with DatabasePool.get_cursor(commit=True) as cursor:
            cursor.execute(
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
            return cursor.fetchone()["id"]

    # --- DOMAIN SUBAGENTS ---
    @staticmethod
    def get_subagents_by_parent(parent_agent_id: int) -> List[Dict[str, Any]]:
        with DatabasePool.get_cursor() as cursor:
            cursor.execute(
                """SELECT id, parent_agent_id, name, display_name, description, system_prompt, tool_bindings, skills_path, is_active 
                   FROM domain_subagents WHERE parent_agent_id = %s AND is_active = TRUE ORDER BY id ASC;""",
                (parent_agent_id,)
            )
            rows = cursor.fetchall()
            subagents = []
            for r in rows:
                sub = dict(r)
                if isinstance(sub.get("tool_bindings"), str):
                    sub["tool_bindings"] = json.loads(sub["tool_bindings"])
                subagents.append(sub)
            return subagents

    @staticmethod
    def upsert_subagent(parent_agent_id: int, name: str, description: str, system_prompt: str, display_name: Optional[str] = None, tool_bindings: Optional[list] = None, skills_path: str = "/app/skills/") -> int:
        with DatabasePool.get_cursor(commit=True) as cursor:
            cursor.execute(
                """
                INSERT INTO domain_subagents (parent_agent_id, name, display_name, description, system_prompt, tool_bindings, skills_path, is_active, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, NOW())
                ON CONFLICT (parent_agent_id, name) DO UPDATE SET 
                    display_name = COALESCE(EXCLUDED.display_name, domain_subagents.display_name),
                    description = EXCLUDED.description,
                    system_prompt = EXCLUDED.system_prompt,
                    tool_bindings = EXCLUDED.tool_bindings,
                    is_active = TRUE,
                    updated_at = NOW()
                RETURNING id;
                """,
                (parent_agent_id, name, display_name or name, description, system_prompt, json.dumps(tool_bindings or []), skills_path)
            )
            return cursor.fetchone()["id"]

    @staticmethod
    def delete_mcp_server(name: str) -> bool:
        with DatabasePool.get_cursor(commit=True) as cursor:
            cursor.execute("DELETE FROM mcp_servers WHERE name = %s;", (name.strip().lower(),))
            return cursor.rowcount > 0

    @staticmethod
    def delete_agent(key_name: str) -> bool:
        with DatabasePool.get_cursor(commit=True) as cursor:
            cursor.execute("DELETE FROM domain_agents WHERE key_name = %s;", (key_name.strip().lower(),))
            return cursor.rowcount > 0

    @staticmethod
    def delete_skill(name: str) -> bool:
        with DatabasePool.get_cursor(commit=True) as cursor:
            cursor.execute("DELETE FROM domain_skills WHERE name = %s;", (name.strip().lower(),))
            return cursor.rowcount > 0
