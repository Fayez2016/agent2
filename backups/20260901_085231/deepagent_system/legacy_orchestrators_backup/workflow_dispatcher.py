import logging
from typing import Dict, Any, List
from app.domain.services.entity_extractor import EntityExtractorService
from app.domain.orchestrators.ha_rolling_update import HARollingUpdateOrchestrator
from app.domain.orchestrators.fleet_patcher import FleetPatcherOrchestrator
from app.domain.orchestrators.rhel_diagnostics import RHELDiagnosticsOrchestrator
from app.domain.orchestrators.single_host_ops import SingleHostOperationsOrchestrator

logger = logging.getLogger("WorkflowDispatcher")

class WorkflowDispatcher:
    """
    Domain Orchestrator Dispatcher:
    Routes incoming user requests to the appropriate domain workflow orchestrator
    (HA Rolling Update, Standalone Fleet Patching, Diagnostics, or Single Host Operations)
    based on decoupled Entity & Intent analysis.
    """

    @staticmethod
    async def dispatch(user_query: str, tools_dict: Dict[str, Any]) -> Dict[str, Any]:
        entities = EntityExtractorService.extract_entities(user_query)

        # 1. Standalone Fleet Patching
        if entities["is_fleet_patching"]:
            target_hosts = entities["hosts"] if entities["hosts"] else entities["all_entities"]
            if not target_hosts:
                target_hosts = ["srv-prod-01", "srv-prod-02", "srv-prod-03"]
            logger.info(f"Dispatching to FleetPatcherOrchestrator ({len(target_hosts)} hosts)...")
            return await FleetPatcherOrchestrator.execute(target_hosts=target_hosts, tools_dict=tools_dict)

        # 2. Red Hat HA Multi-Cluster Rolling Update (SOP 2059253)
        elif entities["is_ha_rolling_update"]:
            target_clusters = entities["clusters"] if entities["clusters"] else (entities["hosts"] if entities["hosts"] else ["ha-cluster-01"])
            logger.info(f"Dispatching to HARollingUpdateOrchestrator ({len(target_clusters)} clusters)...")
            return await HARollingUpdateOrchestrator.execute(target_clusters=target_clusters, tools_dict=tools_dict)

        # 3. Cluster & Host Health Diagnostics
        elif entities["is_diagnostics"] or ("health" in user_query.lower() and "patch" not in user_query.lower()):
            target_hosts = entities["hosts"] if entities["hosts"] else (entities["clusters"] if entities["clusters"] else ["rhel-prod-01"])
            logger.info(f"Dispatching to RHELDiagnosticsOrchestrator ({len(target_hosts)} hosts)...")
            return await RHELDiagnosticsOrchestrator.execute(target_hosts=target_hosts, tools_dict=tools_dict)

        # 4. Direct Single-Host Operations (Reboot Host, Check Host, etc.)
        direct_res = await SingleHostOperationsOrchestrator.execute(
            user_query=user_query,
            target_hosts=entities["hosts"],
            tools_dict=tools_dict
        )
        if direct_res:
            return direct_res

        return None
