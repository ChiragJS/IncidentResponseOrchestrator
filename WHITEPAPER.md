# Whitepaper: Autonomous Incident Response Orchestrator

## 1. Executive Summary
This document outlines the architecture, design philosophy, and engineering challenges overcome in building an AI-Driven Incident Response Orchestrator. The system is designed to detect, analyze, and remediate infrastructure incidents autonomously using a combination of Event-Driven Architecture, Retrieval-Augmented Generation (RAG), and Kubernetes-native execution.

## 2. Technical Architecture

### 2.1 Core Loop (The "OODA" Loop)
The system implements an Observe-Orient-Decide-Act loop:
1. **Observe (Ingest)**: Prometheus alerts or manual triggers are normalized into CloudEvents.
2. **Orient (Router)**: Events are enriched with Kubernetes context (Pod status, Logs).
3. **Decide (AI Agent)**: Gemini 1.5 Flash uses RAG to retrieve relevant Runbooks (MinIO/Qdrant) and proposes a remediation plan.
4. **Act (Executor)**: Approved actions are executed against the Kubernetes cluster.

### 2.2 Key Components
- **Kafka (KRaft)**: Acts as the central nervous system, decoupling services.
- **Qdrant & MinIO**: The "Long-Term Memory" of the AI, storing vector embeddings and raw runbooks.
- **Prometheus & Alertmanager**: The "Senses", detecting anomalies.

---

## 3. Design Decisions

### Why Event-Driven?
We chose Kafka to separate concerns. The **Ingest** service doesn't need to know who consumes the alert. This allowed us to plug in the **Router** later without changing the Ingest service. It also handles backpressure if the AI Agent is slow.

### Why "Self-Contained" Helm Chart?
A major goal was "drop-in" capability. We rejected the idea of requiring users to manually upload runbooks. Instead, we:
- **Packaged Runbooks** directly into the Chart.
- Used a **Kubernetes Job** (`init-runbooks`) to automatically hydrate the Knowledge Base on install.
- Result: The system arrives "smart" out of the box.

### Why Retrieval-Augmented Generation (RAG)?
AI Models hallucinate. By forcing the Agent to retrieve a specific **Runbook** (e.g., `k8s_crashloop.md`) before analyzing, we ground the AI's reasoning in verified engineering practices, increasing safety and trust.

---

## 4. Helm Chart Deep Dive

The Helm chart (`deploy/helm/orchestrator`) is more than just deployment manifests. It is an automation engine:

- **Automated Brain Initialization**:
  - `runbooks-configmap.yaml`: Uses Helm's `.Files.Glob` to inline markdown files.
  - `init-job.yaml`: A `post-install` hook that waits for MinIO/Qdrant to be ready, then runs the ingestion script using the shared `ai-agent` image.
- **Dynamic Configuration**:
  - `secrets.yaml`: Injects sensitive data (Gemini Key) securely.
  - `rest.InClusterConfig`: We patched services to auto-detect if they are running inside a Pod versus Local Dev.

---

## 5. Engineering Challenges & Solutions ("War Stories")

### Challenge 1: The "No Such File" K8s Client Error
**Problem**: When moving to production (Helm), services failed with `/root/.kube/config: no such file`.
**Context**: Our Go code prioritized looking for a local kubeconfig file, assuming a developer environment.
**Solution**: We refactored `InitK8sClient` in both Router and Executor to fall back to `rest.InClusterConfig()`. This allows the services to seamless authenticate using the Pod's ServiceAccount when deployed.

### Challenge 2: The "TargetDown" Alert Mystery
**Problem**: During verification, Prometheus wasn't firing alerts even when we broke a target.
**Context**: We discovered that if a Pod target disappears entirely (Service Discovery drop), the `up` metric disappears rather than becoming `0`.
**Solution**: We explicitly created a "broken" target (Pod running but port closed) to force the `up=0` state, confirming the alert flow.

### Challenge 3: "Drop-In" Runbook Ingestion
**Problem**: The initial implementation required a manual `kubectl exec` script to upload runbooks. This wasn't user-friendly.
**Solution**: We implemented the **Init Job** pattern.
- *Hurdle*: The script required `GEMINI_API_KEY` even for ingestion (code dependency).
- *Fix*: We updated the Job template to inject the Secret, ensuring the script ran successfully without manual intervention.

### Challenge 4: Alertmanager Connectivity
**Problem**: Alertmanager webhooks weren't reaching the Ingest service.
**Solution**: We debugged the network path using `wget` from within the pod, identified correct Service DNS names, and verified the JSON payload structure matched what Ingest expected.

---

## 6. Future Improvements
1. **Persistence**: Move from `emptyDir` to PVCs for Runbook/Vector storage to survive restarts.
2. **Ingest Auth**: Add API Key protection to the `/ingest` endpoint.
3. **Rich Slack/Teams Integration**: Allow human approval steps via ChatOps.
