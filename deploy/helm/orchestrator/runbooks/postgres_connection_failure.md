# Postgres Connection Failure Runbook

**Severity**: Critical
**Service**: Database / PostgreSQL
**Keywords**: postgres, db, connection refused, timeout, 5432

## Symptoms
- Application logs show `FATAL: remaining connection slots are reserved for non-replication superuser connections`.
- Logs show `dial tcp <ip>:5432: connect: connection refused`.
- Application returns 500 errors.

## Root Causes
1.  **Max Connections Reached**: Too many active connections (connection leak in app).
2.  **Database Down**: The Postgres process crashed or the pod was evicted.
3.  **Network Policy**: Firewall or NetworkPolicy blocking access from the app namespace.
4.  **Credentials**: Password rotation failed or config is stale.

## Troubleshooting Steps
1.  **Check Pod Status**:
    `kubectl get pods -l app=postgres`
    - Is it Running? Is it ready?

2.  **Check Logs**:
    `kubectl logs -l app=postgres`
    - Look for panic, OOM, or auth errors.

3.  **Check Connections (if accessible)**:
    - Exec into pod: `psql -U postgres -c "SELECT count(*) FROM pg_stat_activity;"`

## Remediation Actions
-   **Restart Database**: A restart clears all connections.
    *Action*: `restart_pod` (Target: `<postgres-pod-name>`)
-   **Kill Idle Connections**: (Requires script)
-   **Scale Connection Pooler**: If using pgbouncer, increase replicas.
