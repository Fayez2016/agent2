# Staging & Airgapped Migration User Guide

This guide details how to prepare, test, and deploy the **Hermes Agent & Enterprise Automation Platform (`agent2`)** in a completely airgapped environment and VMware Kubernetes (vSphere/Tanzu) cluster.

---

## 📋 Overview & Prerequisites

### Environments Supported:
- **Development Workstation / WSL2**: For building offline images and testing locally.
- **Staging Linux Server / VM**: For validating offline airgapped operation.
- **VMware Kubernetes Cluster**: Production target using `kubectl` / Kustomize.

---

## 🚀 Quick Start Guide

### Step 1: Shut Down Active Dev Containers
To free up CPU and RAM on your workstation before starting staging:
```bash
# From workspace root (/home/fayez/agent2)
podman-compose down
```

---

### Step 2: Build Offline Ollama Image (`gemma4:12b`)
Execute script `01_build_offline_ollama.sh` to pull the LLM model into a container storage layer:
```bash
./staging/scripts/01_build_offline_ollama.sh gemma4:12b
```
*This creates the local image `localhost/local-ollama:gemma4-12b`.*

---

### Step 3: Start Staging Environment
Spin up the staging containers (including local Ollama, Hermes Agent, MCP server, HITL portal, and Postgres DB):
```bash
podman-compose -f ./staging/docker-compose.staging.yml --env-file ./staging/.env.staging up -d
```

---

### Step 4: Verify Staging Service Endpoints
Run the automated verification script:
```bash
./staging/scripts/04_verify_staging_airgap.sh
```

Execute the staging test script:
```bash
python3 staging/tests/test_staging_airgap.py
```

---

## 🏷️ Quay.io & Offline Media Packaging

### Option A: Tag & Push to Quay.io Registry
If your staging/airgapped environment can pull from an internal Quay.io registry:
```bash
# Tag all 6 images
./staging/scripts/02_tag_and_push_quay.sh fayez2016 staging

# Push images (requires prior 'podman login quay.io')
podman push quay.io/fayez2016/hermes-agent:staging
podman push quay.io/fayez2016/ansible-mcp:staging
podman push quay.io/fayez2016/hitl-web:staging
podman push quay.io/fayez2016/hitl-db:staging
podman push quay.io/fayez2016/aap-server:staging
podman push quay.io/fayez2016/local-ollama:gemma4-12b
```

### Option B: Export Offline Image Bundle (.tar Archive)
For completely airgapped servers without network registry access:
```bash
./staging/scripts/03_export_image_bundle.sh
```
*Output file: `./staging/bundle/agent2_airgap_bundle.tar`*

On the airgapped target machine, load the tarball:
```bash
podman load -i ./staging/bundle/agent2_airgap_bundle.tar
```

---

## ☸️ VMware Kubernetes (vSphere / Tanzu) Deployment

Deploy to your VMware K8s cluster using `kubectl` and Kustomize:

```bash
# 1. Apply all manifests in namespace 'agent2-airgap'
kubectl apply -k ./staging/k8s/

# 2. Check pod status
kubectl get pods -n agent2-airgap -w

# 3. Access HITL Web & Hermes Agent via NodePort:
#    - HITL Web: http://<Node-IP>:30501
#    - Hermes API: http://<Node-IP>:30642
```

---

## 🔄 Switching Back to Development Mode

When staging testing is complete, tear down staging and resume dev:
```bash
podman-compose -f ./staging/docker-compose.staging.yml down
podman-compose up -d
```
