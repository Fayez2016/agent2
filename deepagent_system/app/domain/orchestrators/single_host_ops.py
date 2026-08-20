import logging
from typing import Dict, Any, List

logger = logging.getLogger("SingleHostOperationsOrchestrator")

class SingleHostOperationsOrchestrator:
    """
    Domain Orchestrator for direct, single-host or ad-hoc lifecycle operations
    such as standalone host reboot, package install, filesystem expansion, etc.
    """

    @staticmethod
    async def execute(user_query: str, target_hosts: List[str], tools_dict: Dict[str, Any]) -> Dict[str, Any]:
        steps = []
        host_target = target_hosts[0] if target_hosts else "rhel-prod-01"
        clean_q = user_query.lower()

        # 1. Single Host Reboot
        if "reboot" in clean_q:
            if "ansible_reboot_host" in tools_dict:
                res = await tools_dict["ansible_reboot_host"].ainvoke({"hostname": host_target})
                steps.append({
                    "step_type": "mcp_tool",
                    "tool_name": "ansible_reboot_host",
                    "tool_args": {"hostname": host_target},
                    "target_subagent": None,
                    "subagent_task_prompt": None,
                    "tool_output": str(res)
                })
                response_text = f"The host `{host_target}` has been scheduled for reboot. Output: {res}"
                return {"intermediate_steps": steps, "response_text": response_text}

        # 2. Single Host Online Check
        if "online" in clean_q or "ping" in clean_q:
            if "ansible_check_host_online" in tools_dict:
                res = await tools_dict["ansible_check_host_online"].ainvoke({"hostlist": host_target})
                steps.append({
                    "step_type": "mcp_tool",
                    "tool_name": "ansible_check_host_online",
                    "tool_args": {"hostlist": host_target},
                    "target_subagent": None,
                    "subagent_task_prompt": None,
                    "tool_output": str(res)
                })
                return {"intermediate_steps": steps, "response_text": f"Status check for `{host_target}`: {res}"}

        return None
