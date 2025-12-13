#!/bin/bash

# Incident Response Orchestrator - Cleanup Script
# This script tears down all resources created by setup.sh

set -e

# Get the project root directory (parent of scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=========================================="
echo "  Incident Response Orchestrator Cleanup"
echo "=========================================="

# Confirm
read -p "This will stop all services and optionally delete the K8s cluster. Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

# Stop Docker Compose
stop_docker() {
    echo ""
    echo "Step 1: Stopping Docker services..."
    
    cd "$PROJECT_ROOT/deploy"
    docker compose down -v 2>/dev/null || true
    
    echo "✓ Docker services stopped"
}

# Delete victim deployment
delete_victim() {
    echo ""
    echo "Step 2: Deleting test deployment..."
    
    kubectl delete deployment kafka-ingest --ignore-not-found 2>/dev/null || true
    
    echo "✓ Test deployment deleted"
}

# Optionally delete Kind cluster
delete_cluster() {
    echo ""
    read -p "Delete the Kind cluster 'orchestrator-test'? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        kind delete cluster --name orchestrator-test 2>/dev/null || true
        rm -f "$PROJECT_ROOT/deploy/kubeconfig"
        echo "✓ Kind cluster deleted"
    else
        echo "  Skipping cluster deletion"
    fi
}

# Clean up Docker resources
cleanup_docker() {
    echo ""
    read -p "Prune unused Docker images and volumes? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker system prune -f 2>/dev/null || true
        docker volume prune -f 2>/dev/null || true
        echo "✓ Docker resources pruned"
    else
        echo "  Skipping Docker prune"
    fi
}

# Print summary
print_summary() {
    echo ""
    echo "=========================================="
    echo "  Cleanup Complete!"
    echo "=========================================="
    echo ""
    echo "To re-setup, run:"
    echo "  ./scripts/setup.sh"
    echo ""
}

# Main
main() {
    stop_docker
    delete_victim
    delete_cluster
    cleanup_docker
    print_summary
}

main "$@"
