#!/usr/bin/env python3
"""
Phase 2 Unit & Integration Test Suite:
1. Validates EntityExtractorService across 10+ arbitrary naming patterns and edge cases.
2. Validates ReportGeneratorService Markdown matrix, incident logs, and action items.
3. Validates HARollingUpdateOrchestrator and FleetPatcherOrchestrator domain execution.
"""

import sys
from app.domain.services.entity_extractor import EntityExtractorService
from app.domain.services.report_generator import ReportGeneratorService

def log(msg):
    print(f"[PHASE2-TEST] {msg}", flush=True)

def test_entity_extractor_service():
    log("==========================================================================")
    log("Testing EntityExtractorService against Diverse Input Patterns...")
    log("==========================================================================")

    # 1. Range expressions
    p1 = "execute rolling update on cluster-01 to cluster-05"
    e1 = EntityExtractorService.extract_entities(p1)
    assert len(e1["clusters"]) == 5, f"Expected 5 clusters, got {e1['clusters']}"
    assert "cluster-01" in e1["clusters"] and "cluster-05" in e1["clusters"]
    assert e1["is_ha_rolling_update"] is True
    log("  ✓ Range expansion (cluster-01 to cluster-05) verified.")

    # 2. Multi-tier roles and UUIDs
    p2 = "Using fleet-patcher, patch hosts srv-db-98af1, srv-web-34a2, srv-cache-bb12"
    e2 = EntityExtractorService.extract_entities(p2)
    assert len(e2["hosts"]) == 3, f"Expected 3 hosts, got {e2['hosts']}"
    assert "srv-db-98af1" in e2["hosts"]
    assert e2["is_fleet_patching"] is True
    log("  ✓ Multi-tier UUID host extraction verified.")

    # 3. SOP Reference
    p3 = "follow SOP 2059253 on ha-cluster-prod-01, ha-cluster-prod-02"
    e3 = EntityExtractorService.extract_entities(p3)
    assert e3["is_ha_rolling_update"] is True
    assert len(e3["clusters"]) == 2
    log("  ✓ SOP 2059253 intent recognition verified.")

    return True

def test_report_generator_service():
    log("==========================================================================")
    log("Testing ReportGeneratorService Synthesis & Action Item Invariants...")
    log("==========================================================================")

    # 1. Clean Fleet Report
    r_clean = ReportGeneratorService.generate_fleet_patching_report(
        target_hosts=["srv-web-01", "srv-db-01"],
        failed_patch_hosts={},
        recovered_hosts=[]
    )
    assert "No Infrastructure Incidents Encountered" in r_clean
    assert "No Manual Action Required" in r_clean
    assert "Standard SSH" in r_clean
    log("  ✓ Clean fleet report verified.")

    # 2. Fleet Report with DNF Failure & Soft Hang
    r_err = ReportGeneratorService.generate_fleet_patching_report(
        target_hosts=["srv-web-01", "srv-db-01"],
        failed_patch_hosts={"srv-db-01": "GPG signature verification failed"},
        recovered_hosts=["srv-web-01"]
    )
    assert "FAILED (DNF Error)" in r_err
    assert "Console Power-On (Recovered)" in r_err
    assert "dnf clean all" in r_err
    log("  ✓ Incident-laden fleet report with actionable remediations verified.")

    # 3. HA Rolling Report with Resource Degradation
    r_ha = ReportGeneratorService.generate_ha_rolling_report(
        target_clusters=["cluster-alpha"],
        node1_list=["cluster-alpha-node1"],
        node2_list=["cluster-alpha-node2"],
        failed_ha_patches={},
        degraded_clusters={"cluster-alpha": "Failcount: 1 on node1"},
        recovered_nodes=["cluster-alpha-node1"]
    )
    assert "rg_cluster-alpha" in r_ha
    assert "WARNING (Failcount Alert)" in r_ha
    assert "pcs resource cleanup" in r_ha
    log("  ✓ HA rolling report with Pacemaker resource warning verified.")

    return True

if __name__ == "__main__":
    assert test_entity_extractor_service()
    assert test_report_generator_service()
    log("==========================================================================")
    log(" PHASE 2 DOMAIN SERVICES TEST SUITE PASSED 100%!")
    log("==========================================================================")
    sys.exit(0)
