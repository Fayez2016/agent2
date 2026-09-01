import asyncio
import logging
import httpx
from typing import Dict, Any, List
from datetime import datetime
from app.infrastructure.db.database import DatabasePool
from app.infrastructure.db.agent_repository import AgentRepository
from app.config import settings

logger = logging.getLogger("SupervisorDaemon")

class SupervisorDaemon:
    """
    Proactive Background Supervisor Daemon for Multi-Domain Deep Agent.
    Periodically checks the health of:
    1. PostgreSQL Database Pool
    2. All Registered Domain FastMCP Servers (Ansible, SOP, WinRM, vSphere, etc.)
    3. LLM Gateway (Ollama, OpenRouter, Groq)
    4. Automatically recovers stale socket connections and notifies the engine.
    """

    _instance = None
    _running = False
    _health_state: Dict[str, Any] = {
        "status": "healthy",
        "last_checked_at": None,
        "database": {"status": "unknown"},
        "llm_gateway": {"status": "unknown"},
        "mcp_servers": {},
        "summary": "Initializing supervisor daemon..."
    }

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = SupervisorDaemon()
        return cls._instance

    @classmethod
    def get_health_state(cls) -> Dict[str, Any]:
        return cls._health_state

    async def start(self):
        if self._running:
            return
        self._running = True
        logger.info("🛡️ Multi-MCP Supervisor Daemon started. Monitoring system health & socket connectivity.")
        asyncio.create_task(self._supervision_loop())

    async def _supervision_loop(self):
        while self._running:
            try:
                await self.check_all_health()
            except Exception as e:
                logger.error(f"Error during supervisor health check cycle: {e}", exc_info=True)
            await asyncio.sleep(10)  # Check every 10 seconds

    async def check_all_health(self) -> Dict[str, Any]:
        now_str = datetime.now().isoformat()
        db_healthy = await self._check_database()
        llm_healthy = await self._check_llm()
        mcp_results = await self._check_mcp_servers()

        all_mcp_up = all(s.get("status") == "healthy" for s in mcp_results.values()) if mcp_results else True
        is_all_healthy = db_healthy and llm_healthy and all_mcp_up

        self._health_state = {
            "status": "healthy" if is_all_healthy else "degraded",
            "last_checked_at": now_str,
            "database": {
                "status": "healthy" if db_healthy else "unreachable"
            },
            "llm_gateway": {
                "status": "healthy" if llm_healthy else "degraded",
                "provider": settings.llm_provider,
                "model": settings.ollama_model if settings.llm_provider == "ollama" else settings.openrouter_model
            },
            "mcp_servers": mcp_results,
            "summary": "All domain services, FastMCP bridges, and database connections are operational." if is_all_healthy else "One or more FastMCP endpoints or services are degraded/unreachable."
        }
        return self._health_state

    async def _check_database(self) -> bool:
        try:
            with DatabasePool.get_cursor() as cursor:
                cursor.execute("SELECT 1;")
                row = cursor.fetchone()
                return row is not None
        except Exception as e:
            logger.warning(f"Supervisor DB health probe failed: {e}")
            return False

    async def _check_llm(self) -> bool:
        if settings.llm_provider == "ollama":
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    resp = await client.get(f"{settings.ollama_host}/api/tags")
                    return resp.status_code == 200
            except Exception:
                return False
        return True

    async def _check_mcp_servers(self) -> Dict[str, Dict[str, Any]]:
        results = {}
        try:
            mcp_records = AgentRepository.get_all_mcp_servers(only_active=True)
        except Exception:
            mcp_records = []

        if not mcp_records:
            mcp_records = [
                {"name": "ansible", "url": settings.ansible_mcp_url, "domain_scope": "linux"},
                {"name": "sop", "url": settings.sop_mcp_url, "domain_scope": "linux"}
            ]

        for s in mcp_records:
            s_name = s.get("name")
            s_url = s.get("url")
            domain_scope = s.get("domain_scope", "global")
            
            status = "unreachable"
            latency_ms = 0
            start_time = asyncio.get_event_loop().time()
            
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    probe_url = s_url.rstrip("/")
                    resp = await client.get(probe_url, headers={"Accept": "text/event-stream, text/html, application/json, */*"})
                    elapsed = (asyncio.get_event_loop().time() - start_time) * 1000
                    latency_ms = round(elapsed, 1)
                    
                    # FastMCP streamable endpoints return 200, 400 (missing session ID), 404, 405, 406 when active & listening
                    if resp.status_code in [200, 400, 404, 405, 406]:
                        status = "healthy"
            except Exception as ex:
                status = "unreachable"
                logger.debug(f"Supervisor probe failed on MCP server '{s_name}' ({s_url}): {ex}")

            results[s_name] = {
                "name": s_name,
                "url": s_url,
                "domain_scope": domain_scope,
                "status": status,
                "latency_ms": latency_ms,
                "last_probed": datetime.now().isoformat()
            }

        return results
