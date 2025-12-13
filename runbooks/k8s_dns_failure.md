# Kubernetes DNS Resolution Failure Runbook

**Severity**: Critical
**Service**: Kubernetes / Networking
**Keywords**: dns, nxdomain, lookup failure, core-dns

## Symptoms
-   Alert: `KubeDnsErrorsHigh`.
-   Logs show `dial tcp: lookup <service-name>: no such host`.
-   Internal service-to-service communication fails completely.

## Root Causes
1.  **CoreDNS Down**: CoreDNS pods are crashed or not ready.
2.  **Node DNS Config**: `/etc/resolv.conf` on the node is incorrect.
3.  **Network Policy**: Blocking UDP/53.
4.  **Conntrack Full**: Node usage of conntrack table failed (common in high traffic).

## Troubleshooting Steps
1.  **Check CoreDNS**:
    `kubectl get pods -n kube-system -l k8s-app=kube-dns`

2.  **Test Lookup**:
    `kubectl run -it --rm busybox --image=busybox:1.28 -- nslookup kubernetes.default`

## Remediation Actions
-   **Restart CoreDNS**: Often clears transient lockups.
    *Action*: `restart_pod` (Target: `coredns-<id>`, Params: `{"namespace": "kube-system"}`)
    *(Note: Policy engine might block this without override)*.
-   **Scale CoreDNS**: If CPU usage is high on CoreDNS pods.
    *Action*: `scale_deployment` (Target: `coredns`)
