# Executor Service

The Executor Service is the actuator of the Incident Response Orchestrator. It executes approved remediation actions against the target Kubernetes cluster.

## Responsibility

- Consume approved actions from `actions.approved` topic
- Execute actions against Kubernetes cluster
- Report execution status to `actions.status` topic

## Supported Actions

| Action Type                  | K8s Operation                           |
|-----------------------------|----------------------------------------|
| `restart_pod`               | Delete pod (triggers replacement)       |
| `scale_deployment`          | Update deployment replica count         |
| `rolling_restart_deployment` | Add restart annotation to trigger rollout |

### `scale_deployment` Parameters

| Parameter           | Description                    |
|--------------------|--------------------------------|
| `replicas`         | Absolute replica count          |
| `replicas_increment` | Relative change (+1, -1, etc.) |
| `namespace`        | Target namespace (default: `default`) |

### `rolling_restart_deployment` Parameters

The executor adds `kubectl.kubernetes.io/restartedAt` annotation to trigger a rolling restart.

## Supported Features

- [x] Kubernetes client integration (client-go)
- [x] Pod deletion for restart
- [x] Deployment scaling (absolute and relative)
- [x] Rolling restart via annotation
- [x] Simulation mode (when K8s client unavailable)
- [x] Status reporting to Kafka

## Not Yet Implemented

- [ ] **Dry-Run Mode**: No preview before execution
- [ ] **Rollback**: No automatic undo on failure
- [ ] **Timeout Handling**: No execution timeouts
- [ ] **Multi-Cluster**: Single cluster support only
- [ ] **Custom Resources**: Only core K8s resources (no CRDs)
- [ ] **Helm/Kustomize**: No chart-based operations

## Configuration

| Environment Variable | Default        | Description              |
|---------------------|----------------|--------------------------|
| `KAFKA_BROKER`      | `localhost:9092` | Kafka bootstrap servers |
| `KUBECONFIG`        | `~/.kube/config` | Path to kubeconfig file |

## Execution Flow

```
actions.approved → Executor → K8s API
                          ↓
              actions.status (success/failed)
```

## Simulation Mode

When no kubeconfig is available, the Executor runs in simulation mode:
- Logs the action that *would* be taken
- Waits 2 seconds (simulated work)
- Reports success

## Tech Stack

- **Language**: Go
- **K8s Client**: client-go
- **Messaging**: Kafka (confluent-kafka-go)
