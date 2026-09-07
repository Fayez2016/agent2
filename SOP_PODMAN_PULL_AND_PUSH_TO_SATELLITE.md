# SOP: Manual Podman Pull & Push to Red Hat Satellite

This standalone procedure explains how to use **Podman** on your workstation, bastion host, or Satellite server to manually pull Deep Agent container images from `quay.io` and push them directly into **Red Hat Satellite's internal container registry**.

This is the recommended approach when Red Hat Satellite cannot connect directly to `quay.io` due to firewall restrictions, proxy SSL interception, or airgap policies.

---

## 1. How Red Hat Satellite Container Registry Works

Red Hat Satellite runs an embedded container registry (Crane/Pulp) on HTTPS port 5000 (or port 443 with reverse proxy).

### Satellite Registry Image Path Format
When you push or pull directly to/from Satellite via Podman/Docker, Satellite requires the image name to follow this naming convention:

```text
<satellite-fqdn>/<organization_label>-<product_label>-<repository_label>:<tag>
```

* **`<satellite-fqdn>`**: The hostname of your Satellite server (e.g., `satellite.corp.internal` or `satellite.corp.internal:5000`).
* **`<organization_label>`**: The lowercase label of your Organization (e.g., `default_organization` or `enterprise`).
* **`<product_label>`**: The lowercase product name (e.g., `deepagent`).
* **`<repository_label>`**: The name of the microservice (e.g., `deepagent-core`).
* **`<tag>`**: `latest`

---

## 2. Step-by-Step Manual Procedure

### Step 1: Prepare the Custom Product & Repositories in Satellite

Before pushing images, Satellite must have the custom container repositories defined to accept them:

#### Option A: Via Satellite Web UI
1. Log in to your Satellite Web UI.
2. Go to **Content** > **Products** > Click **Create Product**.
   - Name: `DeepAgent`
   - Click **Save**.
3. Inside the `DeepAgent` product, create a repository for each of the 7 images:
   - Click **New Repository**.
   - Name: `deepagent-core` (repeat for all 7).
   - Type: `docker`.
   - **Important**: Leave "Upstream URL" **empty / blank** (this tells Satellite it is an internally pushed repository).
   - Click **Save**.

#### Option B: Via `hammer` CLI on Satellite Server
```bash
ORGANIZATION="Default_Organization"

# 1. Create Product
hammer product create \
  --name "DeepAgent" \
  --organization "${ORGANIZATION}"

# 2. Create 7 empty Docker repositories
IMAGES=(
  "deepagent-core"
  "deepagent-ansible-mcp"
  "deepagent-sop-mcp"
  "deepagent-hitl-db"
  "deepagent-mock-aap"
  "deepagent-hitl-web"
  "deepagent-proxy"
)

for img in "${IMAGES[@]}"; do
  hammer repository create \
    --name "${img}" \
    --product "DeepAgent" \
    --content-type "docker" \
    --organization "${ORGANIZATION}"
done
```

---

### Step 2: Log in to Quay.io & Red Hat Satellite

On the workstation or bastion host that has internet access:

```bash
# 1. Log in to Quay.io
echo "kNC@4P_BAFnVf6!" | podman login -u "souffm0a" --password-stdin quay.io

# 2. Log in to Red Hat Satellite
# (Use your Satellite administrator username and password)
SATELLITE_HOST="satellite.corp.internal"
podman login "${SATELLITE_HOST}"
```

> [!NOTE]
> If your Satellite uses a custom corporate CA or self-signed certificate, either trust the Satellite CA in `/etc/pki/ca-trust/source/anchors/` (then run `update-ca-trust`), or pass `--tls-verify=false` to `podman login` and `podman push`.

---

### Step 3: Pull, Tag, and Push the 7 Microservices

Run the following commands to pull from Quay, tag with the Satellite namespace, and push:

```bash
SATELLITE_HOST="satellite.corp.internal"
ORG="default_organization"
PRODUCT="deepagent"
TAG="latest"

IMAGES=(
  "deepagent-core"
  "deepagent-ansible-mcp"
  "deepagent-sop-mcp"
  "deepagent-hitl-db"
  "deepagent-mock-aap"
  "deepagent-hitl-web"
  "deepagent-proxy"
)

for img in "${IMAGES[@]}"; do
  QUAY_NAME="quay.io/souffm0a/${img}:${TAG}"
  SAT_NAME="${SATELLITE_HOST}/${ORG}-${PRODUCT}-${img}:${TAG}"

  echo -e "\n⬇️  [1/3] Pulling ${QUAY_NAME} ..."
  podman pull "${QUAY_NAME}"

  echo "🏷️  [2/3] Tagging as ${SAT_NAME} ..."
  podman tag "${QUAY_NAME}" "${SAT_NAME}"

  echo "⬆️  [3/3] Pushing to Satellite ..."
  podman push "${SAT_NAME}"
done
```

---

### Step 4: Publish & Promote in Satellite (Content View)

Once pushed, Satellite stores the images in the `Library` environment. To make them consumable by production servers:

1. **Content View**:
   - Go to **Content** > **Content Views** > Create `DeepAgent_CV`.
   - Add the 7 Docker repositories from the `DeepAgent` product.
2. **Publish & Promote**:
   - Click **Publish New Version**.
   - Promote to your target lifecycle environment (e.g., `Production`).

---

### Step 5: Deploying Target Servers from Satellite

On your target production servers in the datacenter:

```bash
# 1. Log in to Satellite registry
podman login satellite.corp.internal

# 2. Deploy using the Satellite registry path
REGISTRY="satellite.corp.internal/default_organization-production-deepagent_cv-deepagent" ./deploy_from_quay.sh
```
