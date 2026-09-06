# Validation Evidence

**Scope:** self-owned local n8n reliability sandbox. No customer systems, credentials, or production writes.

## Runtime

- n8n: `2.36.9`
- Node.js: `24.20.0`
- bound locally to `127.0.0.1:5678`
- isolated user folder for the proof runtime

## Executed cases

| Case | Input condition | Expected result | Observed result |
|---|---|---|---|
| Happy path | complete synthetic event | `processed`, HTTP 200 | PASS |
| Duplicate | same successful `event_id` repeated | `duplicate_ignored`, HTTP 200 | PASS |
| Human review | missing `customer_id` | `review_required`, HTTP 202 | PASS |
| Failure | `simulate_failure=true` | `retryable_failure`, HTTP 503 | PASS |
| Retry | same failed event, failure flag removed | `processed`, HTTP 200 | PASS |

The final case demonstrates that a failed downstream attempt did not poison the idempotency key.

## Import / export check

The workflow imported successfully, expected nodes/connections were present, and a post-validation export matched material workflow behavior. One explicit default field was omitted by n8n on export; observed responses matched the intended default behavior.

## Evidence limits

This proof does not claim:
- external API behavior inside this workflow;
- production availability or scale;
- customer-data handling;
- a completed client deployment.

It is deliberately narrow: reliable control flow, failure semantics, idempotency and review routing.
