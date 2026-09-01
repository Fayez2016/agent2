# LangGraph Deep Agent Implementation Plan (With Custom Subagents, React UI & Dual Ansible Backend)

## Executive Summary
This document provides the complete, isolated plan for building a new AI agent system powered by **LangGraph Deep Agent** (`deepagents` package by LangChain, using **Custom Subagents** as defined in official `dcode` documentation) and a **Local Ollama Model** (`gemma4:12b` / `qwen3:1.7b` / `qwen2.5:3b`), complete with a modern **React + `@langchain/react` `useStream()` Control Panel UI**.

The system is **rootless**, **containerized**, and split into **independent microservices**. It features a **Dual Ansible Backend Configuration (`ANSIBLE_BACKEND_MODE=mock|prd`)**, a self-contained **Mock AAP Server (`deepagent_system/mock_aap/`)**, and auto-discovered **Official MCP Server Configuration (`.mcp.json`)**.

This project lives inside `/home/fayez/agent2/deepagent_system/` to ensure zero interference with the existing Hermes agent codebase.

---

## Architecture & System Structure

```
/home/fayez/agent2/deepagent_system/
├── DESIGN.md                    # System architecture design (Mock vs PRD AAP mode spec)
├── REQUIREMENTS.md              # Requirements specification (rootless, microservices, HITL)
├── PLAN.md                      # Implementation plan (This document)
├── .env.example                 # Environment template (ANSIBLE_BACKEND_MODE=mock|prd)
├── .mcp.json                    # Official Deep Agents MCP server discovery config
├── mock_aap/                    # Reusable Mock AAP Server directory
│   ├── mock_aap.py              # Flask server simulating Ansible Automation Platform API
│   └── mock_aap.Dockerfile      # Container definition for mock AAP server
├── .deepagents/
│   └── agents/
│       ├── rhel-diagnostics/
│       │   └── AGENTS.md        # Specialized subagent for pre-patch checks & cluster diagnostics
│       └── fleet-patcher/
│           └── AGENTS.md        # Specialized subagent for RHEL patching & service restarts
├── app/
│   ├── __init__.py              # App package
│   ├── config.py                # Configuration loader (ANSIBLE_BACKEND_MODE, OLLAMA_HOST, MCP_URL)
│   ├── prompts.py               # Prompt aggregator (SOUL.md rules & SOP guidelines)
│   ├── mcp_client.py            # MCP Client loading tools via .mcp.json
│   ├── agent_engine.py          # Official create_deep_agent constructor with Subagents
│   └── main.py                  # FastAPI REST API (/v1/chat/completions) & CLI entrypoint
├── web_ui/                      # React Control Panel UI (@langchain/react + useStream)
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChatStream.tsx   # React useStream component
│   │   │   ├── ToolCard.tsx     # Tool-call lifecycle cards
│   │   │   └── HITLDialog.tsx   # Human-in-the-loop approval dialog
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── index.html
│   └── package.json             # React dependencies (@langchain/react)
├── requirements.txt             # Python package dependencies (deepagents>=0.7)
├── deepagent.Dockerfile         # Container definition for Python microservice
├── web_ui.Dockerfile            # Container definition for React frontend UI
├── docker-compose.deepagent.yml # Dedicated compose file for Deep Agent, Ollama & Web UI
├── push_to_github.sh            # Git commit and push script (https://github.com/Fayez2016/deepagent.git)
└── run_deepagent_tests.py       # E2E test verification script
```

---

## Dual Ansible Backend Switch (`ANSIBLE_BACKEND_MODE=mock|prd`)

The system uses environment variables to dynamically switch between **Mock AAP** (testing) and **Production AAP (PRD)**:

