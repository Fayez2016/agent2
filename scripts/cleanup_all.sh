#!/bin/bash
# ==============================================================================
# Complete SRE Maintenance & Database Cleanup Utility
# Purges conversational traces, threads, and resets HITL request sequence.
# ==============================================================================

echo "=========================================================================="
echo " Starting Full Database & Environment Cleanup..."
echo "=========================================================================="

podman exec -i deepagent-hitl-db psql -U hermes -d hitl -c "
DELETE FROM conversation_messages;
DELETE FROM conversation_threads;
DELETE FROM hitl_requests;
ALTER SEQUENCE hitl_requests_id_seq RESTART WITH 1;
"

echo "Checking database table status:"
podman exec -i deepagent-hitl-db psql -U hermes -d hitl -c "
SELECT 'threads' as table_name, count(*) FROM conversation_threads
UNION ALL
SELECT 'messages', count(*) FROM conversation_messages
UNION ALL
SELECT 'hitl_requests', count(*) FROM hitl_requests
UNION ALL
SELECT 'users', count(*) FROM users
UNION ALL
SELECT 'system_settings', count(*) FROM system_settings;
"

echo "Restarting application service containers..."
podman restart deepagent-service deepagent-langgraph-server

echo "=========================================================================="
echo " ✅ Cleanup complete! Database and service state are clean and ready."
echo "=========================================================================="
