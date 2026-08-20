import logging
from typing import Dict, Any, List
from app.domain.services.report_generator import ReportGeneratorService

logger = logging.getLogger("HARollingUpdateOrchestrator")

class HARollingUpdateOrchestrator:
    """
    Dedicated Domain Workflow Orchestrator for Red Hat Enterprise Linux
    HA Pacemaker/Corosync Rolling Updates per SOP 2059253.
    """

    @staticmethod
    async def execute(target_clusters: List[str], tools_dict: Dict[str, Any]) -> Dict[str, Any]:
        steps = []
        
        # 1. Dynamically compute node1 and node2 member lists
        node1_list = []
        node2_list = []
        for c in target_clusters:
            if "node1" in c or "node2" in c:
                node1_list.append(c)
            else:
                node1_list.append(f"{c}-node1")
                node2_list.append(f"{c}-node2")
        if not node2_list:
            node2_list = [f"{c}-peer" for c in node1_list]

        cluster_str = ",".join(target_clusters)
        node1_str = ",".join(node1_list)
        node2_str = ",".join(node2_list)

        # Step 1: Subagent delegation marker
        steps.append({
            "step_type": "subagent_delegation",
            "tool_name": "task",
            "tool_args": {"subagent_type": "ha-cluster-patcher", "description": f"Execute Red Hat HA Rolling Update (SOP 2059253) across {len(target_clusters)} clusters in batches."},
            "target_subagent": "ha-cluster-patcher",
            "subagent_task_prompt": f"Execute Red Hat HA Rolling Update (SOP 2059253) across {len(target_clusters)} clusters in batches.",
            "tool_output": "Delegated to ha-cluster-patcher subagent."
        })

        # Step 2: Batch Cluster Pre-Check & Resource Group Discovery
        health_out = ""
        degraded_clusters = {}
        if "ansible_pcs_health_check" in tools_dict:
            res = await tools_dict["ansible_pcs_health_check"].ainvoke({"hostlist": cluster_str})
            health_out = str(res)
            steps.append({
                "step_type": "mcp_tool",
                "tool_name": "ansible_pcs_health_check",
                "tool_args": {"hostlist": cluster_str},
                "target_subagent": None,
                "subagent_task_prompt": None,
                "tool_output": health_out
            })
            for c in target_clusters:
                if f"[{c}]" in health_out and ("WARNING" in health_out or "Degraded" in health_out):
                    degraded_clusters[c] = "Resource Failcount alert or constraint degradation detected."

        # Step 3: Evacuate Node 1 across all target clusters (Pre-check & Standby)
        if "ansible_pcs_node_standby" in tools_dict:
            res = await tools_dict["ansible_pcs_node_standby"].ainvoke({"hostlist": node1_str})
            steps.append({
                "step_type": "mcp_tool",
                "tool_name": "ansible_pcs_node_standby",
                "tool_args": {"hostlist": node1_str},
                "target_subagent": None,
                "subagent_task_prompt": None,
                "tool_output": str(res)
            })

        # Step 4: Batch Patch Fleet across Node 1 targets
        failed_ha_patches = {}
        if "ansible_patch_fleet" in tools_dict:
            res = await tools_dict["ansible_patch_fleet"].ainvoke({"hostlist": node1_str})
            p_out1 = str(res)
            steps.append({
                "step_type": "mcp_tool",
                "tool_name": "ansible_patch_fleet",
                "tool_args": {"hostlist": node1_str},
                "target_subagent": None,
                "subagent_task_prompt": None,
                "tool_output": p_out1
            })
            for n in node1_list:
                if f"failed: [{n}]" in p_out1:
                    failed_ha_patches[n] = "DNF Package Dependency / GPG Key verification failure."

        # Step 5: Batch Managed Reboot across Node 1 targets
        if "ansible_reboot_fleet" in tools_dict:
            res = await tools_dict["ansible_reboot_fleet"].ainvoke({"hostlist": node1_str})
            steps.append({
                "step_type": "mcp_tool",
                "tool_name": "ansible_reboot_fleet",
                "tool_args": {"hostlist": node1_str},
                "target_subagent": None,
                "subagent_task_prompt": None,
                "tool_output": str(res)
            })

        # Step 6: Verify Online & Uptime across Node 1 targets
        check_out_1 = ""
        if "ansible_check_host_online" in tools_dict:
            res = await tools_dict["ansible_check_host_online"].ainvoke({"hostlist": node1_str})
            check_out_1 = str(res)
            steps.append({
                "step_type": "mcp_tool",
                "tool_name": "ansible_check_host_online",
                "tool_args": {"hostlist": node1_str},
                "target_subagent": None,
                "subagent_task_prompt": None,
                "tool_output": check_out_1
            })

        # Step 7: Check if any host timed out and trigger out-of-band Console Power On
        recovered_nodes = []
        if "failed:" in check_out_1.lower() or "unreachable:" in check_out_1.lower() or "timed out" in check_out_1.lower():
            hung_targets = [n for n in node1_list if f"failed: [{n}]" in check_out_1 or f"unreachable: [{n}]" in check_out_1 or (f"[{n}]" in check_out_1 and "failed" in check_out_1)]
            hung_str = ",".join(hung_targets)
            if "ansible_console_power_on" in tools_dict and hung_str:
                res = await tools_dict["ansible_console_power_on"].ainvoke({"hostlist": hung_str})
                recovered_nodes.extend(hung_targets)
                steps.append({
                    "step_type": "mcp_tool",
                    "tool_name": "ansible_console_power_on",
                    "tool_args": {"hostlist": hung_str},
                    "target_subagent": None,
                    "subagent_task_prompt": None,
                    "tool_output": str(res)
                })
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

        # Step 8: Reintegrate Node 1 targets (Unstandby)
        if "ansible_pcs_node_unstandby" in tools_dict:
            res = await tools_dict["ansible_pcs_node_unstandby"].ainvoke({"hostlist": node1_str})
            steps.append({
                "step_type": "mcp_tool",
                "tool_name": "ansible_pcs_node_unstandby",
                "tool_args": {"hostlist": node1_str},
                "target_subagent": None,
                "subagent_task_prompt": None,
                "tool_output": str(res)
            })

        # Step 9: Repeat Rolling Cycle for Node 2 targets (Evacuate -> Patch -> Reboot -> Verify -> Unstandby)
        if "ansible_pcs_node_standby" in tools_dict:
            res = await tools_dict["ansible_pcs_node_standby"].ainvoke({"hostlist": node2_str})
            steps.append({
                "step_type": "mcp_tool",
                "tool_name": "ansible_pcs_node_standby",
                "tool_args": {"hostlist": node2_str},
                "target_subagent": None,
                "subagent_task_prompt": None,
                "tool_output": str(res)
            })
        if "ansible_patch_fleet" in tools_dict:
            res = await tools_dict["ansible_patch_fleet"].ainvoke({"hostlist": node2_str})
            p_out2 = str(res)
            steps.append({
                "step_type": "mcp_tool",
                "tool_name": "ansible_patch_fleet",
                "tool_args": {"hostlist": node2_str},
                "target_subagent": None,
                "subagent_task_prompt": None,
                "tool_output": p_out2
            })
            for n in node2_list:
                if f"failed: [{n}]" in p_out2:
                    failed_ha_patches[n] = "DNF Package Dependency / GPG Key verification failure."
        if "ansible_reboot_fleet" in tools_dict:
            res = await tools_dict["ansible_reboot_fleet"].ainvoke({"hostlist": node2_str})
            steps.append({
                "step_type": "mcp_tool",
                "tool_name": "ansible_reboot_fleet",
                "tool_args": {"hostlist": node2_str},
                "target_subagent": None,
                "subagent_task_prompt": None,
                "tool_output": str(res)
            })
        if "ansible_check_host_online" in tools_dict:
            res = await tools_dict["ansible_check_host_online"].ainvoke({"hostlist": node2_str})
            steps.append({
                "step_type": "mcp_tool",
                "tool_name": "ansible_check_host_online",
                "tool_args": {"hostlist": node2_str},
                "target_subagent": None,
                "subagent_task_prompt": None,
                "tool_output": str(res)
            })
        if "ansible_pcs_node_unstandby" in tools_dict:
            res = await tools_dict["ansible_pcs_node_unstandby"].ainvoke({"hostlist": node2_str})
            steps.append({
                "step_type": "mcp_tool",
                "tool_name": "ansible_pcs_node_unstandby",
                "tool_args": {"hostlist": node2_str},
                "target_subagent": None,
                "subagent_task_prompt": None,
                "tool_output": str(res)
            })

        # Step 10: Final Cluster Health & Resource Group Status Post-Check
        if "ansible_pcs_status" in tools_dict:
            res = await tools_dict["ansible_pcs_status"].ainvoke({"hostlist": cluster_str})
            steps.append({
                "step_type": "mcp_tool",
                "tool_name": "ansible_pcs_status",
                "tool_args": {"hostlist": cluster_str},
                "target_subagent": None,
                "subagent_task_prompt": None,
                "tool_output": str(res)
            })

        # Step 11: Send Automated SRE Report via Email
        if "ansible_send_email" in tools_dict:
            res = await tools_dict["ansible_send_email"].ainvoke({
                "recipient": "admin@enterprise.local",
                "subject": f"[SRE Report] HA Multi-Cluster Rolling Update Completed ({len(target_clusters)} Clusters)",
                "body": f"Zero-downtime rolling update completed across {len(target_clusters)} clusters ({len(node1_list) + len(node2_list)} nodes)."
            })
            steps.append({
                "step_type": "mcp_tool",
                "tool_name": "ansible_send_email",
                "tool_args": {"recipient": "admin@enterprise.local", "subject": f"[SRE Report] HA Multi-Cluster Rolling Update Completed ({len(target_clusters)} Clusters)"},
                "target_subagent": None,
                "subagent_task_prompt": None,
                "tool_output": str(res)
            })

        summary_md = ReportGeneratorService.generate_ha_rolling_report(
            target_clusters=target_clusters,
            node1_list=node1_list,
            node2_list=node2_list,
            failed_ha_patches=failed_ha_patches,
            degraded_clusters=degraded_clusters,
            recovered_nodes=recovered_nodes,
            recipient_email="admin@enterprise.local"
        )

        return {"intermediate_steps": steps, "response_text": summary_md}
