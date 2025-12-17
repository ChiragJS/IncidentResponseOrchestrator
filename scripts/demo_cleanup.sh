#!/bin/bash

# Incident Response Orchestrator - Demo Cleanup Script
# This script removes all resources created by demo_helm.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

echo -e "${YELLOW}==========================================${NC}"
echo -e "${YELLOW}  Orchestrator Demo Cleanup${NC}"
echo -e "${YELLOW}==========================================${NC}"

CLUSTER_NAME="orchestrator-demo"

# Check if cluster exists
if ! kind get clusters | grep -q "^$CLUSTER_NAME$"; then
    echo -e "${GREEN}✓ Cluster '$CLUSTER_NAME' does not exist. Nothing to clean up.${NC}"
    exit 0
fi

# Switch context
kubectl config use-context "kind-$CLUSTER_NAME" 2>/dev/null || true

echo -e "\n${YELLOW}[1/3] Uninstalling Helm release...${NC}"
cd "$PROJECT_ROOT/deploy"
if helm list | grep -q "orchestrator"; then
    helm uninstall orchestrator --wait || echo "Helm release already removed"
    echo "✓ Helm release removed"
else
    echo "✓ Helm release not found (already removed)"
fi

echo -e "\n${YELLOW}[2/3] Deleting victim deployments...${NC}"
kubectl delete deployment kafka-ingest --ignore-not-found
kubectl delete deployment crashing-demo --ignore-not-found
echo "✓ Victim deployments removed"

echo -e "\n${YELLOW}[3/3] Deleting Kind cluster...${NC}"
kind delete cluster --name "$CLUSTER_NAME"
echo "✓ Cluster deleted"

echo -e "\n${GREEN}==========================================${NC}"
echo -e "${GREEN}  Cleanup Complete!${NC}"
echo -e "${GREEN}==========================================${NC}"
echo -e "\nAll demo resources have been removed."
echo -e "You can run ${YELLOW}./scripts/demo_helm.sh${NC} again to recreate the demo environment."
