import logging
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api.v1.chat import router as chat_router
from app.api.v1.hitl import router as hitl_router
from app.api.v1.settings import router as settings_router
from app.api.v1.threads import router as threads_router
from app.api.v1.studio import router as studio_router
from app.api.v1.events import router as events_router
from app.api.v1.auth import router as auth_router

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("DeepAgentAPI")

# Initialize FastAPI App with CORS
app = FastAPI(
    title="LangGraph Deep Agent Service",
    description="Domain-driven Deep Agent Autonomous SRE API with Multi-Server MCP integration.",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Modular API Routers
app.include_router(chat_router)
app.include_router(hitl_router)
app.include_router(settings_router)
app.include_router(threads_router)
app.include_router(studio_router)
app.include_router(events_router)
app.include_router(auth_router)

@app.on_event("startup")
async def on_startup():
    """Starts the Multi-MCP Supervisor Daemon on API server startup."""
    from app.supervisor import SupervisorDaemon
    daemon = SupervisorDaemon.get_instance()
    await daemon.start()
    logger.info("✓ SupervisorDaemon initialized and running background health loops.")

@app.get("/health")
async def health_check():
    """Comprehensive microservice & MCP health probe endpoint."""
    from app.supervisor import SupervisorDaemon
    daemon = SupervisorDaemon.get_instance()
    state = daemon.get_health_state()
    return state

@app.get("/v1/system/supervisor")
async def get_supervisor_status():
    """Detailed supervisor status endpoint for Web UI monitoring."""
    from app.supervisor import SupervisorDaemon
    daemon = SupervisorDaemon.get_instance()
    await daemon.check_all_health()
    return daemon.get_health_state()

if __name__ == "__main__":
    logger.info(f"Starting Deep Agent REST API server on port {settings.api_port}...")
    uvicorn.run(app, host=settings.api_server_host, port=settings.api_port)
