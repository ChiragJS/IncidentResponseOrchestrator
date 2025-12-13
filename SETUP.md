# Setup Guide

This guide walks you through setting up the Incident Response Orchestrator from scratch.

## Prerequisites

Before you begin, ensure you have the following installed:

| Tool           | Version  | Purpose                        |
|----------------|----------|--------------------------------|
| Docker         | 20.10+   | Container runtime              |
| Docker Compose | 2.0+     | Multi-container orchestration  |
| Go             | 1.21+    | Building Go services           |
| Python         | 3.10+    | AI Agent service               |
| kubectl        | 1.28+    | Kubernetes CLI                 |
| kind           | 0.20+    | Local Kubernetes cluster       |

## Quick Start (Automated)

Run the automated setup script:

```bash
./scripts/setup.sh
```

This script will:
1. Create a local Kubernetes cluster
2. Start all infrastructure (Kafka, MinIO, Qdrant)
3. Build and deploy all services
4. Ingest sample runbooks
5. Deploy a test victim service

## Manual Setup

### Step 1: Clone the Repository

```bash
git clone https://github.com/ChiragJS/IncidentResponseOrchestrator.git
cd IncidentResponseOrchestrator
```

### Step 2: Set Environment Variables

Create a `.env` file in the `deploy/` directory:

```bash
# Required
GEMINI_API_KEY=your_google_ai_api_key

# Optional (defaults shown)
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
```

### Step 3: Create Local Kubernetes Cluster

```bash
kind create cluster --name orchestrator-test
```

Generate internal kubeconfig:

```bash
kind get kubeconfig --name orchestrator-test --internal > deploy/kubeconfig
```

### Step 4: Start Infrastructure

```bash
cd deploy
docker compose up -d
```

Wait for all services to be healthy:

```bash
docker compose ps
```

### Step 5: Create Test Deployment

Deploy a victim service to test against:

```bash
kubectl create deployment kafka-ingest --image=nginx:alpine --replicas=1
```

### Step 6: Ingest Runbooks

Copy and run the ingestion script:

```bash
docker exec deploy-ai-agent-1 python3 src/scripts/ingest_runbooks.py /app/runbooks
```

### Step 7: Verify the System

Trigger a test incident:

```bash
curl -X POST http://localhost:8080/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "source": "prometheus",
    "service_name": "kafka-ingest",
    "alert": "KafkaConsumerLagHigh",
    "description": "Test alert"
  }'
```

Watch the deployment scale:

```bash
kubectl get deployment kafka-ingest -w
```

## Service Ports

| Service      | Port  | Description              |
|-------------|-------|--------------------------|
| Ingest API  | 8080  | Alert ingestion endpoint |
| Kafka       | 9094  | External Kafka broker    |
| MinIO       | 9000  | Object storage API       |
| MinIO Console | 9001 | MinIO web UI             |
| Qdrant      | 6333  | Vector database          |
| Prometheus  | 9091  | Metrics server           |
| Grafana     | 3000  | Dashboards               |
| Loki        | 3100  | Log aggregation          |

## Troubleshooting

### Kafka Connection Issues

If services fail to connect to Kafka, ensure Kafka is healthy:

```bash
docker logs deploy-kafka-1
```

### MinIO/Qdrant Connection Issues

Check that environment variables are set correctly:

```bash
docker exec deploy-ai-agent-1 env | grep -E "(MINIO|QDRANT)"
```

### Executor Can't Reach K8s

Ensure kubeconfig is mounted and the executor is on the `kind` network:

```bash
docker inspect deploy-executor-1 | grep -A5 Networks
```

## Cleanup

Stop all services:

```bash
cd deploy
docker compose down -v
```

Delete the Kubernetes cluster:

```bash
kind delete cluster --name orchestrator-test
```
