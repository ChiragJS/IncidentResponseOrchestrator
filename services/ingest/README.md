# Ingest Service

The Ingest Service is the entry point for all external alerts and events into the Incident Response Orchestrator.

## Responsibility

- Receive raw alerts via a REST API endpoint
- Normalize incoming data into a standard `NormalizedEvent` protobuf format
- Publish normalized events to the `events.normalized` Kafka topic

## API Endpoints

| Method | Endpoint   | Description                     |
|--------|------------|---------------------------------|
| POST   | `/ingest`  | Receive and queue a new alert   |
| GET    | `/health`  | Health check endpoint           |
| GET    | `/metrics` | Prometheus metrics endpoint     |

### Request Format

```json
{
  "source": "prometheus",
  "service_name": "kafka-ingest",
  "alert": "KafkaConsumerLagHigh",
  "description": "Consumer group lag is 25000 messages"
}
```

### Response Format

```json
{
  "event_id": "uuid",
  "status": "queued"
}
```

## Supported Features

- [x] HTTP REST API for alert ingestion
- [x] JSON payload parsing (flexible schema)
- [x] Event ID generation (UUID v4)
- [x] Kafka producer integration
- [x] Protobuf serialization (protojson)
- [x] **Prometheus metrics** (`/metrics` endpoint)
- [x] **Health check endpoint** (`/health`)
- [x] **Debug logging** of raw payloads
- [x] **Structured logging** with Zap

## Not Yet Implemented

- [ ] **Authentication**: No API key or OAuth support
- [ ] **Rate Limiting**: No protection against flood attacks
- [ ] **Webhook Signatures**: No verification of Alertmanager/Prometheus webhooks
- [ ] **Batch Ingestion**: Single event per request only
- [ ] **Schema Validation**: Accepts any valid JSON

## Configuration

| Environment Variable | Default          | Description               |
|---------------------|------------------|---------------------------|
| `KAFKA_BROKER`      | `localhost:9092` | Kafka bootstrap servers   |
| `PORT`              | `8080`           | HTTP server port          |

## Tech Stack

- **Language**: Go 1.21+
- **Framework**: Standard library `net/http`
- **Messaging**: Kafka (confluent-kafka-go)
- **Logging**: Zap (structured logging)
- **Metrics**: Prometheus client
