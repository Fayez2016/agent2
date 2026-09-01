#!/usr/bin/env python3
"""
Master End-to-End Verification Test Runner for Deep Agent System
Executes all regression, domain, unit, and randomized dynamic scenario test suites in sequence.
"""

import sys
import subprocess
import time

TEST_SUITES = [
    {
        "name": "Phase 1: SOP FastMCP Server (:8001) & MultiServerMCPClient",
        "cmd": ["python3", "/home/fayez/agent2/deepagent_system/tests/test_phase1_sop_mcp.py"]
    },
    {
        "name": "Phase 2: Domain Services (Entity Extractor & Report Generator)",
        "cmd": ["python3", "/home/fayez/agent2/deepagent_system/tests/test_phase2_domain_services.py"],
        "env_pythonpath": "/home/fayez/agent2/deepagent_system"
    },
    {
        "name": "Phase 3: Core API, HITL Gate, Persistence & 8-Stage E2E",
        "cmd": ["python3", "/home/fayez/agent2/deepagent_system/run_deepagent_tests.py"]
    },
    {
        "name": "Phase 4: Randomized Dynamic HA & Fleet Scenarios (5 Cases)",
        "cmd": ["python3", "/home/fayez/agent2/deepagent_system/tests/test_randomized_dynamic_scenarios.py"]
    },
    {
        "name": "Phase 4: Multi-Run Dynamic HA Verification (3 Distinct Runs)",
        "cmd": ["python3", "/home/fayez/agent2/deepagent_system/tests/test_ha_subagent_multiruns.py"]
    },
    {
        "name": "Phase 4: Multi-Run Dynamic Fleet Verification (3 Distinct Runs)",
        "cmd": ["python3", "/home/fayez/agent2/deepagent_system/tests/test_fleet_subagent_multiruns.py"]
    },
    {
        "name": "Phase 4: SRE Failure, Resource Group & Action Items Reporting",
        "cmd": ["python3", "/home/fayez/agent2/deepagent_system/tests/test_error_and_action_reporting.py"]
    }
]

def main():
    print("==========================================================================")
    print(" 🚀 DEEP AGENT MASTER VERIFICATION TEST HARNESS (ALL PHASES)")
    print("==========================================================================")
    
    total_start = time.time()
    passed_count = 0
    failed_suites = []

    for idx, suite in enumerate(TEST_SUITES, 1):
        print(f"\n[{idx}/{len(TEST_SUITES)}] Running: {suite['name']}...")
        start_time = time.time()
        
        import os
        env = os.environ.copy()
        if "env_pythonpath" in suite:
            env["PYTHONPATH"] = suite["env_pythonpath"]
            
        try:
            res = subprocess.run(suite["cmd"], env=env, text=True, capture_output=True)
            elapsed = time.time() - start_time
            if res.returncode == 0:
                print(f"  ✓ PASSED in {elapsed:.1f}s")
                passed_count += 1
            else:
                print(f"  ✗ FAILED in {elapsed:.1f}s (Exit code: {res.returncode})")
                print("--- Output ---")
                print(res.stdout)
                print(res.stderr)
                failed_suites.append(suite["name"])
        except Exception as e:
            elapsed = time.time() - start_time
            print(f"  ✗ EXCEPTION in {elapsed:.1f}s: {e}")
            failed_suites.append(suite["name"])

    total_elapsed = time.time() - total_start
    print("\n==========================================================================")
    print(f" VERIFICATION SUMMARY: {passed_count}/{len(TEST_SUITES)} Suites Passed in {total_elapsed:.1f}s")
    print("==========================================================================")

    if failed_suites:
        print("Failed test suites:")
        for f in failed_suites:
            print(f" - {f}")
        sys.exit(1)
    else:
        print("🎉 ALL TEST SUITES PASSED WITH 100% SUCCESS RATE!")
        sys.exit(0)

if __name__ == "__main__":
    main()
