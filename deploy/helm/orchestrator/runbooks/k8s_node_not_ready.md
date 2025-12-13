# Kubernetes Node Not Ready Runbook

**Severity**: Critical
**Service**: Infrastructure / Node
**Keywords**: node, notready, kubelet, unknown

## Symptoms
-   Alert: `KubeNodeNotReady`.
-   Pods on the node enter `Terminating` or `Unknown` state.
-   Capacity of the cluster decreases.

## Root Causes
1.  **Kubelet Crash**: The kubelet process stopped running.
2.  **Disk Pressure**: Node ran out of disk; Docker/Containerd stopped.
3.  **Network Partition**: Node cannot reach the API server.
4.  **OOM**: System OOM killer killed vital system daemons.

## Troubleshooting Steps
1.  **Describe Node**:
    `kubectl describe node <node-name>`
    - Check "Conditions" (DiskPressure, PIDPressure, Ready).

2.  **Syslogs**:
    (Requires SSH) `journalctl -u kubelet`

## Remediation Actions
-   **Drain Node**: Safely evict workloads to other nodes.
    *Action*: `drain_node` (Target: `<node-name>`)
-   **Reboot Node**: (Last resort, requires IaaS access).
-   **Restart Kubelet**: (Requires SSH access, usually manual).
