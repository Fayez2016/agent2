import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class DeepAgentSettings(BaseSettings):
    """
    Centralized, strongly-typed configuration system using Pydantic v2 Settings.
    Eliminates all scattered os.getenv calls and hardcoded defaults.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # 1. API & Security
    api_port: int = Field(8642, description="Port for Core Deep Agent REST API")
    api_server_key: str = Field("hermes-api-secret", description="API Bearer Token")
    api_server_host: str = Field("0.0.0.0", description="Bind host for REST API")

    # 2. Database Connection
    database_url: Optional[str] = Field(None, description="Direct Database URL URI")
    db_host: str = Field("db", description="PostgreSQL host")
    db_port: int = Field(5432, description="PostgreSQL port")
    db_name: str = Field("hitl", description="Database name")
    db_user: str = Field("hermes", description="Database user")
    db_pass: str = Field("secret456", description="Database password")

    # 3. LLM Inference Engine
    ollama_host: str = Field("http://ollama:11434", description="Ollama API base URL")
    ollama_model: str = Field("qwen2.5:3b", description="Model tag")
    ollama_temperature: float = Field(0.0, description="Model inference temperature")

    # 4. Multi-Server MCP Endpoints
    ansible_mcp_url: str = Field("http://ansible-mcp:8000/mcp", description="Ansible FastMCP streamable URL")
    sop_mcp_url: str = Field("http://sop-mcp:8001/mcp", description="Dedicated SOP FastMCP streamable URL")
    mcp_server_url: str = Field("http://ansible-mcp:8000/mcp", description="Backward compatibility URL")

    # 5. Ansible Backend Settings
    ansible_backend_mode: str = Field("mock", description="Backend mode: 'mock' or 'prd'")
    aap_host_prd: str = Field("https://aap.prd.enterprise.local", description="PRD AAP Host")
    aap_token_prd: str = Field("", description="PRD AAP Token")
    aap_verify_ssl: bool = Field(False, description="Verify SSL for AAP")
    aap_host_mock: str = Field("http://aap-server:5000", description="Mock AAP Host")
    aap_token_mock: str = Field("mock-token-123", description="Mock AAP Token")

    # 6. Operational Guardrails & Timeouts
    hitl_default_mode: str = Field("enforced", description="Default HITL mode: 'enforced' or 'autonomous'")
    hitl_approval_window_minutes: int = Field(15, description="HITL approval validity window")
    reboot_probe_timeout_seconds: int = Field(60, description="Timeout for SSH port 22 probe after reboot")

    @property
    def effective_aap_host(self) -> str:
        return self.aap_host_prd if self.ansible_backend_mode == "prd" else self.aap_host_mock

    @property
    def effective_aap_token(self) -> str:
        return self.aap_token_prd if self.ansible_backend_mode == "prd" else self.aap_token_mock

    @property
    def effective_db_conn_string(self) -> str:
        if self.database_url:
            return self.database_url
        return f"postgresql://{self.db_user}:{self.db_pass}@{self.db_host}:{self.db_port}/{self.db_name}"

# Global settings singleton
settings = DeepAgentSettings()

# Backward compatibility module-level exports
API_PORT = settings.api_port
API_SERVER_KEY = settings.api_server_key
OLLAMA_HOST = settings.ollama_host
OLLAMA_MODEL = settings.ollama_model
MCP_SERVER_URL = settings.mcp_server_url
ANSIBLE_BACKEND_MODE = settings.ansible_backend_mode
AAP_HOST = settings.effective_aap_host
AAP_TOKEN = settings.effective_aap_token
AAP_VERIFY_SSL = settings.aap_verify_ssl
