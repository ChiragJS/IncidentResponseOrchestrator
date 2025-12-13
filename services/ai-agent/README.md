# AI Agent Service

The AI Agent is the intelligent core of the Incident Response Orchestrator. It uses Retrieval-Augmented Generation (RAG) with Gemini 2.5 Flash to analyze incidents and propose remediation actions.

## Responsibility

- Consume domain events from `events.{domain}` topics
- Retrieve relevant runbooks using vector search (Qdrant)
- Fetch full runbook content from MinIO
- Analyze incidents using Gemini LLM
- Propose structured remediation actions
- Publish decisions to `decisions.{domain}` topics

## RAG Pipeline

```
Event → Qdrant (Vector Search) → MinIO (Full Content) → Gemini → Decision
```

## Supported Features

- [x] Kafka consumer/producer integration
- [x] Qdrant vector database for semantic search
- [x] MinIO document store for runbook content
- [x] Gemini 2.5 Flash LLM integration
- [x] Structured JSON output parsing
- [x] Confidence scoring (0.0 - 1.0)
- [x] Strict action schema enforcement

### Supported Action Types

| Action Type                | Description                          |
|---------------------------|--------------------------------------|
| `restart_pod`             | Delete a pod to trigger restart      |
| `scale_deployment`        | Scale deployment replicas up/down    |
| `rolling_restart_deployment` | Trigger rolling restart via annotation |

## Not Yet Implemented

- [ ] **Multi-LLM Support**: Gemini only (no OpenAI/Claude fallback)
- [ ] **Streaming Responses**: Full response buffering
- [ ] **Context Window Management**: No token limit handling
- [ ] **Human-in-the-Loop**: No approval workflow for high-risk actions
- [ ] **Feedback Loop**: No learning from action outcomes
- [ ] **Cost Tracking**: No LLM API cost monitoring

## Runbook Ingestion

Use the ingestion script to populate the knowledge base:

```bash
docker exec deploy-ai-agent-1 python3 src/scripts/ingest_runbooks.py /app/runbooks
```

### Supported Runbook Formats

- Markdown (`.md`)
- Plain Text (`.txt`)
- PDF (`.pdf`)
- JSON (`.json`)
- YAML (`.yaml`)

## Configuration

| Environment Variable | Default        | Description                |
|---------------------|----------------|----------------------------|
| `KAFKA_BROKER`      | `localhost:9092` | Kafka bootstrap servers   |
| `GEMINI_API_KEY`    | *required*     | Google AI API key          |
| `QDRANT_HOST`       | `qdrant`       | Qdrant server hostname     |
| `MINIO_ENDPOINT`    | `minio:9000`   | MinIO server endpoint      |
| `MINIO_ROOT_USER`   | `minioadmin`   | MinIO access key           |
| `MINIO_ROOT_PASSWORD` | `minioadmin` | MinIO secret key           |

## Tech Stack

- **Language**: Python 3.10+
- **LLM**: Google Gemini 2.5 Flash
- **Vector DB**: Qdrant
- **Object Store**: MinIO
- **Messaging**: Kafka (confluent-kafka-python)
