#!/bin/bash

# Incident Response Orchestrator - Setup Script
# This script automates the complete setup of the system

set -e

# Get the project root directory (parent of scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=========================================="
echo "  Incident Response Orchestrator Setup"
echo "=========================================="
echo "Project root: $PROJECT_ROOT"

# Check prerequisites
check_prerequisites() {
    echo ""
    echo "Checking prerequisites..."
    
    command -v docker >/dev/null 2>&1 || { echo "Docker is required but not installed. Aborting." >&2; exit 1; }
    command -v kubectl >/dev/null 2>&1 || { echo "kubectl is required but not installed. Aborting." >&2; exit 1; }
    command -v kind >/dev/null 2>&1 || { echo "kind is required but not installed. Aborting." >&2; exit 1; }
    
    if [ -z "$GEMINI_API_KEY" ]; then
        echo "WARNING: GEMINI_API_KEY not set. AI Agent will not work."
        echo "Set it with: export GEMINI_API_KEY=your_key"
    fi
    
    echo "✓ Prerequisites check passed"
}

# Create Kind cluster
setup_k8s() {
    echo ""
    echo "Step 1: Setting up Kubernetes cluster..."
    
    if kind get clusters | grep -q "orchestrator-test"; then
        echo "  Cluster 'orchestrator-test' already exists"
    else
        kind create cluster --name orchestrator-test
    fi
    
    # Generate internal kubeconfig
    kind get kubeconfig --name orchestrator-test --internal > "$PROJECT_ROOT/deploy/kubeconfig"
    
    echo "✓ Kubernetes cluster ready"
}

# Start infrastructure
start_infra() {
    echo ""
    echo "Step 2: Starting infrastructure..."
    
    cd "$PROJECT_ROOT/deploy"
    docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build
    
    echo "  Waiting for services to be healthy..."
    sleep 15
    
    echo "✓ Infrastructure started"
}

# Deploy victim service
deploy_victim() {
    echo ""
    echo "Step 3: Deploying test victim service..."
    
    kubectl delete deployment kafka-ingest --ignore-not-found
    kubectl create deployment kafka-ingest --image=nginx:alpine --replicas=1
    
    echo "  Waiting for pod to be ready..."
    kubectl wait --for=condition=available deployment/kafka-ingest --timeout=120s
    
    echo "✓ Victim service deployed"
}

# Ingest runbooks
ingest_runbooks() {
    echo ""
    echo "Step 4: Ingesting runbooks into knowledge base..."
    
    # Wait for AI Agent to be ready
    echo "  Waiting for AI Agent to initialize..."
    sleep 10
    
    docker exec deploy-ai-agent-1 python3 src/scripts/ingest_runbooks.py /app/runbooks 2>/dev/null || {
        echo "  Retrying ingestion..."
        sleep 15
        docker exec deploy-ai-agent-1 python3 src/scripts/ingest_runbooks.py /app/runbooks
    }
    
    echo "✓ Runbooks ingested"
}

# Verify setup
verify_setup() {
    echo ""
    echo "Step 5: Verifying setup..."
    
    # Check services
    echo "  Checking services..."
    curl -s http://localhost:8080/health >/dev/null 2>&1 || echo "  NOTE: Ingest health endpoint not implemented"
    
    # Check K8s
    echo "  Kubernetes status:"
    kubectl get deployment kafka-ingest
    
    echo ""
    echo "✓ Setup verification complete"
}

# Print summary
print_summary() {
    echo ""
    echo "=========================================="
    echo "  Setup Complete!"
    echo "=========================================="
    echo ""
    echo "Available Services:"
    echo "  - Ingest API:    http://localhost:8080/ingest"
    echo "  - Kafka:         localhost:9094"
    echo "  - MinIO Console: http://localhost:9001 (minioadmin/minioadmin)"
    echo "  - Grafana:       http://localhost:3000 (admin/admin)"
    echo "  - Prometheus:    http://localhost:9091"
    echo ""
    echo "Test the system:"
    echo "  curl -X POST http://localhost:8080/ingest \\"
    echo "    -H 'Content-Type: application/json' \\"
    echo "    -d '{\"source\":\"test\",\"service_name\":\"kafka-ingest\",\"alert\":\"KafkaConsumerLagHigh\",\"description\":\"Test\"}'"
    echo ""
    echo "Watch scaling:"
    echo "  kubectl get deployment kafka-ingest -w"
    echo ""
}

# Main
main() {
    check_prerequisites
    setup_k8s
    start_infra
    deploy_victim
    ingest_runbooks
    verify_setup
    print_summary
}

main "$@"
