# SSL/TLS Certificate Expiry Runbook

**Severity**: Critical
**Service**: Security / Ingress
**Keywords**: ssl, tls, certificate, expired, handshake failure

## Symptoms
-   Alert: `SSLCertificateExpiringSoon` (< 7 days).
-   Users see browser warnings ("Your connection is not private").
-   Webhooks/API calls fail with `x509: certificate has expired`.

## Root Causes
1.  **Auto-Renewal Failed**: Cert-manager or Let's Encrypt challenge failed.
2.  **Manual Oversight**: Manual certificate was not updated.
3.  **Secret Sync**: The new cert exists but wasn't synced to the Ingress secret.

## Troubleshooting Steps
1.  **Check Certificate**:
    `kubectl get certificate -A`
    - Look at `READY` and `EXPIRATION` columns.

2.  **Check Cert-Manager Logs**:
    `kubectl logs -l app=cert-manager -n cert-manager`

## Remediation Actions
-   **Delete Secret**: Forces cert-manager to re-issue (if configured correctly).
    *Action*: (Manual) `kubectl delete secret <cert-secret-name>`
-   **Restart Ingress Controller**: Sometimes required to pick up the new secret.
    *Action*: `restart_pod` (Target: `ingress-nginx-controller-<id>`)
