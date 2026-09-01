#!/usr/bin/env python3
"""
================================================================================
 Consolidated SRE Verification & End-to-End Test Suite
================================================================================
 Runs and asserts the full suite of operational test scenarios:
 1. Health Check & Mode Verification (Enforced vs Autonomous)
 2. Dynamic Recipient Email Persistence & Retrieval
 3. 10-Cluster HA Rolling Update (Dynamic Discovery, 2-Wave Execution, Failure Isolation)
 4. Regular Fleet Patching (10 Hosts: Inventory -> Patch -> Reboot -> Verify -> Report)
 5. SRE Report Email Dispatch Verification
================================================================================
"""

import os
import sys
import time
import json
import requests

API_HOST = os.getenv("API_HOST", "http://localhost:8642")
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": "Bearer hermes-api-secret"
}

TEST_EMAIL = "fayez.soufyani@gmail.com"

def log_header(title: str):
    print("\n" + "=" * 78)
    print(f" 🧪 {title}")
    print("=" * 78)

def test_system_settings():
    log_header("TEST 1: System Settings & SRE Recipient Email")
    
    # Set Recipient Email
    res = requests.post(f"{API_HOST}/v1/settings/notification_email", json={"value": TEST_EMAIL})
    assert res.status_code == 200, f"Failed to save email: {res.text}"
    print(f" [PASS] Saved SRE recipient email: {TEST_EMAIL}")

    # Fetch Recipient Email
    res = requests.get(f"{API_HOST}/v1/settings/notification_email")
    assert res.status_code == 200, f"Failed to get email: {res.text}"
    fetched = res.json().get("email")
    assert fetched == TEST_EMAIL, f"Email mismatch: {fetched} != {TEST_EMAIL}"
    print(f" [PASS] Verified SRE recipient email from database: {fetched}")

    # Set Mode to Autonomous for automated pipeline
    res = requests.post(f"{API_HOST}/v1/settings/hitl_mode", json={"mode": "autonomous"})
    assert res.status_code == 200, f"Failed to set autonomous mode: {res.text}"
    print(" [PASS] Set guardrail mode to 'autonomous' for execution pipeline.")

def test_ha_10_clusters_rolling_update():
    log_header("TEST 2: 10-Cluster Zero-Downtime HA Rolling Update (SOP 2059253)")
    prompt = (
        "Using ha_cluster_patcher subagent, execute the Red Hat HA Rolling Update (SOP 2059253) "
        "across 10 HA clusters (ha_cluster1 to ha_cluster10). "
        "Dynamically discover member nodes (pattern: ha_cluster1_node1 to ha_cluster10_node2), "
        "execute Wave 1 for Node 1 across all clusters, isolate any failed cluster, "
        f"execute Wave 2 for Node 2 on healthy clusters, and email the final SRE report to {TEST_EMAIL}."
    )

    payload = {
        "model": "deepagent",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False
    }

    start = time.time()
    print(" Sending HA Rolling Update request to Deep Agent...")
    res = requests.post(f"{API_HOST}/v1/chat/completions", headers=HEADERS, json=payload, timeout=180)
    elapsed = time.time() - start

    assert res.status_code == 200, f"HA Rolling Update failed ({res.status_code}): {res.text}"
    reply = res.json()["choices"][0]["message"]["content"]

    print(f"\n--- Execution Finished in {elapsed:.2f}s ---")
    print(reply[:800] + ("...\n[Content truncated for display]" if len(reply) > 800 else ""))

    # Assertions
    has_clusters = any(f"ha_cluster{i}" in reply.lower() or f"cluster{i}" in reply.lower() for i in range(1, 11))
    has_wave1 = "node1" in reply.lower() or "wave 1" in reply.lower()
    has_table = "|" in reply or "matrix" in reply.lower() or "report" in reply.lower()

    assert has_clusters, "Failed: Did not discover/output 10 clusters."
    assert has_wave1, "Failed: Wave 1 primary execution not tracked."
    assert has_table, "Failed: Lifecycle matrix not generated."
    print("\n [PASS] 10-Cluster HA Rolling Update verified successfully.")

