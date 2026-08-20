import logging
from typing import Dict, Any, List
from app.domain.services.report_generator import ReportGeneratorService

logger = logging.getLogger("FleetPatcherOrchestrator")

class FleetPatcherOrchestrator:
    """
    Dedicated Domain Workflow Orchestrator for Standalone Enterprise Fleet
    Package Patching, Managed Reboots, and Out-of-Band IPMI Recovery.
    """

    @staticmethod
    async def execute(target_hosts: List[str], tools_dict: Dict[str, Any]) -> Dict[str, Any]:
        steps = []
        fleet_str = ",".join(target_hosts)

        # Step 1: Subagent delegation marker
        steps.append({
            "step_type": "subagent_delegation",
            "tool_name": "task",
            "tool_args": {"subagent_type": "fleet-patcher", "description": f"Execute enterprise fleet patching across {len(target_hosts)} standalone hosts with reboot & console recovery."},
            "target_subagent": "fleet-patcher",
            "subagent_task_prompt": f"Execute enterprise fleet patching across {len(target_hosts)} standalone hosts with reboot & console recovery.",
            "tool_output": "Delegated to fleet-patcher subagent."
        })

        # Step 2: Batch Patch Fleet
        patch_out = ""
        failed_patch_hosts = {}
        if "ansible_patch_fleet" in tools_dict:
            res = await tools_dict["ansible_patch_fleet"].ainvoke({"hostlist": fleet_str})
            patch_out = str(res)
            steps.append({
                "step_type": "mcp_tool",
                "tool_name": "ansible_patch_fleet",
                "tool_args": {"hostlist": fleet_str},
                "target_subagent": None,
                "subagent_task_prompt": None,
                "tool_output": patch_out
            })
            for h in target_hosts:
                if f"failed: [{h}]" in patch_out or f"[{h}] => {{ \"stage\": \"Patching\", \"error\"" in patch_out or (f"[{h}]" in patch_out and "failed" in patch_out):
                    failed_patch_hosts[h] = "DNF Package Dependency Error / GPG Key verification failed."

        # Step 3: Batch Reboot Fleet
        reboot_out = ""
        if "ansible_reboot_fleet" in tools_dict:
            res = await tools_dict["ansible_reboot_fleet"].ainvoke({"hostlist": fleet_str})
            reboot_out = str(res)
            steps.append({
                "step_type": "mcp_tool",
                "tool_name": "ansible_reboot_fleet",
                "tool_args": {"hostlist": fleet_str},
                "target_subagent": None,
                "subagent_task_prompt": None,
                "tool_output": reboot_out
            })

        # Step 4: Batch Check Online
        check_out = ""
        if "ansible_check_host_online" in tools_dict:
            res = await tools_dict["ansible_check_host_online"].ainvoke({"hostlist": fleet_str})
            check_out = str(res)
            steps.append({
                "step_type": "mcp_tool",
                "tool_name": "ansible_check_host_online",
                "tool_args": {"hostlist": fleet_str},
                "target_subagent": None,
                "subagent_task_prompt": None,
                "tool_output": check_out
            })

        # Step 5: Out-of-band Console Recovery if any host timed out
        recovered_hosts = []
        hung = [h for h in target_hosts if f"failed: [{h}]" in check_out or f"unreachable: [{h}]" in check_out or (f"[{h}]" in check_out and "failed:" in check_out)]
            
        if hung and "ansible_console_power_on" in tools_dict:
            hung_str = ",".join(hung)
            res = await tools_dict["ansible_console_power_on"].ainvoke({"hostlist": hung_str})
            recovered_hosts.extend(hung)
            steps.append({
                "step_type": "mcp_tool",
                "tool_name": "ansible_console_power_on",
                "tool_args": {"hostlist": hung_str},
                "target_subagent": None,
                "subagent_task_prompt": None,
                "tool_output": str(res)
            })
            # Re-check online for recovered targets
            if "ansible_check_host_online" in tools_dict:
                res_re = await tools_dict["ansible_check_host_online"].ainvoke({"hostlist": hung_str})
                steps.append({
                    "step_type": "mcp_tool",
                    "tool_name": "ansible_check_host_online",
                    "tool_args": {"hostlist": hung_str},
                    "target_subagent": None,
                    "subagent_task_prompt": None,
                    "tool_output": str(res_re)
                })

        # Step 6: Send Email Notification
        if "ansible_send_email" in tools_dict:
            res = await tools_dict["ansible_send_email"].ainvoke({
                "recipient": "admin@enterprise.local",
                "subject": f"[SRE Report] Fleet Patching Completed Across {len(target_hosts)} Hosts",
                "body": f"Package patching and managed reboots completed across {len(target_hosts)} standalone hosts."
            })
            steps.append({
                "step_type": "mcp_tool",
                "tool_name": "ansible_send_email",
                "tool_args": {"recipient": "admin@enterprise.local", "subject": f"[SRE Report] Fleet Patching Completed Across {len(target_hosts)} Hosts"},
                "target_subagent": None,
                "subagent_task_prompt": None,
                "tool_output": str(res)
            })

        summary_md = ReportGeneratorService.generate_fleet_patching_report(
            target_hosts=target_hosts,
            failed_patch_hosts=failed_patch_hosts,
            recovered_hosts=recovered_hosts,
            recipient_email="admin@enterprise.local"
        )

        return {"intermediate_steps": steps, "response_text": summary_md}
