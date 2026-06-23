# Technical Implementation Notes

## Architecture Style

- Django MVT only for frontend rendering.
- Service-layer pattern for business rules.
- Strategy pattern for lead distribution.
- Database-driven policy engine.
- Audit-first design for sensitive events.
- Dynamic permissions with group templates and user overrides.
- Tenant-specific webhooks for self-service Meta Ads linkage through Make/Zapier.

## Background Services

- Celery Beat schedules repeated jobs.
- Celery Worker executes SLA, reminder, and email jobs.
- SLA jobs are idempotent by row status and database locking.
- Webhook processing is idempotent by endpoint + idempotency key.
- Email sending uses EmailOutbox to avoid losing emails when SMTP fails.

## Notification Types

Seeded notification types include lead assignment, SLA warnings, manual reassignment requirements, reminders, campaign approval statuses, webhook failures, permission changes, and policy changes.

## Extension Points

- Add new distribution strategies in `apps/distribution/strategies.py`.
- Add new company policies in `seed_crm_defaults.py` or through DB admin screens.
- Add new templates under each app's `templates/<app>/` folder.
- Add new permissions to `PERMISSION_CATALOG` and rerun the seed command.