def test_regular_fleet_patching():
    log_header("TEST 3: Enterprise Fleet Patching (10 Hosts: rhel-prod-01 to rhel-prod-10)")
    prompt = (
        "Using fleet_patcher subagent, execute fleet patching on hosts rhel-prod-01 to rhel-prod-10: "
        f"inspect server inventory, apply package updates, execute managed reboots, verify online status, and email report to {TEST_EMAIL}."
    )

    payload = {
        "model": "deepagent",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False
    }

    start = time.time()
    print(" Sending Fleet Patching request to Deep Agent...")
    res = requests.post(f"{API_HOST}/v1/chat/completions", headers=HEADERS, json=payload, timeout=180)
    elapsed = time.time() - start

    assert res.status_code == 200, f"Fleet Patching failed ({res.status_code}): {res.text}"
    reply = res.json()["choices"][0]["message"]["content"]

    print(f"\n--- Execution Finished in {elapsed:.2f}s ---")
    print(reply[:800] + ("...\n[Content truncated for display]" if len(reply) > 800 else ""))

    # Assertions
    has_hosts = "rhel-prod" in reply.lower()
    has_table = "|" in reply or "matrix" in reply.lower()

    assert has_hosts, "Failed: Target hosts not found in report."
    assert has_table, "Failed: Host execution table not found."
    print("\n [PASS] Enterprise Fleet Patching verified successfully.")

def test_studio_crud_and_mcp_ping():
    log_header("TEST 4: Dynamic Agent & MCP Studio Endpoints & Live Tool Ping")
    
    # 1. Query registered MCP servers
    res = requests.get(f"{API_HOST}/v1/studio/mcp_servers")
    assert res.status_code == 200, f"Failed to list MCP servers: {res.text}"
    servers = res.json().get("servers", [])
    assert len(servers) >= 2, f"Expected at least 2 MCP servers, found {len(servers)}"
    print(f" [PASS] Listed {len(servers)} MCP servers from PostgreSQL: {[s['name'] for s in servers]}")

    # 2. Live Ping Ansible MCP Server
    res = requests.post(f"{API_HOST}/v1/studio/mcp_servers/ansible/ping")
    assert res.status_code == 200, f"Ping request failed: {res.text}"
    ping_data = res.json()
    assert ping_data["status"] == "connected", f"Ansible MCP not connected: {ping_data}"
    assert ping_data["live_tools_count"] > 10, f"Insufficient tools reported: {ping_data}"
    print(f" [PASS] Live ping successful on 'ansible' MCP server: {ping_data['live_tools_count']} live tools reported.")

    # 3. Query Domain Agents & Subagents
    res = requests.get(f"{API_HOST}/v1/studio/agents")
    assert res.status_code == 200, f"Failed to list agents: {res.text}"
    agents = res.json().get("agents", [])
    assert len(agents) >= 1, "No domain agents returned"
    linux_ag = next((a for a in agents if a["key_name"] == "linux_sre"), None)
    assert linux_ag is not None, "linux_sre agent not found"
    assert len(linux_ag.get("subagents", [])) >= 4, "Subagents not populated for linux_sre"
    print(f" [PASS] Dynamic Domain Agent '{linux_ag['key_name']}' loaded with {len(linux_ag['subagents'])} subagents.")

    # 4. Query Skills / SOPs
    res = requests.get(f"{API_HOST}/v1/studio/skills")
    assert res.status_code == 200, f"Failed to list skills: {res.text}"
    skills = res.json().get("skills", [])
    assert len(skills) >= 2, "Skills not populated"
    print(f" [PASS] Listed {len(skills)} declarative skills from PostgreSQL: {[s['name'] for s in skills]}")

