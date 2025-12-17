#!/bin/bash

# Incident Response Orchestrator - Helm Setup Script
# This script automates the infrastructure setup on a local Kind cluster.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}==========================================${NC}"
echo -e "${BLUE}  Orchestrator Setup (Helm + Kind)        ${NC}"
echo -e "${BLUE}==========================================${NC}"

# Check for .env file
if [ -f "$PROJECT_ROOT/.env" ]; then
    export $(grep -v '^#' "$PROJECT_ROOT/.env" | xargs)
fi

# 1. Prerequisites Check
echo -e "\n${YELLOW}[1/4] Checking Prerequisites...${NC}"

if [ -z "$GEMINI_API_KEY" ]; then
    echo -e "${RED}❌ Error: GEMINI_API_KEY is not set.${NC}"
    echo "Please ensure .env file exists with GEMINI_API_KEY or export it manually."
    exit 1
fi

command -v kind >/dev/null 2>&1 || { echo "❌ kind is required."; exit 1; }
command -v helm >/dev/null 2>&1 || { echo "❌ helm is required."; exit 1; }
command -v kubectl >/dev/null 2>&1 || { echo "❌ kubectl is required."; exit 1; }

echo "✅ All prerequisites found."

# 2. Cluster Creation
echo -e "\n${YELLOW}[2/4] Setting up Kind Cluster...${NC}"
CLUSTER_NAME="orchestrator-test"

if kind get clusters | grep -q "^$CLUSTER_NAME$"; then
    echo "Cluster '$CLUSTER_NAME' already exists. Switching context..."
else
    kind create cluster --name "$CLUSTER_NAME"
fi
kubectl cluster-info --context "kind-$CLUSTER_NAME"

# 3. Helm Installation
echo -e "\n${YELLOW}[3/4] Installing Orchestrator Chart...${NC}"
cd "$PROJECT_ROOT/deploy"

helm upgrade --install orchestrator ./helm/orchestrator \
    --set secrets.geminiApiKey="$GEMINI_API_KEY" \
    --set image.pullPolicy=Always \
    --wait \
    --timeout 10m

echo "✅ Helm chart installed successfully."

# 4. Instructions
echo -e "\n${YELLOW}[4/4] Setup Complete!${NC}"
echo -e "${BLUE}==========================================${NC}"
echo -e "\n${GREEN}Services are running:${NC}"
echo "  - Grafana:       http://localhost:3000 (Forward with: kubectl port-forward svc/orchestrator-grafana 3000:3000)"
echo "  - Prometheus:    http://localhost:9090 (Forward with: kubectl port-forward svc/orchestrator-prometheus 9090:9090)"
echo "  - Agent Logs:    kubectl logs -l app=ai-agent -f"
echo ""
echo "To run the tests, check TEST.md."
