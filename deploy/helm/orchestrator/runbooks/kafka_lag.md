# Kafka Consumer Lag Runbook

**Severity**: High
**Service**: Kafka / Consumer Groups
**Keywords**: kafka, lag, latency, consumer

## Symptoms
- Alert triggered: `KafkaConsumerLagHigh`
- Delayed processing of events in downstream services.
- `kafka_consumer_group_lag` metric spiking > 10,000.

## Root Causes
1.  **High Load**: Sudden spike in producer throughput.
2.  **Slow Consumer**: Processing logic in consumer is taking too long (e.g., DB formatting, external API calls).
3.  **Rebalancing**: Frequent consumer group rebalances causing stop-the-world pauses.
4.  **Pod Crash**: One or more consumer pods crashed, leaving fewer consumers than partitions.

## Troubleshooting Steps
1.  **Check Consumer Logs**:
    -   Look for errors or timeouts.
    -   Check for "rebalancing" messages.
    `kubectl logs -l app=ingest-service` (or relevant consumer)

2.  **Check Resource Usage**:
    -   Is the consumer pod CPU/Memory throttled?
    `kubectl top pod -l app=ingest-service`

3.  **Check Kafka Broker**:
    -   Are brokers healthy?
    -   Is there network saturation?

## Remediation Actions
-   **Scale Consumers**: High lag usually indicates the consumers cannot keep up with the load.
    *Action*: `kubectl scale deployment <deployment-name> --replicas=<n+1>`
-   **Restart Consumer**: If the consumer is stuck in a dead-lock or zombie state.
    *Action*: `restart_pod` (Target: `<pod-name>`)
-   **Optimize**: If code is slow, this requires a code fix (hotfix).