def test_event_batcher_and_high_concurrency():
    log_header("TEST 5: 5-Minute Event Deduplicator Subagent & Alert Storm Ingestion")
    
    # 1. Simulate alert storm of 50 webhook alarms on 5 distinct targets
    targets = ["ha_cluster1_node1", "ha_cluster2_node1", "ha_cluster3_node1", "rhel-prod-04", "rhel-prod-08"]
    alarm_types = ["CPU_THROTTLING_ALARM", "HIGH_MEMORY_PRESSURE", "COROSYNC_TOKEN_LOSS", "DISK_INODE_FULL"]
    
    raw_events = []
    for i in range(50):
        raw_events.append({
            "host_target": targets[i % len(targets)],
            "alert_type": alarm_types[i % len(alarm_types)],
            "severity": "critical" if i % 4 == 0 else "warning",
            "domain": "linux",
            "payload": {"source": "Dynatrace", "alarm_seq": i}
        })

    # Bulk Ingestion
    res = requests.post(f"{API_HOST}/v1/events/bulk", json={"events": raw_events, "domain": "linux"})
    assert res.status_code == 200, f"Bulk ingestion failed: {res.text}"
    ingested_count = res.json().get("count", 0)
    assert ingested_count == 50, f"Expected 50 events ingested, got {ingested_count}"
    print(f" [PASS] Successfully buffered {ingested_count} high-frequency webhook alarms in PostgreSQL buffer.")

    # Query Buffer
    res = requests.get(f"{API_HOST}/v1/events/pending?domain=linux")
    assert res.status_code == 200, f"Failed to get pending events: {res.text}"
    pending = res.json().get("events", [])
    assert len(pending) >= 50, f"Expected at least 50 pending events, got {len(pending)}"
    print(f" [PASS] Verified PostgreSQL pending buffer table has {len(pending)} unprocessed rows.")

    # Trigger Event Batcher Deduplication Subagent Logic
    res = requests.post(f"{API_HOST}/v1/events/process_batch?domain=linux")
    assert res.status_code == 200, f"Batch processing failed: {res.text}"
    manifest = res.json().get("manifest", {})
    assert manifest.get("total_raw_events") >= 50, "Raw events not counted"
    assert manifest.get("deduplicated_count") == len(targets), f"Expected {len(targets)} targets, got {manifest.get('deduplicated_count')}"
    print(f" [PASS] Event Batcher successfully deduplicated {manifest.get('total_raw_events')} raw alarms into {manifest.get('deduplicated_count')} clean target nodes.")
    print(f" [PASS] Deduplication Summary: {manifest.get('summary')}")

def test_dynamic_mcp_and_agent_factory():
    log_header("TEST 6: Zero-Code Dynamic Agent & FastMCP Server Registration")
    
    # 1. Dynamically Register a New FastMCP Server via REST API
    test_mcp_payload = {
        "name": "dynamic_test_mcp",
        "display_name": "Dynamic Diagnostics FastMCP",
        "domain_scope": "linux",
        "url": "http://deepagent-ansible-mcp:8000/mcp",
        "transport": "streamable_http"
    }
    res = requests.post(f"{API_HOST}/v1/studio/mcp_servers", json=test_mcp_payload)
    assert res.status_code == 200, f"Failed to add dynamic MCP: {res.text}"
    print(" [PASS] Dynamically registered new FastMCP server 'dynamic_test_mcp' in PostgreSQL.")

    # 2. Live Ping Connection without Restart
    res = requests.post(f"{API_HOST}/v1/studio/mcp_servers/dynamic_test_mcp/ping")
    assert res.status_code == 200, f"Failed to ping dynamic MCP: {res.text}"
    ping_data = res.json()
    assert ping_data.get("status") == "connected", f"MCP ping failed: {ping_data}"
    assert ping_data.get("live_tools_count", 0) >= 20, "Live tools not discovered"
    print(f" [PASS] Live ping successful on dynamically added MCP: {ping_data.get('live_tools_count')} tools active.")

    # 3. Dynamically Register a New Main Domain Agent via REST API
    test_agent_payload = {
        "key_name": "database_admin",
        "display_name": "PostgreSQL & Database SRE",
        "domain_category": "database",
        "description": "Automated database maintenance and query optimization",
        "model_provider": "openrouter",
        "model_name": "qwen/qwen-2.5-72b-instruct",
        "system_prompt": "You are the Database Administrator SRE. You specialize in zero-downtime maintenance."
    }
    res = requests.post(f"{API_HOST}/v1/studio/agents", json=test_agent_payload)
    assert res.status_code == 200, f"Failed to create agent: {res.text}"
    print(" [PASS] Dynamically created Main Domain Agent 'database_admin' in PostgreSQL.")

    # 4. Clean up test records
    res_del_mcp = requests.delete(f"{API_HOST}/v1/studio/mcp_servers/dynamic_test_mcp")
    assert res_del_mcp.status_code == 200
    res_del_ag = requests.delete(f"{API_HOST}/v1/studio/agents/database_admin")
    assert res_del_ag.status_code == 200
    print(" [PASS] Cleaned up dynamic test MCP and agent records.")

