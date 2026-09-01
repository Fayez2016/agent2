#!/usr/bin/env python3
"""
Deep Agent Interactive Test & Action Logger Script

Features:
1. Interactive CLI session or single-prompt execution mode.
2. Sends requests to Deep Agent REST API (:8642).
3. Auto-approval support (--auto-approve 20) for testing HITL operations with a configurable wait window.
4. Logs all user requests, assistant responses, MCP tool calls & outputs, execution latency, and error states.
5. Queries PostgreSQL HITL audit DB to track actions, approvals, and timestamp details.
6. Saves clean structured Markdown logs (logs/session_<timestamp>.md) and JSONL logs (logs/session_<timestamp>.jsonl).
"""

import sys
import os
import re
import time
import json
import requests
import datetime
import subprocess
import argparse
import threading
from typing import Dict, Any, Optional

DEEPAGENT_API_URL = "http://localhost:8642/v1/chat/completions"
HITL_URL = "http://localhost:5001"
API_KEY = "hermes-api-secret"
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")

os.makedirs(LOG_DIR, exist_ok=True)
SESSION_TIMESTAMP = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
MARKDOWN_LOG_FILE = os.path.join(LOG_DIR, f"session_{SESSION_TIMESTAMP}.md")
JSONL_LOG_FILE = os.path.join(LOG_DIR, f"session_{SESSION_TIMESTAMP}.jsonl")

