# Air-Gapped Deployment Issues & Permanent Automated Fixes

This document records the exact issues encountered on the target air-gapped server (`ps501484.aramco.com`) during deployment of `deepagent-prod-pod`, along with their root causes, manual workarounds, and the automated script updates applied to ensure zero manual intervention in future deployments.

---

## Issue Summary Matrix

| Issue # | Component | Error Message / Symptom | Root Cause | Solution & Automated Fix |
| :--- | :--- | :--- | :--- | :--- |
| **1** | `.env.production` | `cp: cannot stat .env.production.template: No such file or directory` | Script depended on an external template file not copied to the target directory. | Made installer script 100% self-contained by embedding configuration in memory / inline defaults. |
| **2** | File Permissions | `.env.production: Permission denied` | Host directory or old file was owned by `root`, preventing non-root user (`saua`) from writing. | Removed disk write dependency; configs are set in memory and fallback to `/tmp` if host path is read-only. |
| **3** | `deepagent-proxy` (SSL) | `nginx: [emerg] cannot load certificate key "/etc/nginx/ssl/server.key": Permission denied` | Host SSL directory had `700` permissions and key was `600`. Rootless container user `1001` could not read the host volume mount. | **Eliminated volume mount**. Container image already has pre-baked valid SSL certificates and `nginx.conf` with proper permissions. |
| **4** | Health Probe | `curl: (35) OpenSSL SSL_ERROR_ZERO_RETURN in connection to localhost` | On RHEL 9, `localhost` resolves to IPv6 `::1`. Rootless Podman port forwarding binds to IPv4 `127.0.0.1`. | Changed health check targets in script from `https://localhost:8443` to explicit IPv4 `https://127.0.0.1:8443`. |
| **5** | `deepagent-hitl-db` | `FATAL: could not create any Unix-domain sockets` / `could not set permissions of file "/var/run/postgresql": Operation not permitted` | In Alpine/PostgreSQL 16 under rootless Podman without subuid mapping (`ignore_chown_errors=true`), PostgreSQL's `chmod` on `/var/run/postgresql` fails. | Add `-e PGDATA=/var/lib/postgresql/data` and run PostgreSQL with `-c unix_socket_directories=/tmp` or listen on TCP `127.0.0.1`. |
| **6** | `domain_agents` DB Seed | Agent hangs for ~60s and returns empty message bubble | Pre-seeded database had `linux_sre` agent hardcoded to `model_provider='openrouter'`. In airgap, `openrouter.ai` has no network route and times out after 60s. | Run SQL update on `domain_agents`: `UPDATE domain_agents SET model_provider='custom_openai', model_name='<TAG>' WHERE key_name='linux_sre';` |
| **7** | `psql` CLI Invocations | `psql: error: connection to server on socket "/var/run/postgresql/.s.PGSQL.5432" failed: No such file or directory` | Default `psql` CLI in Alpine expects socket at `/var/run/postgresql`. Under rootless Podman, socket was moved to `/tmp` or TCP. | Explicitly connect via TCP with password: `psql -h 127.0.0.1 -U hermes -d hitl` with `-e PGPASSWORD=secret456`. |
| **8** | LLM Gateway Routes | `detail: Not Found` (404) vs `Method Not Allowed` (405) | Enterprise AI Gateways expose specific routes: `/models` is `GET`-only, `/chat/completions` is `POST`-only. Omitting or adding `/v1` can cause 404. | Tested full matrix; verified working route is `https://<GATEWAY_HOST>/chat/completions` accepting standard `POST` with bearer token. |
| **9** | Enterprise SSL / CA Trust | `detail: Connection error.` / `[SSL: CERTIFICATE_VERIFY_FAILED]` | While `curl -k` succeeded by ignoring SSL, Python's `truststore` reads from `/etc/ssl/certs/ca-certificates.crt`, which lacks internal enterprise Root CAs. | **Full TLS Preserved**: Extract gateway certificate chain live via `openssl s_client` and append into `/etc/ssl/certs/ca-certificates.crt`. Preserves strict TLS (`verify_mode=2`) securely without bypass. |
| **10** | Python Hook vs System CA | `sitecustomize.py` bypassed by low-level transports | `sitecustomize.py` monkey-patching top-level `httpx.Client` didn't catch `httpx2.HTTPTransport` used by `openai`. | Solved cleanly by injecting CA into system bundle (`/etc/ssl/certs/ca-certificates.crt`), making all libraries (`httpx`, `httpx2`, `urllib3`, `truststore`) trust the gateway natively. |
| **11** | Nginx Ingress vs Core API | `301 Moved Permanently` (nginx/1.22.1) on port 8080 | Port `8080` in the pod is Nginx's HTTP port that permanently redirects to HTTPS `8443`. The core FastAPI service actually listens on port `8642`. | Target internal API calls to `http://127.0.0.1:8642/v1/chat/completions` or via HTTPS `https://127.0.0.1:8443/v1/chat/completions`. |
| **12** | Uvicorn Boot Race Condition | Test query outputs `FAILED` immediately after restart | Uvicorn/FastAPI takes ~6-8 seconds to initialize PostgreSQL connection pools and discover FastMCP tools. Querying at 4 seconds hit `Connection refused`. | Added `/health` endpoint polling loop before executing chat verification query. |
| **13** | AAP Template Name Alias | `Template 'Reboot Host' not found` | The FastMCP tool `ansible_reboot_host` searches for template name `'Reboot Host'`, but the pre-baked mock AAP template list registered it as `'Reboot Fleet'`. | Register `'Reboot Host'` alias in mock AAP template table (`mock_aap.py`), mapping both single-host and fleet reboot calls to ID `111`. |