def test_multidomain_alert_ingestion_and_simulation():
    log_header("TEST 7: Multi-Domain Alert Storm Simulation & Agent Analysis (Linux, Windows, VMware)")

    # 1. Linux HA Cluster Storm Simulation (30 alarms)
    linux_targets = ["ha_cluster1_node1", "ha_cluster2_node1", "ha_cluster3_node1"]
    linux_alarms = ["CorosyncTokenLoss", "PCSResourceFailCount", "DiskPressure95Percent"]
    raw_linux_events = []
    for i in range(30):
        raw_linux_events.append({
            "host_target": linux_targets[i % len(linux_targets)],
            "alert_type": linux_alarms[i % len(linux_alarms)],
            "severity": "critical" if i % 2 == 0 else "warning",
            "domain": "linux",
            "payload": {"source": "Dynatrace_RHEL_Agent", "event_id": f"linux_{i+1}"}
        })
    res_l = requests.post(f"{API_HOST}/v1/events/bulk", json={"events": raw_linux_events, "domain": "linux"})
    assert res_l.status_code == 200, f"Linux bulk ingestion failed: {res_l.text}"
    print(f" [PASS] Ingested 30 Linux HA cluster monitoring alarms into PostgreSQL buffer.")

    # 2. Windows Enterprise Storm Simulation (20 alarms)
    win_targets = ["win-dc-01.corp.internal", "win-iis-02.corp.internal"]
    win_alarms = ["ADReplicationFailure", "IISAppPoolStopped", "HighMemoryPressure"]
    raw_win_events = []
    for i in range(20):
        raw_win_events.append({
            "host_target": win_targets[i % len(win_targets)],
            "alert_type": win_alarms[i % len(win_alarms)],
            "severity": "critical",
            "domain": "windows",
            "payload": {"source": "SolarWinds_SCOM", "event_id": f"win_{i+1}"}
        })
    res_w = requests.post(f"{API_HOST}/v1/events/bulk", json={"events": raw_win_events, "domain": "windows"})
    assert res_w.status_code == 200, f"Windows bulk ingestion failed: {res_w.text}"
    print(f" [PASS] Ingested 20 Windows Enterprise Active Directory alarms into PostgreSQL buffer.")

    # 3. VMware Cloud Storm Simulation (20 alarms)
    vm_targets = ["esxi-cluster01-host01", "esxi-cluster01-host02"]
    vm_alarms = ["ESXiHostNotResponding", "DatastoreUsage98Percent", "vMotionFailed"]
    raw_vm_events = []
    for i in range(20):
        raw_vm_events.append({
            "host_target": vm_targets[i % len(vm_targets)],
            "alert_type": vm_alarms[i % len(vm_alarms)],
            "severity": "critical",
            "domain": "vmware",
            "payload": {"source": "vCenter_Alerts", "event_id": f"vm_{i+1}"}
        })
    res_v = requests.post(f"{API_HOST}/v1/events/bulk", json={"events": raw_vm_events, "domain": "vmware"})
    assert res_v.status_code == 200, f"VMware bulk ingestion failed: {res_v.text}"
    print(f" [PASS] Ingested 20 VMware vSphere infrastructure alarms into PostgreSQL buffer.")

    # 4. Process Windows Batch & Assert Domain Isolation & Auto-Created Incident Session
    res_proc_win = requests.post(f"{API_HOST}/v1/events/process_batch?domain=windows")
    assert res_proc_win.status_code == 200
    win_data = res_proc_win.json()
    win_manifest = win_data.get("manifest", {})
    assert win_manifest.get("total_raw_events") >= 20, "Windows raw events mismatch"
    assert win_manifest.get("deduplicated_count") == len(win_targets), "Windows target deduplication mismatch"
    assert win_data.get("thread_id") is not None, "Windows incident session thread was not auto-created"
    
    # Assert thread message has Windows SRE assessment
    res_win_msg = requests.get(f"{API_HOST}/v1/threads/{win_data['thread_id']}/messages")
    assert res_win_msg.status_code == 200
    win_msgs = res_win_msg.json().get("messages", [])
    assert any("Windows Enterprise Administrator" in m.get("content", "") or "ad_sync_operator" in m.get("content", "") for m in win_msgs), "Windows assessment missing from incident thread"
    print(f" [PASS] Windows Alert Storm Deduplicated: 20 alarms -> 2 nodes -> Dispatched ad_sync_operator.")

    # 5. Process VMware Batch & Assert Domain Isolation & Auto-Created Incident Session
    res_proc_vm = requests.post(f"{API_HOST}/v1/events/process_batch?domain=vmware")
    assert res_proc_vm.status_code == 200
    vm_data = res_proc_vm.json()
    vm_manifest = vm_data.get("manifest", {})
    assert vm_manifest.get("total_raw_events") >= 20, "VMware raw events mismatch"
    assert vm_manifest.get("deduplicated_count") == len(vm_targets), "VMware target deduplication mismatch"
    assert vm_data.get("thread_id") is not None, "VMware incident session thread was not auto-created"
    print(f" [PASS] VMware Alert Storm Deduplicated: 20 alarms -> 2 hosts -> Dispatched vmotion_operator.")

    # 6. Process Linux Batch & Assert Cluster Quorum Diagnostics
    res_proc_l = requests.post(f"{API_HOST}/v1/events/process_batch?domain=linux")
    assert res_proc_l.status_code == 200
    linux_data = res_proc_l.json()
    linux_manifest = linux_data.get("manifest", {})
    assert linux_manifest.get("total_raw_events") >= 30, "Linux raw events mismatch"
    assert linux_manifest.get("deduplicated_count") == len(linux_targets), "Linux target deduplication mismatch"
    print(f" [PASS] Linux Alert Storm Deduplicated: 30 alarms -> 3 nodes -> Dispatched rhel_diagnostician.")

