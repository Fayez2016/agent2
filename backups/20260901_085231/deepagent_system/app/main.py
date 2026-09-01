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

@app.get("/health")
async def health_check():
    """Health probe endpoint."""
    return {"status": "ok", "version": "2.0.0"}

if __name__ == "__main__":
    logger.info(f"Starting Deep Agent REST API server on port {settings.api_port}...")
    uvicorn.run(app, host=settings.api_server_host, port=settings.api_port)
