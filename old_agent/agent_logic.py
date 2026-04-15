# /react-agent_service/agent_logic.py
import re
import os
import docker
import operator
import sqlite3
import json
import paramiko # Added for SSH client
import logging # Added logging
import requests # Added for check_website
import time # Added for monitoring
from functools import wraps # Added for decorator
from uuid import uuid4
from typing import TypedDict, Annotated, Sequence

from langchain_ollama import ChatOllama
from langchain_community.tools import tool
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.sqlite import SqliteSaver
from ansible_tool import run_ansible_job

# --- Configuration ---
OLLAMA_API_URL = os.getenv("OLLAMA_HOST", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")
CONTAINER_NAME = "linux-test-machine"
ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")

# --- Logging ---
logger = logging.getLogger(__name__)

# --- Monitoring Setup ---
monitoring_logger = logging.getLogger("monitoring")
monitoring_logger.setLevel(logging.INFO)
# Avoid adding multiple handlers if module is reloaded
if not monitoring_logger.handlers:
    monitor_handler = logging.FileHandler("/tmp/monitoring.log")
    monitor_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
    monitoring_logger.addHandler(monitor_handler)

def monitor_tool(func):
    """Decorator to log tool execution details to a monitoring file."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        tool_name = func.__name__
        start_time = time.time()
        status = "success"
        result = None
        
        try:
            result = func(*args, **kwargs)
            # Heuristic check for failure in string output
            if isinstance(result, str) and ("Failed" in result or "Error" in result):
                status = "failed"
        except Exception as e:
            result = str(e)
            status = "error"
            # Re-raise or return error string? Tools usually return string error.
            return f"Tool Execution Error: {str(e)}"
        
        duration = time.time() - start_time
        
        log_payload = {
            "tool": tool_name,
            "inputs": kwargs if kwargs else args, # Simplified input logging
            "status": status,
            "duration_seconds": round(duration, 4),
            "timestamp": start_time
        }
        
        monitoring_logger.info(json.dumps(log_payload))
        return result
    return wrapper

# ✅ UPDATED: Even stricter prompt to forbid any code block generation
SYSTEM_PROMPT = """You are a precise Linux assistant specialized in Red Hat Enterprise Linux (RHEL).

**Goal:** Autonomously resolve the user's request by executing commands.

**Rules:**
1.  **Chain Actions:** If a request requires multiple steps (e.g., "reboot then check uptime"), execute them one by one in a continuous loop. Do not stop until all steps are done.
2.  **Use Tools:** Always use the provided tools (`ansible_run_command`, etc.) to perform actions.
3.  **Hostname:** Always provide the `hostname` argument (default: 'linux-test-machine').
4.  **Package Management:** You are managing a RHEL/CentOS system. ALWAYS use `yum` or `dnf` for package installation/updates. NEVER use `apt` or `apt-get`.
5.  **Retries:** If a previous attempt failed, and the user asks to try again, YOU MUST CALL THE TOOL AGAIN. Do not give up. Do not just say you will do it.
6.  **Action Assurance:** If you say "I will..." or "Rebooting...", you MUST accompany that with a matching tool call. Text alone does nothing.
7.  **Final Response:** When you have completed all actions and no more tools are needed, you MUST output a final summary message explaining what was done. NEVER leave the conversation hanging without a final text response.

**STRICT PROHIBITIONS:**
*   **NEVER** output Markdown code blocks (e.g. ```bash, ```python, or just ```).
*   **NEVER** write out a tool call as text (e.g. do not write "ansible_run_command(...)").
*   **NEVER** explain how to use a tool.
*   **JUST CALL THE TOOL.**

Proceed autonomously.
"""

# --- Define the Agent State ---
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]

# --- Define the Agent's Tools ---
# docker_run_command has been removed, its mock functionality is now integrated into ansible_run_command for dev.

# Helper wrapper for production calls (to avoid repeating boilerplate)
def run_ansible_job_wrapper(template_name, extra_vars):
    try:
        from api import app, get_system_setting # Local import to avoid circular dependency
        with app.app_context():
            aap_host = get_system_setting('AAP_HOST')
            aap_token = get_system_setting('AAP_TOKEN')
        
        result = run_ansible_job(template_name=template_name, extra_vars=extra_vars, aap_host=aap_host, aap_token=aap_token)
        if result.get("status") == "successful":
             return f"Ansible Job Successful:\n{result.get('output', 'No output captured.')}"
        else:
             return f"Ansible Job Failed or Incomplete. Status: {result.get('status')}\nError: {result.get('error', 'Unknown error')}"
    except Exception as e:
        logger.error(f"Error executing Ansible job wrapper: {e}")
        return f"Error executing Ansible job: {str(e)}"

@tool
@monitor_tool
def check_website(url: str) -> str:
    """
    Checks the HTTP status code of a given URL to verify connectivity.
    Args:
        url (str): The full URL to check (e.g., https://google.com).
    Returns:
        str: The status code and reason, or an error message.
    """
    try:
        # Verify=False to allow testing internal sites with self-signed certs
        response = requests.get(url, timeout=10, verify=False)
        return f"HTTP Request to {url} completed.\nStatus Code: {response.status_code}\nReason: {response.reason}"
    except Exception as e:
        return f"HTTP Request Failed to {url}.\nError: {str(e)}"

@tool
@monitor_tool
def ansible_run_command(command: str, hostname: str) -> str:
    """
    Executes a shell command on a specific remote Linux system via Ansible or simulates in dev.
    In dev, this runs the command directly on linux-test-machine via SSH.
    Args:
        command (str): The shell command to execute.
        hostname (str): The target hostname or IP address (required).
    Returns:
        str: The output of the command.
    """
    if ENVIRONMENT != "prod":
        # SSH into linux-test-machine to simulate Ansible execution
        # In dev, we ignore the hostname argument and always connect to the test container
        # but we log it to simulate production behavior.
        logger.debug(f"ansible_run_command called for target host: {hostname}")
        
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            ssh_user = os.getenv("LINUX_TEST_USER", "root")
            ssh_password = os.getenv("LINUX_TEST_PASSWORD", "password") # Default password for testing

            ssh.connect('linux-test-machine', username=ssh_user, password=ssh_password, timeout=10)

            stdin, stdout, stderr = ssh.exec_command(command)
            out = stdout.read().decode().strip()
            err = stderr.read().decode().strip()
            ssh.close()

            # Simulate Ansible output format
            formatted_output = ""
            if out:
                formatted_output += f"stdout: {out}\n"
            if err:
                formatted_output += f"stderr: {err}\n"

            return f"""TASK [Run command] *******************************************************************\nchanged: [{hostname}] => {{\n    "cmd": "{command}",\n    {formatted_output.replace(chr(10), chr(10) + '    ').strip()}\n}}\n\nPLAY RECAP *********************************************************************\n{hostname}     : ok=1    changed=1    unreachable=0    failed={1 if err and not out else 0}    skipped=0    rescued=0    ignored=0"""

        except paramiko.AuthenticationException:
            msg = "ALERT: SSH Authentication Failed. Please check LINUX_TEST_USER/PASSWORD."
            logger.error(msg)
            return msg
        except paramiko.SSHException as e:
            msg = f"ALERT: SSH Connection Error to linux-test-machine: {str(e)}"
            logger.error(msg)
            return msg
        except Exception as e:
            logger.error(f"SSH Execution Error: {e}")
            return f"Failed to execute command via SSH on linux-test-machine: {str(e)}"

    # Production path (AAP integration)
    try:
        template_name = "Limited Run Any Command"
        extra_vars = {
            "hostlist": hostname, # Use the provided hostname instead of 'all'
            "agent_comand": command
        }
        
        result = run_ansible_job(template_name=template_name, extra_vars=extra_vars)
        
        if result.get("status") == "successful":
             return f"Ansible Job Successful:\n{result.get('output', 'No output captured.')}"
        else:
             return f"Ansible Job Failed or Incomplete. Status: {result.get('status')}\nError: {result.get('error', 'Unknown error')}"
             
    except Exception as e:
        logger.error(f"Production Ansible Error: {e}")
        return f"Error executing Ansible job: {str(e)}"

@tool
@monitor_tool
def ansible_reboot_host(hostname: str) -> str:
    """
    Reboots a SPECIFIC remote host using Ansible.
    Use this tool when you need to restart a single machine.
    Args:
        hostname (str): The hostname or IP of the target to reboot.
    Returns:
        str: The outcome of the reboot operation.
    """
    if ENVIRONMENT != "prod":
        # Enhanced mock logic
        if not hostname:
            return "Ansible Job Failed. Status: failed\nError: No hostname provided."

        return f"""TASK [Reboot host] ***************************************************************\nchanged: [{hostname}]

PLAY RECAP *********************************************************************
{hostname}                  : ok=1    changed=1    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0"""
    return run_ansible_job_wrapper("Reboot Host", {"hostname": hostname})

@tool
@monitor_tool
def ansible_expand_fs(hostname: str, mount_point: str, size_gb: int) -> str:
    """
    Expands a filesystem on a remote host (VMware/Physical) by adding disk or extending VG/LV.
    The Volume Group and Logical Volume are automatically discovered from the mount point.
    
    Args:
        hostname (str): The target hostname.
        mount_point (str): The mount point to expand (e.g., '/var/app_data').
        size_gb (int): The size in GB to add.
    Returns:
        str: The outcome of the filesystem expansion.
    """
    if ENVIRONMENT != "prod":
        return f"Ansible Job (Mock): Filesystem '{mount_point}' on '{hostname}' expanded by {size_gb}GB."
    
    return run_ansible_job_wrapper("Auto-Scale Red Hat XFS", {
        "hostname": hostname,
        "mount_point": mount_point,
        "size_gb": size_gb
    })

@tool
@monitor_tool
def ansible_fix_pcs(hostname: str, action: str, resource: str = "") -> str:
    """
    Fixes PCS cluster issues on a specific host using Ansible.
    
    Args:
        hostname (str): The target hostname (e.g., 'sys2').
        action (str): The PCS action to perform. Options: 'status', 'cleanup', 'start_node', 'unstandby'.
        resource (str, optional): The target resource to cleanup (e.g., 'p_fs_app'). Required for 'cleanup' action.
        
    Returns:
        str: The outcome of the PCS remediation operation.
    """
    if ENVIRONMENT != "prod":
        # Mock logic for dev
        return f"Ansible Job (Mock): PCS action '{action}' on '{hostname}' with resource '{resource}' completed successfully."
    
    return run_ansible_job_wrapper("PCS Cluster Remediation", {
        "hostname": hostname,
        "pcs_action": action,
        "target_resource": resource
    })

@tool
@monitor_tool
def ansible_install_package(hostname: str, package_name: str) -> str:
    """
    Installs a package on a remote host using DNF/YUM via Ansible.
    
    Args:
        hostname (str): The target hostname.
        package_name (str): The name of the package to install (e.g., 'git', 'vim').
    Returns:
        str: The outcome of the installation.
    """
    if ENVIRONMENT != "prod":
        return f"Ansible Job (Mock): Package '{package_name}' installed successfully on '{hostname}'."
    
    return run_ansible_job_wrapper("Install Package", {
        "hostname": hostname,
        "package_name": package_name
    })

# --- Set up the LangGraph Agent ---

# Global checkpointer setup (needs to be available for setup_agent and setup_external_agent)
# We try to initialize it lazily or handle the app context requirement if using Postgres
_global_checkpointer = None

def get_checkpointer():
    global _global_checkpointer
    if _global_checkpointer:
        return _global_checkpointer
        
    db_url = os.getenv("DATABASE_URL")
    if db_url and db_url.startswith("postgres"):
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg_pool import ConnectionPool
        # In a real app, we might want to manage the pool lifecycle better
        pool = ConnectionPool(conninfo=db_url, max_size=20, kwargs={"autocommit": True})
        _global_checkpointer = PostgresSaver(pool)
        if hasattr(_global_checkpointer, "setup"):
            _global_checkpointer.setup()
        print("🚀 Using PostgreSQL for Agent Memory (Lazy Init)")
    else:
        conn = sqlite3.connect("agent_memory.sqlite", check_same_thread=False)
        _global_checkpointer = SqliteSaver(conn)
        print("⚠️ Using SQLite for Agent Memory (Lazy Init)")
    return _global_checkpointer

# Initialize on module load if possible, or rely on functions calling get_checkpointer()
# For simplicity in this architecture, we'll initialize it here.
_global_checkpointer = get_checkpointer()


def apply_self_correction(response, messages, llm_with_tools):
    """
    Checks if the response is a text-only hallucination of an action and retries if so.
    Returns a dict with updated messages if corrected, or None.
    """
    # Self-Correction: Detect missed tool calls in action-oriented text
    if not hasattr(response, "tool_calls") or not response.tool_calls:
         # Basic keywords that imply action but weren't followed by a tool call
         action_keywords = ["rebooting", "installing", "running command", "executing"]
         content_lower = response.content.lower() if isinstance(response.content, str) else ""
         
         if any(k in content_lower for k in action_keywords):
             logger.warning("Detected text-only response for action. Retrying with hint.")
             retry_msg = SystemMessage(content="You responded with text only, but this request requires a Tool Call (e.g., ansible_reboot_host). Please generate the correct Tool Call now.")
             
             # Recursively invoke the model with the hint
             try:
                 retry_response = llm_with_tools.invoke(list(messages) + [response, retry_msg])
                 # Return the whole chain so the history reflects the correction
                 return {"messages": [response, retry_msg, retry_response]}
             except Exception as e:
                 logger.error(f"Retry failed: {e}")
                 # Fallthrough to original response if retry crashes
    return None

def setup_agent(): 
    llm = ChatOllama(model=OLLAMA_MODEL, base_url=OLLAMA_API_URL, temperature=0.0)

    if ENVIRONMENT == "prod":
        tools = [ansible_run_command, ansible_reboot_host, ansible_expand_fs, check_website, ansible_fix_pcs, ansible_install_package]
        logger.info("Running in PRODUCTION mode")
    else:
        # Enable Ansible tools in Dev for testing purposes (Mocked)
        tools = [ansible_run_command, ansible_reboot_host, ansible_expand_fs, check_website, ansible_fix_pcs, ansible_install_package] 
        logger.info("Running in DEVELOPMENT mode")

    llm_with_tools = llm.bind_tools(tools)

    def agent_node(state: AgentState):
        response = llm_with_tools.invoke(state["messages"])

        # Fallback for "brtc" or raw JSON command hallucination
        if isinstance(response.content, str) and '{"command":' in response.content and ("yum" in response.content or "dnf" in response.content or "apt" in response.content):
            try:
                match = re.search(r'(\{.*"command":.*?\})', response.content, re.DOTALL)
                if match:
                    data = json.loads(match.group(1))
                    if "command" in data:
                        tool_calls = [{
                            "name": "ansible_run_command",
                            "args": {
                                "command": data["command"],
                                "hostname": data.get("hostname", "linux-test-machine")
                            },
                            "id": str(uuid4())
                        }]
                        response = AIMessage(content="", tool_calls=tool_calls)
                        logger.info("Fixed malformed tool call from model.")
            except Exception as e:
                logger.warning(f"Failed to fix malformed tool call: {e}")

        # Robust parsing: Check if content looks like a tool call JSON, even without [TOOL_CALLS] prefix
        if isinstance(response.content, str) and (
            "[TOOL_CALLS]" in response.content or 
            '[{"name":' in response.content or 
            "[{'name':" in response.content
        ):
            # Try to find a JSON-like list
            match = re.search(r'(\[\s*\{.*?\}\s*\])', response.content, re.DOTALL)
            if match:
                try:
                    tool_call_json_str = match.group(1)
                    # Handle potential single quotes if model messed up
                    if "'" in tool_call_json_str and '"' not in tool_call_json_str:
                        tool_call_json_str = tool_call_json_str.replace("'", '"')
                        
                    tool_calls_data = json.loads(tool_call_json_str)

                    tool_calls = [
                        {
                            "name": tool_data["name"],
                            "args": tool_data["arguments"],
                            "id": str(uuid4())
                        }
                        for tool_data in tool_calls_data
                    ]

                    response = AIMessage(content="", tool_calls=tool_calls)
                except (json.JSONDecodeError, KeyError) as e:
                    logger.error(f"Failed to parse tool call: {e}")
                    pass
        
        # Use extracted logic for self-correction
        correction = apply_self_correction(response, state["messages"], llm_with_tools)
        if correction:
             return correction

        is_tool_call = hasattr(response, "tool_calls") and response.tool_calls
        content_str = str(response.content).strip() if response.content else ""
        if not content_str and not is_tool_call:
            response.content = "The requested task has been completed successfully."

        return {"messages": [response]}

    tool_node = ToolNode(tools)
    builder = StateGraph(AgentState)
    builder.add_node("agent", agent_node)
    builder.add_node("tool_node", tool_node)
    builder.add_edge(START, "agent")

    def has_tool_calls(state: AgentState):
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return END

    builder.add_conditional_edges("agent", has_tool_calls, {"tools": "tool_node", END: END})
    builder.add_edge("tool_node", "agent")

    return builder.compile(checkpointer=_global_checkpointer, interrupt_before=["tool_node"])


def setup_external_agent(recursion_limit: int = 3):
    """
    Creates a separate agent graph for external/background tasks.
    - Uses Ansible tool (Mocked in Dev, Real in Prod).
    - Has a configurable recursion limit.
    - Does NOT interrupt before tool execution (auto-executes).
    """
    llm = ChatOllama(model=OLLAMA_MODEL, base_url=OLLAMA_API_URL, temperature=0.0)
    
    # External agent always has access to Ansible tool (mocked or real)
    # It could also have docker if needed, but user asked for simulated ansible
    tools = [ansible_run_command, ansible_reboot_host, ansible_expand_fs, check_website, ansible_fix_pcs, ansible_install_package]
    
    llm_with_tools = llm.bind_tools(tools)

    def agent_node(state: AgentState):
        logger.debug(f"External agent_node invoked. Messages: {len(state['messages'])}")
        response = llm_with_tools.invoke(state["messages"])
        logger.debug(f"External agent_node response received.")
        
        # Fallback for "brtc"
        if isinstance(response.content, str) and '{"command":' in response.content and ("yum" in response.content or "dnf" in response.content):
             try:
                 match = re.search(r'(\{.*"command":.*?\})', response.content, re.DOTALL)
                 if match:
                     data = json.loads(match.group(1))
                     if "command" in data:
                         tool_calls = [{
                             "name": "ansible_run_command",
                             "args": {
                                 "command": data["command"],
                                 "hostname": data.get("hostname", "linux-test-machine")
                             },
                             "id": str(uuid4())
                         }]
                         response = AIMessage(content="", tool_calls=tool_calls)
             except: pass

        # (Parsing logic same as above)
        if isinstance(response.content, str) and ('[{"name":' in response.content or "[{'name':" in response.content):
             match = re.search(r'(\[\s*\{.*?\}\s*\])', response.content, re.DOTALL)
             if match:
                 try:
                     tool_data = json.loads(match.group(1).replace("'", '"'))
                     tool_calls = [{"name": t["name"], "args": t["arguments"], "id": str(uuid4())} for t in tool_data]
                     response = AIMessage(content="", tool_calls=tool_calls)
                 except: pass

        is_tool_call = hasattr(response, "tool_calls") and response.tool_calls
        content_str = str(response.content).strip() if response.content else ""
        if not content_str and not is_tool_call:
            response.content = "The requested task has been completed successfully."

        return {"messages": [response]}

    tool_node = ToolNode(tools)
    builder = StateGraph(AgentState)
    builder.add_node("agent", agent_node)
    builder.add_node("tool_node", tool_node)
    builder.add_edge(START, "agent")

    def has_tool_calls(state: AgentState):
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return END

    builder.add_conditional_edges("agent", has_tool_calls, {"tools": "tool_node", END: END})
    builder.add_edge("tool_node", "agent")

    # Reuse memory backend logic
    return builder.compile(checkpointer=_global_checkpointer)
