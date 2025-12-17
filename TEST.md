# Incident Response Orchestrator - Testing Guide

This guide describes how to verify the **Automated Rollback** capability of the Incident Response Orchestrator.

## Prerequisites
- A running Kubernetes cluster (Kind, Minikube, or Cloud).
- Helm installed.
- `kubectl` configured.
- `GEMINI_API_KEY` set in `.env` or environment.

## 1. Setup
Run the setup script to install the orchestrator on a local Kind cluster:
```bash
./scripts/setup_helm.sh
```

## 2. Deploy Victim Service
Deploy a service that will crash to simulate an incident.

**Step 1: Deploy Stable Version (v1)**
```bash
kubectl create deployment crashing-demo --image=nginx:alpine --replicas=1
kubectl rollout status deployment/crashing-demo
```

**Step 2: Update to Crashing Version (v2)**
Apply a patch or set image to a version that crashes on startup:
```bash
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
        - name: nginx
          image: busybox:latest
          command: ["sh", "-c", "echo Starting... && sleep 5 && echo FATAL_ERROR && exit 1"]
EOF
```

The pod will enter `CrashLoopBackOff`.

## 3. Verify Automation
The system should automatically detect the crash and roll back the deployment.

**Monitor Logs:**
Open a new terminal to watch the AI Agent:
```bash
kubectl logs -l app=ai-agent -f
# Look for: "Processing decision", "Proposed Action: rollback_deployment"
```

Open another terminal to watch the Executor:
```bash
kubectl logs -l app=executor -f
# Look for: "Attempting Rollback", "Rollback successful"
```

**Monitor Pod Status:**
Watch the deployment revert to the stable state:
```bash
kubectl get pods -l app=crashing-demo -w
```
You should see the crashing pod terminate and a new pod (running `nginx:alpine`) start up.

## 4. Manual Trigger (Optional)
If you want to speed up the alert (bypass Prometheus scrape/alert delays), trigger it manually:

```bash
kubectl port-forward svc/orchestrator-ingest 8080:8080 &

curl -X POST -H "Content-Type: application/json" -d '{
  "receiver": "webhook",
  "status": "firing",
  "alerts": [
    {
      "status": "firing",
      "labels": {
        "alertname": "PodCrashLooping",
        "severity": "critical",
        "pod": "crashing-demo-xxxxx",
        "namespace": "default",
        "app": "crashing-demo"
      },
      "annotations": {
        "summary": "Pod crashing-demo is crash looping"
      },
      "startsAt": "2025-12-16T12:00:00Z"
    }
  ],
  "commonLabels": {
    "pod": "crashing-demo-xxxxx",
    "app": "crashing-demo"
  }
}' http://localhost:8080/ingest
```

## 5. Cleanup
To remove the demo resources and orchestrator:
```bash
kubectl delete deployment crashing-demo
helm uninstall orchestrator
```