```python
# app/config.py
import os

ANSIBLE_BACKEND_MODE = os.getenv("ANSIBLE_BACKEND_MODE", "mock").lower()

if ANSIBLE_BACKEND_MODE == "prd":
    AAP_HOST = os.getenv("AAP_HOST_PRD", "https://aap.prd.enterprise.local")
    AAP_TOKEN = os.getenv("AAP_TOKEN_PRD")
    AAP_VERIFY_SSL = os.getenv("AAP_VERIFY_SSL", "true").lower() == "true"
else: # default: mock
    AAP_HOST = os.getenv("AAP_HOST_MOCK", "http://aap-server:5000")
    AAP_TOKEN = os.getenv("AAP_TOKEN_MOCK", "mock-token-123")
    AAP_VERIFY_SSL = False
```

---

## Milestone Execution Checklist

- [x] **Step 0: Design & Requirements Specification**
  - Create [`deepagent_system/DESIGN.md`](file:///home/fayez/agent2/deepagent_system/DESIGN.md) (Architecture, rootless Podman configuration, microservice boundaries, Mock vs PRD AAP mode spec)
  - Create [`deepagent_system/REQUIREMENTS.md`](file:///home/fayez/agent2/deepagent_system/REQUIREMENTS.md) (Rootless execution, decoupled containerization, air-gapped Ollama, HITL compliance, `ANSIBLE_BACKEND_MODE=mock|prd` matrix)
  - Copy reusable Mock AAP server to [`deepagent_system/mock_aap/`](file:///home/fayez/agent2/deepagent_system/mock_aap/mock_aap.py)

- [x] **Step 1: Codebase & Subagents Initialization**
  - Create [`deepagent_system/.mcp.json`](file:///home/fayez/agent2/deepagent_system/.mcp.json) (Official Deep Agents MCP configuration)
  - Create [`deepagent_system/.env.example`](file:///home/fayez/agent2/deepagent_system/.env.example) defining `ANSIBLE_BACKEND_MODE=mock|prd`
  - Create [`.deepagents/agents/rhel-diagnostics/AGENTS.md`](file:///home/fayez/agent2/deepagent_system/.deepagents/agents/rhel-diagnostics/AGENTS.md)
  - Create [`.deepagents/agents/fleet-patcher/AGENTS.md`](file:///home/fayez/agent2/deepagent_system/.deepagents/agents/fleet-patcher/AGENTS.md)
  - Create [`deepagent_system/requirements.txt`](file:///home/fayez/agent2/deepagent_system/requirements.txt)
  - Create [`deepagent_system/app/config.py`](file:///home/fayez/agent2/deepagent_system/app/config.py)
  - Create [`deepagent_system/app/prompts.py`](file:///home/fayez/agent2/deepagent_system/app/prompts.py)
  - Create [`deepagent_system/app/mcp_client.py`](file:///home/fayez/agent2/deepagent_system/app/mcp_client.py)
  - Create [`deepagent_system/app/agent_engine.py`](file:///home/fayez/agent2/deepagent_system/app/agent_engine.py)
  - Create [`deepagent_system/app/main.py`](file:///home/fayez/agent2/deepagent_system/app/main.py)

- [x] **Step 2: Containerization & Compose Setup**
  - Create [`deepagent_system/deepagent.Dockerfile`](file:///home/fayez/agent2/deepagent_system/deepagent.Dockerfile)
  - Create [`deepagent_system/docker-compose.deepagent.yml`](file:///home/fayez/agent2/deepagent_system/docker-compose.deepagent.yml)

- [x] **Step 3: Service Deployment**
  - Build and launch containers (`podman-compose -f deepagent_system/docker-compose.deepagent.yml up -d --build`)
  - Verify container status and logs

- [x] **Step 4: End-to-End Verification Suite**
  - Execute [`run_deepagent_tests.py`](file:///home/fayez/agent2/deepagent_system/run_deepagent_tests.py) (All 4 verification stages PASSED)

- [x] **Step 5: React Control Panel UI Implementation (@langchain/react)**
  - Built [`web_ui/`](file:///home/fayez/agent2/deepagent_system/web_ui/src/App.tsx) (React `@langchain/react` control panel dashboard)
  - Created [`web_ui.Dockerfile`](file:///home/fayez/agent2/deepagent_system/web_ui.Dockerfile)
