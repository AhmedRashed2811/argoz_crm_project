# Argoz CRM — Django MVT Detailed UI Project

This project is a Django MVT implementation of the Argoz Real Estate CRM specifications. It is intentionally template-rendered, not frontend REST-based. The frontend now includes detailed UI screens for lead creation, source-specific rules, marketing campaign type creation, user/group/permission assignment, policy configuration, SLA monitoring, notifications, integrations, audit, and reports.

## What changed in this detailed UI version

- Professional responsive layout with sidebar, cards, tables, tabs, stepper workflows, live badges and sticky summaries.
- SweetAlert2 confirmation and toast feedback.
- Async AJAX helpers through `static/js/crm_ui.js`.
- Django URL reversing everywhere in templates through `{% url %}`.
- Full campaign builder UI for all marketing types:
  - Events
  - TV Ads
  - Street Ads
  - Social Media Ads
  - Exhibitions
  - Other Costs
- Dynamic repeatable frontend sections for:
  - Event celebrities, giveaways and catering
  - TV channels and slots
  - Street ad type/location lines
  - Social platform budgets
  - Exhibition records
  - Other costs
- Improved lead creation wizard with source-specific sections for:
  - Self Generated
  - Campaign
  - Broker
  - Walk-in
  - Call Center
  - Exhibition
  - Referral
  - Existing Client
- Improved user creation UX:
  - Role/group cards by business type
  - Async preview of inherited group permissions
  - Direct permission checkboxes grouped by module
  - Supports cross-module permissions: for example, a Sales Head can receive Marketing Member permissions.
- Policy console for company-configured behavior.
- Notification center with types, reminders and email outbox preview.
- SLA monitor screen for background expiry processing.
- Tenant-specific integrations screens for dynamic Make/Zapier webhooks.

## Technical architecture

- Django MVT, rendered templates.
- Service-layer pattern for lead creation, distribution, SLA, notifications, campaigns, budgets and approvals.
- Strategy pattern for lead distribution:
  - `round_robin_load_balanced`
  - `by_turn`
  - `retry_team_escalation`
  - `manual_assignment`
- Database-driven policies through `PolicyDefinition`, `PolicyOption`, and `CompanyPolicy`.
- Flexible authorization using Django groups and direct user permissions.
- Background jobs via Celery + Redis:
  - SLA expiry checks
  - reminder sending
  - email outbox delivery
- Real-time-ready notifications using Django Channels.
- MariaDB/MySQL database configuration already included.

## Database configuration

The project is configured for MariaDB/MySQL:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'argoz_crm',
        'USER': 'root',
        'PASSWORD': '',
        'HOST': '127.0.0.1',
        'PORT': '3306',
    }
}
```

## Run guide

### 1. Extract the ZIP

```bash
unzip Argoz_CRM_Django_MVT_Project_Detailed_UI.zip
cd argoz_crm_project_detailed_ui
```

### 2. Create and activate virtual environment

Windows PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
python -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

If `mysqlclient` fails on Windows, install Microsoft C++ Build Tools or use a compatible wheel.

### 4. Create the database

Open MySQL/MariaDB and run:

```sql
CREATE DATABASE argoz_crm CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 5. Apply migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### 6. Seed default CRM data

```bash
python manage.py seed_crm_defaults
```

Default login:

```text
Email: admin@argoz.local
Password: Admin@12345
```

### 7. Run Django

```bash
python manage.py runserver
```

Open:

```text
http://127.0.0.1:8000/
```

### 8. Run background services

Start Redis, then open separate terminals:

```bash
celery -A argoz_crm worker -l info
```

```bash
celery -A argoz_crm beat -l info
```

## Suggested testing flow

1. Login with the seeded admin user.
2. Open **Users & Permissions**.
3. Create a Sales Head user and also select some Marketing permissions.
4. Open **Campaign Builder**.
5. Select multiple campaign types and add records under each type.
6. Save campaign and open its details page.
7. Open **Create Lead**.
8. Test every lead source and watch dynamic sections appear.
9. Assign a lead manually or automatically.
10. Open SLA Monitor, Notification Center and Audit Logs.

## Important note

This project provides a strong implementation scaffold and a detailed template-driven UI. Some production concerns still need final hardening before go-live, such as advanced field-level validation, test coverage, deployment configuration, user onboarding emails, production storage, advanced analytics, and native Meta App Review integration if you decide to remove Make/Zapier later.
