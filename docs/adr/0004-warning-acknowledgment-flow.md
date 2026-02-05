# ADR-0004: Validation Warning Acknowledgment Flow

## Status
Accepted

## Context
Validators can have severity `error` (blocks save) or `warning` (informational). Warnings should:
- Be shown to the user before save completes
- Require explicit acknowledgment
- Prevent accidental bypass

## Decision
We will implement a token-based acknowledgment flow.

### Flow

```
1. Client submits: POST /entities/contract
   Body: { data: {...} }

2. Server validates, finds warnings (no errors)

3. Server responds: HTTP 202 Accepted
   {
     "valid": true,
     "requiresAcknowledgment": true,
     "warnings": [
       { "field": "discount", "message": "Discount exceeds typical range", "code": "HIGH_DISCOUNT" }
     ],
     "acknowledgmentToken": "abc123"
   }

4. Client shows warnings to user, user confirms

5. Client re-submits: POST /entities/contract
   Body: {
     "data": {...},
     "acknowledgeWarnings": "abc123"
   }

6. Server re-validates:
   - If new errors exist: HTTP 422 with errors
   - If warnings still present and token valid: proceed to save
   - If token invalid/expired: HTTP 422, request new acknowledgment

7. Server responds: HTTP 201 Created
   { "data": {...} }
```

### Token Properties
- **Short-lived**: 5-minute expiration
- **Single-use**: Invalidated after successful save
- **Content-bound**: Token is hash of (entity, record data, warnings)
  - If data changes between submissions, token is invalid
  - Ensures user acknowledged *these specific* warnings for *this specific* data

### HTTP Status Codes

| Scenario | Status | Response |
|----------|--------|----------|
| Validation errors | 422 | `{ valid: false, errors: [...], warnings: [...] }` |
| Warnings only, no token | 202 | `{ valid: true, requiresAcknowledgment: true, warnings: [...], acknowledgmentToken: "..." }` |
| Warnings + valid token | 201 | `{ data: {...} }` |
| Warnings + invalid/expired token | 422 | `{ valid: false, errors: [{ code: "INVALID_ACKNOWLEDGMENT", message: "Please review warnings again" }] }` |
| No issues | 201 | `{ data: {...} }` |

### Token Generation

```python
import hashlib
import time
import secrets

def generate_acknowledgment_token(
    entity: str,
    record: dict,
    warnings: list[ValidationError],
    secret_key: str,
    ttl_seconds: int = 300
) -> str:
    expires_at = int(time.time()) + ttl_seconds

    # Content hash ensures token is bound to this specific submission
    content = f"{entity}:{json.dumps(record, sort_keys=True)}:{json.dumps([w.code for w in warnings], sort_keys=True)}"
    content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

    # Token format: expiry.content_hash.signature
    payload = f"{expires_at}.{content_hash}"
    signature = hashlib.sha256(f"{payload}.{secret_key}".encode()).hexdigest()[:16]

    return f"{payload}.{signature}"

def verify_acknowledgment_token(
    token: str,
    entity: str,
    record: dict,
    warnings: list[ValidationError],
    secret_key: str
) -> bool:
    try:
        expires_at, content_hash, signature = token.split(".")

        # Check expiration
        if int(expires_at) < time.time():
            return False

        # Verify signature
        payload = f"{expires_at}.{content_hash}"
        expected_sig = hashlib.sha256(f"{payload}.{secret_key}".encode()).hexdigest()[:16]
        if signature != expected_sig:
            return False

        # Verify content hash matches current data
        content = f"{entity}:{json.dumps(record, sort_keys=True)}:{json.dumps([w.code for w in warnings], sort_keys=True)}"
        expected_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        if content_hash != expected_hash:
            return False

        return True
    except:
        return False
```

### Frontend Behavior

```typescript
async function saveEntity(entity: string, data: Record<string, any>) {
  const response = await api.post(`/entities/${entity}`, { data });

  if (response.status === 422) {
    // Show errors, block save
    showErrors(response.data.errors);
    return;
  }

  if (response.status === 202 && response.data.requiresAcknowledgment) {
    // Show warning dialog
    const proceed = await showWarningDialog(response.data.warnings);

    if (proceed) {
      // Re-submit with acknowledgment
      const finalResponse = await api.post(`/entities/${entity}`, {
        data,
        acknowledgeWarnings: response.data.acknowledgmentToken
      });

      if (finalResponse.status === 201) {
        showSuccess("Saved successfully");
      } else {
        // Token expired or new errors - show new issues
        showErrors(finalResponse.data.errors);
      }
    }
    return;
  }

  if (response.status === 201) {
    showSuccess("Saved successfully");
  }
}
```

## Consequences

### Positive
- Users cannot accidentally bypass warnings
- Token binding prevents replay attacks
- Re-validation on acknowledgment catches changes
- Clear HTTP semantics (202 for "accepted but pending")

### Negative
- Additional round-trip for warnings
- Token management adds complexity
- 5-minute TTL may frustrate slow users

### Alternatives Considered
- **Simple flag**: `acknowledgeWarnings: true` without token
  - Rejected: No guarantee user saw current warnings
- **Session-based**: Store warnings in session
  - Rejected: Doesn't work for API-only clients
- **Warnings don't block**: Just return warnings with saved data
  - Rejected: User requirement for explicit acknowledgment