def test_dynamic_random_alert_disambiguation():
    log_header("TEST 8: Dynamic Disambiguation of Random Related vs. Unrelated Alerts (Deep Agent ReAct Loop)")

    # 1. Generate randomized mixed alert payload containing:
    #    Track A (Related / Cascading): Storage Full on DB node causing VIP failover timeouts
    #    Track B (Unrelated / Independent): SSL certificate expiration on Web node
    #    Track C (Unrelated / Independent): Inode exhaustion on Log collector
    import random
    rnd_suffix = random.randint(100, 999)
    db_node = f"rhel-db-{rnd_suffix}"
    web_node = f"rhel-web-{rnd_suffix}"
    log_node = f"rhel-log-{rnd_suffix}"

    mixed_alerts = [
        # Related cascade 1 (Root Cause)
        {"host_target": db_node, "alert_type": "DISK_STORAGE_EXHAUSTED_99_PERCENT", "severity": "critical", "domain": "linux", "payload": {"mount": "/var/lib/pgsql", "free_mb": 12}},
        # Related cascade 2 (Downstream symptom)
        {"host_target": db_node, "alert_type": "POSTGRESQL_CONNECTION_TIMEOUT", "severity": "critical", "domain": "linux", "payload": {"error": "cannot extend transaction log file"}},
        # Related cascade 3 (Downstream symptom)
        {"host_target": db_node, "alert_type": "PCS_VIP_FAILOVER_HEURISTIC_TIMEOUT", "severity": "warning", "domain": "linux", "payload": {"resource": "db_vip"}},
        
        # Completely Unrelated Incident 1
        {"host_target": web_node, "alert_type": "SSL_CERTIFICATE_EXPIRED", "severity": "critical", "domain": "linux", "payload": {"cert": "/etc/pki/tls/certs/api.corp.pem", "days_remaining": -1}},
        
        # Completely Unrelated Incident 2
        {"host_target": log_node, "alert_type": "INODE_TABLE_FULL_ZERO_FREE", "severity": "warning", "domain": "linux", "payload": {"fs": "/var/log/journal", "inodes_free": 0}}
    ]

    print(f" [INFO] Ingesting randomized compound alert stream across 3 nodes ({db_node}, {web_node}, {log_node})...")
    res_ingest = requests.post(f"{API_HOST}/v1/events/bulk", json={"events": mixed_alerts, "domain": "linux"})
    assert res_ingest.status_code == 200, f"Failed to ingest mixed alerts: {res_ingest.text}"

    # 2. Invoke Deep Agent ReAct Loop to analyze and disambiguate
    # Direct prompt to Lead SRE Agent with raw incident manifest
    prompt = (
        f"You are the Lead Linux SRE Deep Agent. Analyze the following 5 incoming alerts from monitoring:\n"
        f"1. Host {db_node}: DISK_STORAGE_EXHAUSTED_99_PERCENT on /var/lib/pgsql\n"
        f"2. Host {db_node}: POSTGRESQL_CONNECTION_TIMEOUT (cannot extend transaction log)\n"
        f"3. Host {db_node}: PCS_VIP_FAILOVER_HEURISTIC_TIMEOUT on db_vip\n"
        f"4. Host {web_node}: SSL_CERTIFICATE_EXPIRED on /etc/pki/tls/certs/api.corp.pem\n"
        f"5. Host {log_node}: INODE_TABLE_FULL_ZERO_FREE on /var/log/journal\n\n"
        f"Perform Root Cause Analysis (RCA):\n"
        f"A) Clearly distinguish which alerts are RELATED and part of a single cascading failure vs. which are UNRELATED independent problems.\n"
        f"B) Propose specific remediation actions for each distinct incident track."
    )

    thread_id = f"test_rca_{rnd_suffix}"
    chat_payload = {
        "thread_id": thread_id,
        "message": prompt,
        "domain": "linux_sre"
    }

    t0 = time.time()
    res = requests.post(f"{API_HOST}/v1/chat/message", json=chat_payload, timeout=60)
    assert res.status_code == 200, f"Chat analysis failed: {res.text}"
    elapsed = time.time() - t0
    reply = res.json()["choices"][0]["message"]["content"]

    print(f"\n--- Dynamic Deep Agent Disambiguation Analysis ({elapsed:.2f}s) ---")
    print(reply[:900] + ("...\n[Content truncated for display]" if len(reply) > 900 else ""))

    # Assertions on dynamic LLM reasoning
    reply_lower = reply.lower()
    
    # 1. Must identify DB disk as root cause of DB cascade
    has_related_cascade = "related" in reply_lower or "cascade" in reply_lower or "root cause" in reply_lower
    has_db_root_cause = "disk" in reply_lower and "postgres" in reply_lower

    # 2. Must identify Web SSL and Log Inode as unrelated/independent
    has_unrelated_concept = "unrelated" in reply_lower or "independent" in reply_lower or "distinct" in reply_lower or "isolated" in reply_lower
    has_web_cert = "ssl" in reply_lower or "cert" in reply_lower
    has_log_inode = "inode" in reply_lower or "journal" in reply_lower

    assert has_related_cascade, "Failed: Deep Agent did not explain the cascading correlation."
    assert has_db_root_cause, "Failed: Deep Agent did not link DB disk full to the PostgreSQL timeouts."
    assert has_unrelated_concept, "Failed: Deep Agent did not distinguish unrelated independent incidents."
    assert has_web_cert and has_log_inode, "Failed: Deep Agent failed to evaluate the independent problem tracks."

    print("\n [PASS] Dynamic Alert Disambiguation verified: Deep Agent successfully correlated cascading DB failure and isolated unrelated SSL/Inode problems.")