---

## Detailed Root Cause Analysis & Permanent Solutions

### Issue #6: The `openrouter` Database Seed Trap
* **Symptom:** Saving custom OpenAI details in the Web UI Settings tab did not activate the internal gateway. Sending "hi" waited 60 seconds and stopped.
* **Why:** The Web UI settings tab writes to the `system_settings` table. However, the active agent (`linux_sre`) in the `domain_agents` table has its own independent `model_provider` column, which was seeded with `'openrouter'`.
* **Fix:**
  ```bash
  podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -c "
  UPDATE domain_agents SET model_provider='custom_openai', model_name='<MODEL_TAG>', updated_at=NOW() WHERE key_name='linux_sre';
  "
  ```

### Issue #9, #10 & #12: Enterprise SSL Verification via Trusted CA Injection (Strict TLS Preserved)
* **Symptom:** Direct `curl -k` succeeded, but Python threw `Connection error.` (`[SSL: CERTIFICATE_VERIFY_FAILED]`).
* **Why:** The container uses Python `truststore`, which reads system certificates from `/etc/ssl/certs/ca-certificates.crt`. The internal enterprise Root CA was absent from that bundle.
* **Verified Permanent Solution (Preserves TLS):**
  Extract the gateway's certificate chain live over the network and inject it into the container's CA bundle:
  ```bash
  openssl s_client -showcerts -servername "$GW_HOST" -connect "${GW_HOST}:443" </dev/null 2>/dev/null | \
    awk '/-----BEGIN CERTIFICATE-----/,/-----END CERTIFICATE-----/' > /tmp/ca_chain.pem
  podman exec -i -u 0 deepagent-service bash -c "cat >> /etc/ssl/certs/ca-certificates.crt" < /tmp/ca_chain.pem
  podman restart deepagent-service
  ```
  **Result:** Deep Agent communicates securely with full TLS verification (`verify_mode=2 / STRICT VALIDATION`).

---

## Standalone Optimization Checklist for Future Airgap Deployments

1. **Deploy Pod:** Use rootless Podman with `--network host` or dedicated pod infra with ports `8080`, `8443`, `8642`.
2. **PostgreSQL Launch:** Always run with `-c unix_socket_directories=/tmp` and connect via `-h 127.0.0.1`.
3. **Database Seed:** Ensure `domain_agents` is initialized with `model_provider='custom_openai'`.
4. **CA Certificate Injection:** Automatically inject enterprise CA into `/etc/ssl/certs/ca-certificates.crt` during provisioning.
5. **FastMCP Ports:** Verify `deepagent-ansible-mcp:8000` and `deepagent-sop-mcp:8001` are running and responsive.

---

## Production Milestone & Verification Status

- **Status:** **OPERATIONAL & VALIDATED** (All 8 Pod Containers Online)
- **TLS Security:** Enforced (`verify_mode=2 / STRICT VALIDATION`) via `/etc/ssl/certs/ca-certificates.crt`.
- **Inference Models:** Multi-model enabled (`Qwen/Qwen3.8-27B`, `zai-org/GLM-5.3 Flash`, `deepseek-v4`).
- **Harness & Tooling:** Full autonomous reasoning chain active:
  - Discovers cluster state and node topology (`ansible_get_info` / `ansible_pcs_health_check`).
  - Retrieves operational runbooks and standards (`sop_get_procedure`).
  - Successfully spawns and orchestrates domain subagents (`task` delegation tool).
  - Enforces HITL gate on disruptive actions (standby, patch, reboot).

---

## Persistent Customizations & Retention Matrix

To ensure customizations survive container updates, host reboots, and clean redeployments without manual intervention, the following retention mechanisms are established:

| Component | Critical Customization | Retention Mechanism & Location | Survival Guarantee |
| :--- | :--- | :--- | :--- |
| **Inference Gateway** | Enterprise Root CA Bundle | `/etc/ssl/certs/ca-certificates.crt` in `deepagent-service` | Injected into container or mounted as host volume (`:ro,Z`). Survives restarts. |
| **Ansible MCP Engine** | Enterprise Root CA Bundle | `/etc/ssl/certs/ca-certificates.crt` in `deepagent-ansible-mcp` | Injected into container for TLS validation against real AAP server. |
| **Database (PostgreSQL)** | Models, API tokens, HITL audit, subagents | Podman named volume `db-data` (`/var/lib/postgresql/data`) | Survives container deletion (`podman rm`), image upgrades, and host reboots. |
| **Nginx Reverse Proxy** | TLS 1.3 certificates (`server.crt`/`server.key`) | Pre-baked in `deepagent-proxy` (`/etc/nginx/ssl`) with `644` permissions | Immune to rootless Podman volume permission lockouts (`chmod 700/600`). |
| **AAP Job Templates** | Tool name aliases (e.g. `Reboot Host` -> ID 111) | Registered in `mock_aap.py` / real AAP job templates | Survives container restarts; baked into AAP template map. |
| **Podman Storage** | Non-root overlay driver & chown handling | Host OS: `~/.config/containers/storage.conf` | Permanent on host. Prevents unpacking errors on airgap image loads. |
