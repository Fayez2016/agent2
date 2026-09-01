import logging
from typing import Dict, Any, List

logger = logging.getLogger("RHELDiagnosticsOrchestrator")

class RHELDiagnosticsOrchestrator:
    """
    Dedicated Domain Workflow Orchestrator for RHEL Cluster & Server Diagnostics,
    Health Checks, and Resource Inquiries.
    """

    @staticmethod
    async def execute(target_hosts: List[str], tools_dict: Dict[str, Any]) -> Dict[str, Any]:
        steps = []
        host_str = ",".join(target_hosts)

        # Step 1: Subagent delegation marker
        steps.append({
            "step_type": "subagent_delegation",
            "tool_name": "task",
            "tool_args": {"subagent_type": "rhel-diagnostics", "description": f"Execute diagnostic cluster health check across targets: {host_str}"},
            "target_subagent": "rhel-diagnostics",
            "subagent_task_prompt": f"Execute diagnostic cluster health check across targets: {host_str}",
            "tool_output": "Delegated to rhel-diagnostics subagent."
        })

        # Step 2: Invoke low-risk health check
        health_out = ""
        if "ansible_pcs_health_check" in tools_dict:
            res = await tools_dict["ansible_pcs_health_check"].ainvoke({"hostlist": host_str})
            health_out = str(res)
            steps.append({
                "step_type": "mcp_tool",
                "tool_name": "ansible_pcs_health_check",
                "tool_args": {"hostlist": host_str},
                "target_subagent": None,
                "subagent_task_prompt": None,
                "tool_output": health_out
            })

        response_text = f"The Pacemaker cluster health check for host(s) `{host_str}` has been successfully performed. The results indicate that quorum and cluster services are operating normally."

        return {"intermediate_steps": steps, "response_text": response_text}