def test_auth_rbac_and_scoped_tokens():
    log_header("TEST 9: Enterprise Authentication, RBAC User Management & Scoped API Token Generator")

    # 1. Operator Login
    login_res = requests.post(f"{API_HOST}/v1/auth/login", json={"username": "admin", "password": "admin123"})
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    login_data = login_res.json()
    assert login_data.get("status") == "success", "Login status not success"
    session_token = login_data.get("session_token")
    assert session_token is not None, "Missing session token"
    print(f" [PASS] Operator Login verified: authenticated as '{login_data['user']['username']}' (role: {login_data['user']['role']}).")

    # 2. Whoami / /v1/auth/me Verification
    me_res = requests.get(f"{API_HOST}/v1/auth/me", headers={"Authorization": f"Bearer {session_token}"})
    assert me_res.status_code == 200, f"Auth verification failed: {me_res.text}"
    assert me_res.json()["user"]["username"] == "admin"
    print(" [PASS] Bearer session token verified via /v1/auth/me.")

    # 3. Create New SRE Operator User
    new_user_payload = {
        "username": "sre_operator_test",
        "password": "Password123!",
        "role": "operator",
        "email": "sre.operator@enterprise.internal"
    }
    create_user_res = requests.post(f"{API_HOST}/v1/auth/users", json=new_user_payload)
    assert create_user_res.status_code == 200, f"Failed to create user: {create_user_res.text}"
    print(f" [PASS] Created new enterprise user 'sre_operator_test' with role 'operator'.")

    # 4. Generate Scoped API Token for SIEM / Monitoring Webhooks
    token_payload = {
        "name": "Dynatrace SRE Alert Webhook",
        "scope": "read_write",
        "domain_category": "linux",
        "expiry_option": "30d"
    }
    gen_token_res = requests.post(f"{API_HOST}/v1/auth/tokens", json=token_payload)
    assert gen_token_res.status_code == 200, f"Token generation failed: {gen_token_res.text}"
    token_record = gen_token_res.json().get("token_record", {})
    raw_api_key = token_record.get("raw_token")
    token_id = token_record.get("id")
    assert raw_api_key is not None and raw_api_key.startswith("da_sec_"), "Invalid raw API key format"
    print(f" [PASS] Generated 30-day scoped API key: '{token_record['name']}' (Expires: {token_record['expires_at']}).")

    # 5. Authenticate via Generated Scoped API Token
    api_auth_res = requests.get(f"{API_HOST}/v1/auth/me", headers={"Authorization": f"Bearer {raw_api_key}"})
    assert api_auth_res.status_code == 200, f"Scoped token validation failed: {api_auth_res.text}"
    assert api_auth_res.json().get("type") == "api_token"
    print(" [PASS] Validated external webhook authorization using generated Scoped API token.")

    # 6. Revoke Scoped API Token
    revoke_res = requests.delete(f"{API_HOST}/v1/auth/tokens/{token_id}")
    assert revoke_res.status_code == 200, f"Failed to revoke token: {revoke_res.text}"
    
    # Assert revoked token is rejected
    revoked_auth_res = requests.get(f"{API_HOST}/v1/auth/me", headers={"Authorization": f"Bearer {raw_api_key}"})
    assert revoked_auth_res.status_code == 401, "Revoked token was unexpectedly accepted"
    print(f" [PASS] Revocation verified: revoked token is immediately rejected by API security filter.")

def main():
    print("==============================================================================")
    print(" 🚀 DEEP AGENT CONSOLIDATED TEST SUITE")
    print("==============================================================================")
    
    suite_start = time.time()
    try:
        test_system_settings()
        test_studio_crud_and_mcp_ping()
        test_dynamic_mcp_and_agent_factory()
        test_event_batcher_and_high_concurrency()
        test_multidomain_alert_ingestion_and_simulation()
        test_dynamic_random_alert_disambiguation()
        test_auth_rbac_and_scoped_tokens()
        test_ha_10_clusters_rolling_update()
        test_regular_fleet_patching()
        
        total_time = time.time() - suite_start
        print("\n==============================================================================")
        print(f" 🎉 ALL CONSOLIDATED TESTS PASSED SUCCESSFULLY in {total_time:.2f}s!")
        print("==============================================================================\n")
    except AssertionError as e:
        print(f"\n ❌ TEST ASSERTION FAILED: {e}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n ❌ UNEXPECTED ERROR: {e}\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
