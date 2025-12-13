# Disk Space Low Runbook

**Severity**: High
**Service**: Infrastructure / Storage
**Keywords**: disk, storage, filesystem, no space left on device

## Symptoms
-   Alert: `DiskSpaceLow` (< 10% free).
-   Application fails to write logs or temp files (`IOException: No space left on device`).
-   Database panic / switching to read-only mode.

## Root Causes
1.  **Log Rotation Failed**: Logs filling up `/var/log`.
2.  **Core Dumps**: Application crashing and dumping large files.
3.  **PVC Full**: Persistent volume claimed size is matched by data growth.
4.  **Temp Files**: App creating temp files without cleanup.

## Troubleshooting Steps
1.  **Check Usage**:
    `df -h` inside the pod/node.
    `du -sh * | sort -hr | head -n 10` (Find largest directories)

2.  **Check PVC**:
    `kubectl get pvc`

## Remediation Actions
-   **Clean Logs**: Truncate log files.
    *Action*: (Requires shell access) `> /path/to/large.log`
-   **Restart Pod**: Clears `/tmp` (if ephemeral storage).
    *Action*: `restart_pod` (Target: `<pod-name>`)
-   **Expand PVC**: Edit PVC size and apply (if StorageClass supports expansion).
