# Setup Guide

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Docker | 20.10+ | Container runtime |
| kubectl | 1.28+ | Kubernetes CLI |
| Helm | 3.10+ | Package manager (Required for Prod) |
| kind | 0.20+ | Local cluster (Optional) |
| Go | 1.21+ | Service development |

---

## 🚀 Option 1: Production Deployment (Helm) - Recommended

This is the robust, "drop-in" method suitable for any Kubernetes cluster (EKS, GKE, AKS, or Kind).

### 1. Requirements
Ensure you have a Kubernetes cluster and `helm` installed.
```bash
export GEMINI_API_KEY=your_actual_key
```

### 2. Install the Chart
The chart is fully self-contained. It will deploy Kafka, MinIO, Qdrant, and all microservices, effectively populating the Knowledge Base automatically.

```bash
cd deploy
helm install orchestrator ./helm/orchestrator \
  --set secrets.geminiApiKey=$GEMINI_API_KEY
```

**Customization:**
To verify what will be installed:
```bash
helm template orchestrator ./helm/orchestrator --set secrets.geminiApiKey=$GEMINI_API_KEY
```

### 3. Verify Deployment
Wait for the automated initialization job to complete (ingesting runbooks):

```bash
kubectl get jobs -w
# Wait for orchestrator-init-runbooks to complete
```

Check all pods:
```bash
kubectl get pods
```

### 4. Trigger a Test Alert
You can manually simulate an alert using a temporary pod:
```bash
kubectl run manual-alert --image=curlimages/curl --restart=Never -- \
  curl -X POST http://orchestrator-ingest:8080/ingest \
  -H "Content-Type: application/json" \
  -d '{"source":"manual","event_type":"alert","severity":"critical","summary":"Manual Test from Helm Setup","metadata":{"namespace":"default","service":"test"}}'
```

---

## 🛠️ Option 2: Local Development (Docker Compose)

Use this for rapid iteration on the services code.

### Automated Setup (Recommended)
We provide a script that handles Kind cluster creation and Docker Compose overlay for you:

```bash
./scripts/setup.sh
```

### Manual Setup
If you prefer running commands manually:

1. **Create Cluster**:
   ```bash
   kind create cluster --name orchestrator-test
   kind get kubeconfig --name orchestrator-test --internal > deploy/kubeconfig
   ```

2. **Start Services**:
   **Important**: You must use the `docker-compose.local.yml` overlay to work with Kind.
   ```bash
   cd deploy
   docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build
   ```

3. **Ingest Runbooks**:
   ```bash
   docker exec deploy-ai-agent-1 python3 src/scripts/ingest_runbooks.py /app/runbooks
   ```

---

## Troubleshooting

### Helm Init Job Failure
If `orchestrator-init-runbooks` fails:
- Check logs: `kubectl logs -l app=init-runbooks`
- Ensure API Key is set: Check secrets `kubectl get secret orchestrator-secrets -o yaml`

### Kafka Connectivity
- **Helm**: Internal services use `orchestrator-kafka:9092`. K8s naming resolution must work.
- **Docker Compose**: Uses `kind` network. Ensure you didn't start with just `docker compose up` (missing the network overlay).
