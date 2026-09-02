#!/bin/bash
export PODMAN_IGNORE_CGROUPSV1_WARNING=1
cd /tmp/test_manual_online/deepagent_system
podman compose -f docker-compose.production.yml up -d
