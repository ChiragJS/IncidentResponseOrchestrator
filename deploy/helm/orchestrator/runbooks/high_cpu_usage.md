# High CPU Usage Runbook

**Severity**: Warning/High
**Service**: General / Compute
**Keywords**: cpu, throttling, slow, performance

## Symptoms
-   Alert: `ContainerHighCPUUsage` (> 90%).
-   Response times increase (latency).
-   Liveness probes might time out due to starvation.

## Root Causes
1.  **Infinite Loop**: Application bug causing 100% core usage.
2.  **Traffic Spike**: Valid increase in user load.
3.  **Crypto Mining / Compromise**: Unauthorized process running.
4.  **Garbage Collection**: Heavy GC cycles (Java/Go).

## Troubleshooting Steps
1.  **Identify Top Consumers**:
    `kubectl top pod --sort-by=cpu`

2.  **Profile**:
    -   If Go: check pprof.
    -   If unknown: `kubectl exec <pod> -- top`

## Remediation Actions
-   **Scale Out**: Add more replicas to distribute load.
    *Action*: `scale_deployment` (Target: `<deployment-name>`)
-   **Restart Pod**: If triggered by a stuck process/loop.
    *Action*: `restart_pod` (Target: `<pod-name>`)
-   **Vertical Scale**: Increase CPU limits in deployment YAML (Long term).
