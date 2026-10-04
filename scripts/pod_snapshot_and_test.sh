#!/usr/bin/env bash
# ==============================================================================
# Script: pod_snapshot_and_test.sh
# Purpose: Instant container snapshotting, smoke testing, and rollback.
# Usage:
#   ./pod_snapshot_and_test.sh snapshot [label]   -> Take backup
#   ./pod_snapshot_and_test.sh test               -> Run 5-point smoke test
#   ./pod_snapshot_and_test.sh rollback [label]   -> Restore from backup
#   ./pod_snapshot_and_test.sh list               -> List backups
# ==============================================================================
set -o pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

CRITICAL_CONTAINERS=(
    "deepagent-service"
    "deepagent-proxy"
    "deepagent-webui"
    "deepagent-ansible-mcp"
    "deepagent-sop-mcp"
)

run_smoke_test() {
    echo -e "\n${BLUE}====================================================${NC}"
    echo -e "${YELLOW}>>> Running DeepAgent Smoke Test...${NC}"
    echo -e "${BLUE}====================================================${NC}"

    local errors=0

    echo -n " [1/5] Checking container states ... "
    for c in "${CRITICAL_CONTAINERS[@]}"; do
        status=$(podman inspect -f '{{.State.Status}}' "$c" 2>/dev/null || echo "down")
        if [ "$status" != "running" ]; then
            echo -e "${RED}FAILED${NC} ($c is $status)"
            return 1
        fi
    done
    echo -e "${GREEN}PASS (All 5 containers running)${NC}"

    echo -n " [2/5] Verifying deepagent-service Python imports ... "
    import_err=$(podman exec -i deepagent-service python3 -c "import app.agent_engine, app.main; print('OK')" 2>&1)
    if [[ "$import_err" =~ "OK" ]]; then
        echo -e "${GREEN}PASS${NC}"
    else
        echo -e "${RED}FAILED${NC} ($import_err)"
        errors=$((errors + 1))
    fi

    echo -n " [3/5] Checking FastMCP listeners (Ports 8000 & 8001) ... "
    mcp_test=$(podman exec -i deepagent-service python3 -c "
import urllib.request, urllib.error
for p in [8000, 8001]:
    try:
        req = urllib.request.Request(f'http://127.0.0.1:{p}/mcp', headers={'Accept': 'application/json, text/event-stream'})
        with urllib.request.urlopen(req, timeout=3) as r: pass
    except urllib.error.HTTPError as e:
        if e.code not in (400, 200, 406): raise Exception(f'Port {p} code {e.code}')
    except Exception as e:
        raise Exception(f'Port {p} failed: {e}')
print('OK')
" 2>&1)
    if [[ "$mcp_test" =~ "OK" ]]; then
        echo -e "${GREEN}PASS${NC}"
    else
        echo -e "${RED}FAILED${NC} ($mcp_test)"
        errors=$((errors + 1))
    fi

    echo -n " [4/5] Checking internal API backend (Port 8642) ... "
    svc_test=$(podman exec -i deepagent-service python3 -c "
import urllib.request
with urllib.request.urlopen('http://127.0.0.1:8642/health', timeout=3) as r:
    print('OK' if r.status == 200 else 'FAIL')
" 2>/dev/null || echo "FAIL")
    if [ "$svc_test" == "OK" ]; then
        echo -e "${GREEN}PASS${NC}"
    else
        echo -e "${RED}FAILED (Port 8642 not responding 200)${NC}"
        errors=$((errors + 1))
    fi

    echo -n " [5/5] Checking External HTTPS Endpoint (Port 8443) ... "
    http_code=$(curl -k -s -o /dev/null -w "%{http_code}" https://127.0.0.1:8443/health 2>/dev/null || echo "000")
    if [ "$http_code" == "200" ]; then
        echo -e "${GREEN}PASS (HTTP 200 OK)${NC}"
    else
        echo -e "${RED}FAILED (HTTP $http_code)${NC}"
        errors=$((errors + 1))
    fi

    echo -e "${BLUE}====================================================${NC}"
    if [ $errors -eq 0 ]; then
        echo -e "${GREEN}🎉 SMOKE TEST PASSED: System is completely healthy.${NC}"
        return 0
    else
        echo -e "${RED}❌ SMOKE TEST FAILED with $errors error(s).${NC}"
        return 1
    fi
}

create_snapshot() {
    local label="${1:-$(date +%Y%m%d_%H%M%S)}"
    echo -e "\n${BLUE}====================================================${NC}"
    echo -e "${YELLOW}>>> Creating Snapshot: [backup-${label}]...${NC}"
    echo -e "${BLUE}====================================================${NC}"

    for c in "${CRITICAL_CONTAINERS[@]}"; do
        local img_tag="localhost/${c}:backup-${label}"
        echo -n "  📸 Snapshotting $c -> $img_tag ... "
        podman commit "$c" "$img_tag" >/dev/null
        echo -e "${GREEN}✓ Done${NC}"
    done

    mkdir -p "$HOME/.deepagent_snapshots"
    echo "$label" > "$HOME/.deepagent_snapshots/latest"
    echo "$(date '+%Y-%m-%d %H:%M:%S') | Label: backup-${label}" >> "$HOME/.deepagent_snapshots/history.log"
    echo -e "\n${GREEN}✓ Snapshot [backup-${label}] created successfully.${NC}"
}

rollback_snapshot() {
    local label="$1"
    if [ -z "$label" ]; then
        if [ -f "$HOME/.deepagent_snapshots/latest" ]; then
            label=$(cat "$HOME/.deepagent_snapshots/latest")
        else
            echo -e "${RED}Error: No snapshot label specified.${NC}"
            exit 1
        fi
    fi

    echo -e "\n${BLUE}====================================================${NC}"
    echo -e "${YELLOW}>>> Rolling Back to Snapshot: [backup-${label}]...${NC}"
    echo -e "${BLUE}====================================================${NC}"

    for c in "${CRITICAL_CONTAINERS[@]}"; do
        local original_img="localhost/${c}:backup-${label}"
        podman stop -t 2 "$c" >/dev/null 2>&1 || true
        podman rm "$c" >/dev/null 2>&1 || true

        if [ "$c" == "deepagent-service" ]; then
            podman run -d --name deepagent-service --pod deepagent-prod-pod \
              -e DATABASE_URL=postgresql://hermes:secret456@127.0.0.1:5432/hitl \
              -e ANSIBLE_MCP_URL=http://127.0.0.1:8000/mcp \
              -e SOP_MCP_URL=http://127.0.0.1:8001/mcp \
              "$original_img" python -m app.main >/dev/null
        elif [ "$c" == "deepagent-proxy" ]; then
            podman run -d --name deepagent-proxy --pod deepagent-prod-pod "$original_img" nginx -g "daemon off;" >/dev/null
        elif [ "$c" == "deepagent-webui" ]; then
            podman run -d --name deepagent-webui --pod deepagent-prod-pod "$original_img" python -m http.server 3000 >/dev/null
        elif [ "$c" == "deepagent-ansible-mcp" ]; then
            podman run -d --name deepagent-ansible-mcp --pod deepagent-prod-pod "$original_img" python ansible_mcp_server.py >/dev/null
        elif [ "$c" == "deepagent-sop-mcp" ]; then
            podman run -d --name deepagent-sop-mcp --pod deepagent-prod-pod "$original_img" python server.py >/dev/null
        fi
        echo -e "${GREEN}✓ Restored $c${NC}"
    done

    echo "Waiting 5 seconds for services to initialize..."
    sleep 5
    run_smoke_test
}

list_snapshots() {
    echo -e "\n${BLUE}====================================================${NC}"
    echo -e "${YELLOW}>>> Existing DeepAgent Container Snapshots:${NC}"
    echo -e "${BLUE}====================================================${NC}"
    podman images | grep "backup-" || echo "No snapshots found."
}

case "${1:-test}" in
    snapshot) create_snapshot "$2" ;;
    test) run_smoke_test ;;
    rollback) rollback_snapshot "$2" ;;
    list) list_snapshots ;;
    *) echo "Usage: $0 {snapshot [label] | test | rollback [label] | list}" ; exit 1 ;;
esac
