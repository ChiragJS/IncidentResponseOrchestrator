# Redis High Latency / Eviction Runbook

**Severity**: High
**Service**: Cache / Redis
**Keywords**: redis, cache, latency, eviction, slow

## Symptoms
-   Alert: `RedisHighLatency` (> 50ms avg).
-   Alert: `RedisMemoryfragmentation` or `RedisEvictedKeys` spiking.
-   Application performance degrades; higher load on primary DB.

## Root Causes
1.  **Memory Full**: Redis reached `maxmemory`; spending CPU on evicting keys.
2.  **Slow Commands**: Usage of `KEYS *`, `HGETALL` on large hashes.
3.  **Single Thread Saturation**: High operation rate saturating the single Redis thread.
4.  **Network**: Bandwidth limit reached.

## Troubleshooting Steps
1.  **Check Slowlog**:
    `redis-cli slowlog get 10`
    - Look for O(N) commands.

2.  **Check Memory**:
    `redis-cli info memory`
    - Check `evicted_keys` and `used_memory_human`.

## Remediation Actions
-   **Scale Cache**: Increase memory limit if valid data growth.
    *Action*: (Requires config change/restart).
-   **Flush All**: (Dangerous) If cache is corrupted or filled with garbage.
    *Action*: (Manual approval required) `FLUSHALL`
-   **Restart Pod**: Clears memory (if not using AOF/RDB persistence).
    *Action*: `restart_pod` (Target: `<redis-pod-name>`)
