# Deep Agent Air-Gapped LLM Candidates & Production Binding Guide

This guide details the specifications for **Step 3.2: Production Environmental Binding**, including the primary model used in development and validation (**Qwen**), top candidate models for enterprise on-premise inference, and the exact steps to bind Deep Agent to production Red Hat AAP.

---

## 1. Primary Model Used in Testing: Qwen 2.5

Throughout Phase 1 and Phase 2 testing, the primary reference models used for multi-step LangGraph orchestration, function calling, and structured JSON output were:

| Model Identifier | Parameters | Primary Test Environment | Strengths & Capabilities |
| :--- | :---: | :--- | :--- |
| **`qwen/qwen-2.5-72b-instruct`** | **72B** | OpenRouter / Cloud Inference | Top-tier reasoning, complex HA topology discovery, multi-turn plan generation (`write_todos`), and strict JSON schema compliance. |
| **`qwen2.5:3b` / `qwen2.5:7b`** | **3B / 7B** | Local Ollama / Air-gapped CPU/small GPU | Lightweight local testing, rapid tool routing, and zero-latency loopback execution. |
| **`qwen/qwen3.6-27b`** | **27B** | Groq / High-Throughput Gateway | High token generation speed with robust tool calling. |

---

## 2. Top On-Premise Enterprise LLM Candidates for Air-Gapped Production

When deploying on-premise without external internet access (served via **vLLM**, **TGI**, **OpenShift AI**, or **Ollama**), these are the leading candidate models evaluated for Deep Agent:

### Candidate A: Qwen 2.5 Family (Recommended Baseline)
* **Model Tags**: `Qwen/Qwen2.5-72B-Instruct`, `Qwen/Qwen2.5-32B-Instruct`, `Qwen/Qwen2.5-14B-Instruct`
* **Why it fits**: Exceptional native tool-calling / function-calling benchmark scores. Highly reliable at parsing Ansible playbooks, cluster outputs (`pcs status`), and multi-host error traces without hallucinations.
* **Minimum Hardware**:
  - `72B` (FP16): 2x A100/H100 (80GB) or 4x A100 (40GB)
  - `32B` (AWQ/GPTQ 4-bit): 1x A100 (40GB) or 2x L40S (48GB)
  - `14B` (FP16): 1x A100 (40GB) or 1x RTX 6000 Ada

### Candidate B: DeepSeek-R1 Distill Qwen (Advanced Reasoning & Incident Recovery)
* **Model Tags**: `deepseek-ai/DeepSeek-R1-Distill-Qwen-32B`, `deepseek-ai/DeepSeek-R1-Distill-Qwen-14B`
* **Why it fits**: Combines DeepSeek's chain-of-thought (CoT) reasoning with Qwen's tool proficiency. Excels at complex, non-linear incident troubleshooting, analyzing cascading failures, and determining recovery procedures (e.g. IPMI reboot vs. fencing isolate).

### Candidate C: Red Hat Granite 3.0 / 3.1 (Enterprise Native & OpenShift AI)
* **Model Tags**: `ibm-granite/granite-3.0-8b-instruct`, `ibm-granite/granite-3.1-8b-instruct`
* **Why it fits**: Officially backed and trained for enterprise Linux, OpenShift, and Ansible automation tasks. Highly compact, license-friendly for enterprise deployment, and runs on smaller GPU footprints (single L4/A10/T4).

### Candidate D: Llama 3.3 70B Instruct
* **Model Tags**: `meta-llama/Llama-3.3-70B-Instruct`
* **Why it fits**: Industry-standard open-weights model with 128k context window and robust multi-step instruction following.

---

## 3. How Deep Agent Connects to Any OpenAI-Compliant Model Gateway

Deep Agent uses standard `langchain_openai.ChatOpenAI`. Any internal gateway serving standard OpenAI routes (`/v1/chat/completions` and `/v1/models`) connects out of the box.

### Configuration Parameters:
* **`custom_openai_base_url`**: The internal gateway URL (e.g., `http://vllm-service.ai.internal:8000/v1`)
* **`custom_openai_model`**: The served model identifier (e.g., `Qwen/Qwen2.5-32B-Instruct`)
* **`custom_openai_api_key`**: Bearer token (or `none` / `sk-dummy` if behind private network perimeter)

---

## 4. Production Red Hat AAP Binding Details

To switch from the simulated mock engine to real enterprise AAP:

### Required Parameters:
* **`aap_backend_mode`**: `production`
* **`aap_host`**: `https://<YOUR_AAP_CONTROLLER_FQDN>`
* **`aap_token`**: Application Bearer Token generated in AAP under **Users > Admin > Tokens**.
* **`aap_verify_ssl`**: `true` (enterprise CA) or `false` (self-signed internal cert).

### Job Template Requirements on Target AAP:
The production AAP controller must have Job Templates corresponding to the MCP tool names:
1. `PCS Node Standby`
2. `PCS Node Unstandby`
3. `PCS Cluster Stop` / `PCS Cluster Start`
4. `Patch Fleet`
5. `Reboot Fleet` / `Reboot Host`
6. `Limited Run Any Command`
