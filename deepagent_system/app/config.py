import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# 1. Ansible Backend Mode Selection ('mock' vs 'prd')
ANSIBLE_BACKEND_MODE = os.getenv("ANSIBLE_BACKEND_MODE", "mock").lower()

if ANSIBLE_BACKEND_MODE == "prd":
    AAP_HOST = os.getenv("AAP_HOST_PRD", "https://aap.prd.enterprise.local")
    AAP_TOKEN = os.getenv("AAP_TOKEN_PRD", "")
    AAP_VERIFY_SSL = os.getenv("AAP_VERIFY_SSL", "true").lower() == "true"
else:
    # Default: Mock Mode
    AAP_HOST = os.getenv("AAP_HOST_MOCK", "http://aap-server:5000")
    AAP_TOKEN = os.getenv("AAP_TOKEN_MOCK", "mock-token-123")
    AAP_VERIFY_SSL = False

# 2. Ollama Configuration
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")

# 3. MCP & Server Settings
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://ansible-mcp:8000/mcp")
API_PORT = int(os.getenv("API_PORT", "8642"))
API_SERVER_KEY = os.getenv("API_SERVER_KEY", "hermes-api-secret")
