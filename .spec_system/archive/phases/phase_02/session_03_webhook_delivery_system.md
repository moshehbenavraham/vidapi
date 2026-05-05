# Session 03: Webhook Delivery System

**Session ID**: `phase02-session03-webhook-delivery-system`
**Status**: Not Started
**Estimated Tasks**: ~18
**Estimated Duration**: 3-4 hours

---

## Objective

Implement webhook callback delivery with HMAC-SHA256 payload signing, exponential backoff retry, and a full delivery audit trail so clients receive reliable notifications on render completion, failure, and cancellation.

---

## Scope

### In Scope (MVP)
- SQLModel `webhook_attempts` table: id, render_id, event, url, status_code, response_body_excerpt, attempt_number, scheduled_at, delivered_at, error
- Webhook service with async delivery via httpx
- HMAC-SHA256 payload signing with configurable secret
- Timestamp and signature headers on webhook requests
- Webhook events: render.succeeded, render.failed, render.cancelled
- Exponential backoff retry: 3 attempts at 1s, 10s, 60s delays
- Store every delivery attempt for audit
- Non-blocking delivery: never block render completion on webhook
- Webhook payload format per PRD specification
- Integration with worker pipeline: dispatch webhook after terminal status

### Out of Scope
- Webhook management endpoints (future phase)
- Custom webhook headers or authentication beyond HMAC
- Webhook event filtering or subscription management

---

## Prerequisites

- [ ] Session 02 complete (template rendering pipeline)
- [ ] Render pipeline reaches terminal states reliably

---

## Deliverables

1. WebhookAttempt database model
2. Webhook service with signing and delivery logic
3. Retry mechanism with exponential backoff
4. Worker integration for webhook dispatch on terminal status
5. Webhook payload construction per PRD spec

---

## Success Criteria

- [ ] Webhook fires on render.succeeded with correct payload
- [ ] Webhook fires on render.failed and render.cancelled
- [ ] Payloads are signed with HMAC-SHA256 and include timestamp header
- [ ] Failed deliveries retry up to 3 times with 1s, 10s, 60s delays
- [ ] Every delivery attempt is stored in webhook_attempts table
- [ ] Webhook delivery never blocks render status updates