def query_latest_hitl_db_record() -> Optional[Dict[str, Any]]:
    """Queries PostgreSQL container for the most recent hitl_requests record."""
    cmd = [
        "podman", "exec", "deepagent-hitl-db",
        "psql", "-U", "hermes", "-d", "hitl", "-t", "-A", "-c",
        "SELECT id, action_name, action_summary, status, requested_at, resolved_at FROM hitl_requests ORDER BY id DESC LIMIT 1;"
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        out = res.stdout.strip()
        if out:
            parts = out.split("|")
            if len(parts) >= 6:
                return {
                    "id": parts[0],
                    "action_name": parts[1],
                    "action_summary": parts[2],
                    "status": parts[3],
                    "requested_at": parts[4],
                    "resolved_at": parts[5]
                }
    except Exception:
        pass
    return None

def resolve_hitl_request_web(request_id: int) -> bool:
    """Logs into HITL Web Portal (:5001) and grants decision for a specific request ID."""
    session = requests.Session()
    login_url = f"{HITL_URL}/login"
    login_data = {"username": "admin", "password": "admin123"}
    try:
        r = session.get(HITL_URL, timeout=5)
        if "Login" in r.text and "Logout" not in r.text:
            csrf_match = re.search(r'name="csrf_token" value="(.*?)"', r.text)
            if csrf_match:
                token = csrf_match.group(1)
                session.post(login_url, data={**login_data, "csrf_token": token}, timeout=5)
                r = session.get(HITL_URL, timeout=5)

        forms = re.findall(r'action="/resolve/(\d+)".*?name="csrf_token" value="(.*?)"', r.text, re.DOTALL)
        for req_id, csrf in forms:
            if str(req_id) == str(request_id):
                res = session.post(
                    f"{HITL_URL}/resolve/{req_id}",
                    data={"decision": "GRANTED", "csrf_token": csrf},
                    timeout=5
                )
                if res.status_code in [200, 302]:
                    return True
    except Exception as e:
        print(f"  [Auto-Approve Warning]: Web resolution error: {e}")
    return False

def init_markdown_log():
    """Initializes the Markdown session log file with a clean header."""
    if not os.path.exists(MARKDOWN_LOG_FILE):
        with open(MARKDOWN_LOG_FILE, "w", encoding="utf-8") as f:
            f.write(f"# Deep Agent Interactive Test & Action Log\n")
            f.write(f"- **Session Date:** {datetime.datetime.now().isoformat()}\n")
            f.write(f"- **Target API:** `{DEEPAGENT_API_URL}`\n")
            f.write(f"- **Log JSONL:** `{os.path.basename(JSONL_LOG_FILE)}`\n\n")
            f.write(f"---\n\n")

def append_to_logs(entry: Dict[str, Any]):
    """Appends interaction details to both JSONL and Markdown log files."""
    with open(JSONL_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
        
    init_markdown_log()
    with open(MARKDOWN_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"### Interaction #{entry['interaction_id']} - {entry['timestamp']}\n\n")
        f.write(f"**User Request:**\n> {entry['user_prompt']}\n\n")
        f.write(f"**Execution Details:**\n")
        f.write(f"- **Status Code:** `{entry['http_status']}`\n")
        f.write(f"- **Latency:** `{entry['latency_seconds']:.2f}s`\n\n")
        
        steps = entry.get("intermediate_steps", [])
        if steps:
            f.write(f"**Agent Actions & Intermediate Steps ({len(steps)} executed):**\n\n")
            for idx, step in enumerate(steps, 1):
                step_type = step.get("step_type", "tool")
                
                if step_type == "subagent_delegation":
                    target = step.get("target_subagent", "subagent")
                    prompt = step.get("subagent_task_prompt", "")
                    f.write(f"#### Step {idx}: 🤖 Subagent Delegation -> `{target}`\n")
                    f.write(f"- **Task Prompt / Description:**\n> {prompt}\n\n")
                    f.write(f"- **Subagent Output / Report:**\n```text\n{step.get('tool_output')}\n```\n\n")
                elif step_type == "mcp_tool":
                    f.write(f"#### Step {idx}: 🛠️ MCP Tool Call -> `{step.get('tool_name')}`\n")
                    f.write(f"- **Arguments:** `{json.dumps(step.get('tool_args'))}`\n")
                    f.write(f"- **Raw Tool Output:**\n```text\n{step.get('tool_output')}\n```\n\n")
                elif step_type == "filesystem_tool":
                    f.write(f"#### Step {idx}: 📁 Filesystem Operation -> `{step.get('tool_name')}`\n")
                    f.write(f"- **Arguments:** `{json.dumps(step.get('tool_args'))}`\n")
                    f.write(f"- **Output:**\n```text\n{step.get('tool_output')}\n```\n\n")
                else:
                    f.write(f"#### Step {idx}: Tool Call -> `{step.get('tool_name')}`\n")
                    f.write(f"- **Arguments:** `{json.dumps(step.get('tool_args'))}`\n")
                    f.write(f"- **Output:**\n```text\n{step.get('tool_output')}\n```\n\n")
        else:
            f.write(f"**Agent Intermediate Actions:** None (Direct LLM Response)\n\n")

        f.write(f"**Assistant Final Response:**\n```text\n{entry['assistant_response']}\n```\n\n")
        
        if entry.get("db_hitl_record"):
            db = entry["db_hitl_record"]
            f.write(f"**🛡️ HITL PostgreSQL Audit DB Action:**\n")
            f.write(f"- **Record ID:** `{db.get('id')}`\n")
            f.write(f"- **Action Name:** `{db.get('action_name')}`\n")
            f.write(f"- **Action Summary:** `{db.get('action_summary')}`\n")
            f.write(f"- **DB Status:** `{db.get('status')}`\n")
            f.write(f"- **Requested At:** `{db.get('requested_at')}`\n")
            f.write(f"- **Resolved At:** `{db.get('resolved_at')}`\n\n")
        else:
            f.write(f"**🛡️ HITL Audit DB Action:** None (No authorization gate triggered)\n\n")
            
        f.write(f"---\n\n")

def print_step_summary(steps: list):
    """Prints a formatted summary of intermediate agent steps to the console."""
    if not steps:
        return
    print(f"\n--- [Agent Behavior & Action Trace ({len(steps)} steps)] ---")
    for idx, step in enumerate(steps, 1):
        step_type = step.get("step_type", "tool")
        if step_type == "subagent_delegation":
            target = step.get("target_subagent", "subagent")
            prompt = step.get("subagent_task_prompt", "")
            print(f"  [Step {idx}] 🤖 SUBAGENT DELEGATION -> '{target}'")
            print(f"    Task: {prompt[:120]}..." if len(prompt) > 120 else f"    Task: {prompt}")
            out_preview = str(step.get('tool_output', '')).strip().replace('\n', ' ')
            print(f"    Subagent Output: {out_preview[:160]}...")
        elif step_type == "mcp_tool":
            print(f"  [Step {idx}] 🛠️  MCP TOOL CALL -> '{step.get('tool_name')}'")
            print(f"    Args: {json.dumps(step.get('tool_args'))}")
            out_preview = str(step.get('tool_output', '')).strip().replace('\n', ' ')
            print(f"    Tool Output: {out_preview[:160]}...")
        elif step_type == "filesystem_tool":
            print(f"  [Step {idx}] 📁 FILESYSTEM ACTION -> '{step.get('tool_name')}'")
            print(f"    Args: {json.dumps(step.get('tool_args'))}")
            out_preview = str(step.get('tool_output', '')).strip().replace('\n', ' ')
            print(f"    Output: {out_preview[:160]}...")
        else:
            print(f"  [Step {idx}] ⚙️  TOOL CALL -> '{step.get('tool_name')}'")
            print(f"    Args: {json.dumps(step.get('tool_args'))}")
            out_preview = str(step.get('tool_output', '')).strip().replace('\n', ' ')
            print(f"    Output: {out_preview[:160]}...")

def send_agent_request(user_prompt: str, interaction_id: int, auto_approve_delay: int = 0) -> Dict[str, Any]:
    """Sends prompt to Deep Agent REST API, captures response, latency, MCP tool calls, and DB action state."""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepagent",
        "messages": [{"role": "user", "content": user_prompt}],
        "stream": False
    }

    db_before = query_latest_hitl_db_record()
    start_time = time.time()
    
    result_container = {}
    
    def post_request():
        try:
            resp = requests.post(DEEPAGENT_API_URL, headers=headers, json=payload, timeout=300)
            latency = time.time() - start_time
            result_container["http_status"] = resp.status_code
            result_container["latency_seconds"] = round(latency, 2)
            if resp.status_code == 200:
                data = resp.json()
                result_container["raw_response"] = data
                choices = data.get("choices", [])
                if choices:
                    result_container["assistant_response"] = choices[0].get("message", {}).get("content", "")
                result_container["intermediate_steps"] = data.get("intermediate_steps", [])
            else:
                result_container["assistant_response"] = f"HTTP Error {resp.status_code}: {resp.text}"
                result_container["intermediate_steps"] = []
        except Exception as e:
            latency = time.time() - start_time
            result_container["http_status"] = 500
            result_container["latency_seconds"] = round(latency, 2)
            result_container["assistant_response"] = f"Exception during request: {e}"
            result_container["intermediate_steps"] = []

    req_thread = threading.Thread(target=post_request)
    req_thread.start()

    detected_pending_id = None
    if auto_approve_delay > 0:
        print(f"\n[HITL Monitor]: Polling PostgreSQL DB for pending HITL authorization request...")
        for _ in range(30):
            if not req_thread.is_alive():
                break
            time.sleep(1.5)
            db_current = query_latest_hitl_db_record()
            if db_current and db_current.get("status") == "PENDING":
                if not db_before or db_before.get("id") != db_current.get("id"):
                    detected_pending_id = db_current.get("id")
                    print(f"\n[HITL Interception Detected!]: Request ID #{detected_pending_id} created for action '{db_current.get('action_name')}'.")
                    print(f"[Auto-Approval Timer]: Waiting {auto_approve_delay} seconds before granting approval...")
                    time.sleep(auto_approve_delay)
                    
                    print(f"[Auto-Approving]: Submitting decision 'GRANTED' to HITL Web Portal (:5001)...")
                    success = resolve_hitl_request_web(detected_pending_id)
                    if success:
                        print(f"✓ HITL Request #{detected_pending_id} successfully APPROVED (GRANTED)!")
                    else:
                        print(f"! Failed to submit web approval for Request #{detected_pending_id}")
                    break

    req_thread.join()

    db_after = query_latest_hitl_db_record()
    db_record = None
    if db_after and (not db_before or db_before.get("id") != db_after.get("id")):
        db_record = db_after

    entry = {
        "interaction_id": interaction_id,
        "timestamp": datetime.datetime.now().isoformat(),
        "user_prompt": user_prompt,
        "http_status": result_container.get("http_status", 500),
        "latency_seconds": result_container.get("latency_seconds", 0.0),
        "assistant_response": result_container.get("assistant_response", ""),
        "intermediate_steps": result_container.get("intermediate_steps", []),
        "raw_response": result_container.get("raw_response", {}),
        "db_hitl_record": db_record
    }

    append_to_logs(entry)
    return entry

def main():
    parser = argparse.ArgumentParser(description="Deep Agent Interaction & Action Logging Script")
    parser.add_argument("prompt", nargs="?", type=str, help="Optional user request prompt to execute directly")
    parser.add_argument("--auto-approve", type=int, default=0, help="Automatically grant HITL approval after N seconds of waiting")
    args = parser.parse_args()

    print("==========================================================================")
    print(" Deep Agent Interaction & Action Logger")
    print(f" Logs saved to: {MARKDOWN_LOG_FILE}")
    if args.auto_approve > 0:
        print(f" HITL Auto-Approval Mode: Enabled (Wait {args.auto_approve}s before approving)")
    print("==========================================================================")

    if args.prompt:
        # Single execution mode
        print(f"\n[Request] User: {args.prompt}")
        entry = send_agent_request(args.prompt, 1, auto_approve_delay=args.auto_approve)
        
        print_step_summary(entry.get("intermediate_steps", []))
        
        if entry.get("db_hitl_record"):
            db = entry["db_hitl_record"]
            print(f"\n--- [HITL Audit Record Logged] ---")
            print(f"  ID #{db['id']} | Action: '{db['action_name']}' | Status: {db['status']}")
            print(f"  Summary: {db['action_summary']}")

        print(f"\n[Assistant Summary ({entry['latency_seconds']}s | HTTP {entry['http_status']})]:")
        print(f"{entry['assistant_response']}\n")
        sys.exit(0)

    # Interactive CLI Shell Mode
    interaction_count = 0
    while True:
        try:
            user_input = input("\nEnter request (or 'exit' / 'quit'): ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["exit", "quit", "q"]:
                print("\nExiting session. Log saved to:", MARKDOWN_LOG_FILE)
                break
                
            interaction_count += 1
            print(f"\nProcessing Request #{interaction_count}...")
            entry = send_agent_request(user_input, interaction_count, auto_approve_delay=args.auto_approve)
            
            print_step_summary(entry.get("intermediate_steps", []))
            
            if entry.get("db_hitl_record"):
                db = entry["db_hitl_record"]
                print(f"\n--- [HITL Audit Record Logged] ---")
                print(f"  ID #{db['id']} | Action: '{db['action_name']}' | Status: {db['status']}")
                print(f"  Summary: {db['action_summary']}")

            print(f"\n[Assistant Response ({entry['latency_seconds']}s | HTTP {entry['http_status']})]:")
            print("--------------------------------------------------------------------------")
            print(entry['assistant_response'])
            print("--------------------------------------------------------------------------")
            print(f"\n✓ Logged to {os.path.basename(MARKDOWN_LOG_FILE)}")
            
        except KeyboardInterrupt:
            print("\nSession interrupted by user.")
            break

if __name__ == "__main__":
    main()
