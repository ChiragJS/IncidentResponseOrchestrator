#!/bin/bash

# Incident Response Orchestrator - Demo Setup Script (Helm + Kind)
# This script automates existing "Option 1" setup on a local Kind cluster for demo purposes.
# Features: Crashing pod for automatic alert triggering, kubectl diagnostics

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}==========================================${NC}"
echo -e "${BLUE}  Orchestrator Demo Setup (Helm edition)  ${NC}"
echo -e "${BLUE}==========================================${NC}"

# 1. Prerequisites Check
echo -e "\n${YELLOW}[1/6] Checking Prerequisites...${NC}"

if [ -z "$GEMINI_API_KEY" ]; then
    echo "❌ Error: GEMINI_API_KEY is not set."
    echo "Please run: export GEMINI_API_KEY=your_actual_key"
    exit 1
fi

command -v kind >/dev/null 2>&1 || { echo "❌ kind is required."; exit 1; }
command -v helm >/dev/null 2>&1 || { echo "❌ helm is required."; exit 1; }
command -v kubectl >/dev/null 2>&1 || { echo "❌ kubectl is required."; exit 1; }

echo "✅ All prerequisites found."

# 2. Cluster Creation
echo -e "\n${YELLOW}[2/6] Setting up Kind Cluster...${NC}"
CLUSTER_NAME="orchestrator-demo"

if kind get clusters | grep -q "^$CLUSTER_NAME$"; then
    echo "Cluster '$CLUSTER_NAME' already exists. Switching context..."
else
    kind create cluster --name "$CLUSTER_NAME"
fi
kubectl cluster-info --context "kind-$CLUSTER_NAME"

# 3. Helm Installation
echo -e "\n${YELLOW}[3/6] Installing Orchestrator Chart...${NC}"
cd "$PROJECT_ROOT/deploy"

# Upgrade --install is idempotent
helm upgrade --install orchestrator ./helm/orchestrator \
    --set secrets.geminiApiKey="$GEMINI_API_KEY" \
    --set image.pullPolicy=IfNotPresent \
    --wait \
    --timeout 10m

echo "✅ Helm chart installed successfully."

# 4. Deploy Crashing Pod (Victim for Demo)
echo -e "\n${YELLOW}[4/6] Deploying Crashing Pod (Demo Victim)...${NC}"

# Delete existing victim if present
kubectl delete deployment crashing-demo --ignore-not-found

# Create a crashing pod that will trigger PodCrashLooping alert
cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: crashing-demo
  labels:
    app: crashing-demo
spec:
  replicas: 1
  selector:
    matchLabels:
      app: crashing-demo
  template:
    metadata:
      labels:
        app: crashing-demo
    spec:
      containers:
        - name: crasher
          image: busybox:latest
          command: ["sh", "-c", "echo 'Starting up...' && sleep 5 && echo 'FATAL ERROR: Connection refused' && exit 1"]
EOF

echo "✅ Crashing pod deployed. It will enter CrashLoopBackOff shortly."

# 5. Wait for things to stabilize
echo -e "\n${YELLOW}[5/6] Waiting for system to stabilize...${NC}"
sleep 10
echo "Checking pod status..."
kubectl get pods

# 6. Instructions & Port Forwarding
echo -e "\n${YELLOW}[6/6] Setup Complete! Ready for Demo.${NC}"
echo -e "${BLUE}==========================================${NC}"

echo -e "\n${RED}🔥 AUTOMATIC ALERT FLOW:${NC}"
echo "The crashing-demo pod will:"
echo "  1. Start → Crash → CrashLoopBackOff"
echo "  2. kube-state-metrics exposes restart count"
echo "  3. Prometheus fires PodCrashLooping alert"
echo "  4. Alertmanager sends webhook to Ingest"
echo "  5. AI Agent runs kubectl diagnostics"
echo "  6. AI Agent proposes remediation"

echo -e "\n${GREEN}Port Forwarding Commands (Run in separate terminals):${NC}"

echo -e "\n1. 📊 Grafana (Dashboards)"
echo "   kubectl port-forward svc/orchestrator-grafana 3000:80"
echo "   URL: http://localhost:3000 (admin/admin)"

echo -e "\n2. 🚨 Alertmanager (UI)"
echo "   kubectl port-forward svc/orchestrator-alertmanager 9093:9093"
echo "   URL: http://localhost:9093"

echo -e "\n3. 📈 Prometheus (Alerts Status)"
echo "   kubectl port-forward svc/orchestrator-prometheus 9090:9090"
echo "   URL: http://localhost:9090/alerts"

echo -e "\n4. 📥 Ingest Service (Manual Triggers)"
echo "   kubectl port-forward svc/orchestrator-ingest 8080:8080"

echo -e "\n${GREEN}Watch the AI Agent in Action:${NC}"
echo "kubectl logs -l app=ai-agent -f"

echo -e "\n${GREEN}Manual Alert Trigger (Optional):${NC}"
echo "curl -X POST http://localhost:8080/ingest \\"
echo "  -H 'Content-Type: application/json' \\"
echo "  -d '{\"source\":\"demo\",\"event_type\":\"alert\",\"severity\":\"critical\",\"summary\":\"Pod CrashLoopBackOff\",\"metadata\":{\"namespace\":\"default\",\"pod\":\"crashing-demo\",\"service\":\"crashing-demo\"}}'"

echo -e "\n${BLUE}Happy Recording! 🎥${NC}"

