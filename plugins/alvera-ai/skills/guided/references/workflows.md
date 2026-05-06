# Workflows

Build, test, and validate event-driven automation workflows. Includes
production-grade templates, Liquid variable reference, and execution
debugging.

## Workflow creation flow

### Step 1: Understand the use case

Ask:

> "What should this workflow automate? For example:
>   - Send a review SMS after appointments
>   - Send an age-aware survey to patients 65+
>   - Trigger a REST API call when new patients are ingested
>   - Something custom
>
> I have production-grade templates for the first two."

Match to a template if possible. Otherwise, build from scratch.

### Step 2: Auto-detect available resources

```bash
alvera --profile <p> tools list [tenant]
alvera --profile <p> ai-agents list <datalake> [tenant]
alvera --profile <p> connected-apps list <datalake> [tenant]
```

Surface what's available. If a required resource is missing, create it
first (per the dependency chain in `outcomes.md`).

### Step 3: Build the workflow

#### Template-based

Load template (see below). Present customisation points as a checklist.
Fill in answers, generate the full workflow body.

#### Custom build — elicitation passes

- **Pass 1 — identity**: name, description, dataset_type,
  generic_table_id (if needed), status (default `draft`)
- **Pass 2 — filter** (optional): what records should enter. Offer common
  patterns (source_uri gate, recency gate, age gate).
- **Pass 3 — decision**: auto-generate static decision for simple
  workflows, or ask what determines which action fires.
- **Pass 4 — context datasets** (optional): additional data before
  decision (e.g. prior messages for dedup).
- **Pass 5 — actions**: walk through each. For each:
  decision_key, action_type, tool, trigger_template, idempotency_template,
  runtime_filter, tool_call, connected app integration, action_window.
- **Pass 6 — AI agents** (optional): attach agents for enrichment.

### Step 4: Create in draft

```bash
alvera --profile <p> workflows create <datalake> [tenant] \
  --body-file /tmp/workflow.json
```

Always start as `draft`. Never auto-promote.

### Step 5: Dry-run test

```bash
alvera --profile <p> workflows run <slug> [tenant] \
  --body '{"sql_where_clause":"1=1 LIMIT 1","mode":"dry_run"}'
```

Auto-run after creation — don't ask permission.

### Step 6: Interpret logs

```bash
alvera --profile <p> workflows workflow-logs <slug> [tenant]
```

| Status | Meaning | Next step |
|--------|---------|-----------|
| `completed` | Full pipeline passed | Ready to promote |
| `filtered` | filter_config rejected | Check filter logic |
| `failed` | Execution error | Surface error, fix template |
| `partial` | Some actions failed | Check individual action logs |

Action-level status: `completed`, `skipped` (runtime filter or idempotency
dedup), `scheduled` (future trigger), `failed`.

### Step 7: Promote to live (on user confirmation)

```bash
alvera --profile <p> workflows update <datalake> <id> [tenant] \
  --body-file /tmp/workflow-live.json
```

Change `status` from `draft` to `live`. Confirm:
> "This will make the workflow respond to automated events. Promote to live? (y/n)"

Append to `alvera-<tenant-slug>.yaml` under `agentic_workflows:`.

## Hard constraints

- **Always create in draft first.** Never auto-promote.
- **Dry-run before live.** Always test before promoting.
- **Confirm before live execution.** `live` mode fires real SMS/API calls.
- **Idempotency is non-negotiable.** Every action must have
  `idempotency_template`. Minimum: `{{ patient_id }}-{{ decision_key }}`.
- **Filter semantics: `true` = proceed.** Opposite of "filter = skip".
- **Runtime filter: `true` = execute.** Same convention.
- **Don't hardcode phone numbers.** Use MDM telecom lookup.
- **Connected app URLs are magic links.** Use `{{ connected_app_form_url }}`.
- **PUT = full replace.** Updates require complete workflow body.

---

## Production templates

### Template A: Review SMS Workflow

After appointment, send review SMS. Includes: source URI gate, recency
gate (24h), 6-month dedup, phone guard, status guard, 3-hour delay.

Customisation points:

| Field | Default | Ask |
|-------|---------|-----|
| `source_uri` | `emr.my-practice.com` | "What's your source_uri?" |
| SMS delay | 3 hours | "Change delay?" |
| Dedup window | 6 months | "Change dedup?" |
| SMS body | Generic review | "Customise SMS?" |
| Connected app route | `/forms/review` | "Form route?" |
| Action window | None | "Delivery hours?" |

Full body: read `templates/review-sms.json`.

Replace: `__SOURCE_URI__`, `__DEDUP_WINDOW__`, `__TOOL_ID__`, `__DELAY__`,
`__CONNECTED_APP_ID__`, `__FORM_ROUTE__`, `__SMS_BODY__`.

If no connected app, remove `connected_app_id`, `connected_app_route`,
`connected_app_metadata_template`, and `{{ connected_app_form_url }}` from SMS body.

### Template B: Age-Aware Survey Workflow (CAHPS)

Survey SMS to patients 65+ one day after appointment. Adds: age gate,
1-day delay, delivery window, daily dedup.

Customisation points:

| Field | Default | Ask |
|-------|---------|-----|
| `source_uri` | `emr.my-practice.com` | "What's your source_uri?" |
| Age threshold | 65 | "Minimum age?" |
| SMS delay | 1 day | "Change delay?" |
| Dedup window | daily (today's date) | "Change dedup?" |
| SMS body | Generic survey | "Customise SMS?" |
| Connected app route | `/forms/cahps` | "Form route?" |
| Action window | None | "Delivery hours?" |

Full body: read `templates/cahps-survey.json`.

Replace: `__SOURCE_URI__`, `__AGE_THRESHOLD__`, `__TOOL_ID__`, `__DELAY__`,
`__CONNECTED_APP_ID__`, `__FORM_ROUTE__`, `__SMS_BODY__`.

Differences from Template A:
- Filter includes age gate (`birth_date | age >= threshold`)
- No context_datasets (no 6-month message dedup — uses daily idempotency instead)
- Idempotency uses today's date (`{{ "" | now | date: "%Y-%m-%d" }}`) for daily dedup
- Optional `action_window_start` / `action_window_end` (integer hours, e.g. 7 and 19 for 7 AM–7 PM)

### Template C: Minimal Workflow (scaffold)

Starting point for custom workflows. Read `templates/minimal-scaffold.json`.

Tool call types: `sms_request`, `restapi_request`, `s3_request`,
`aws_lambda_request`, `sftp_request`.

### Generic table workflows

When `dataset_type` is `generic_table`, the workflow fires on rows
inserted into a custom table. Additional requirements:

- `generic_table_id` is **required** in the workflow body.
- Filter and action templates use `generic_table_row.*` instead of
  `appointment.*` or `patient.*`.
- MDM output may not be available unless the table contains patient
  identifiers that can be resolved.
- Idempotency template should reference the table's unique column(s):
  `{{ generic_table_row.<unique_col> }}-{{ decision_key }}`.

Use Template C as the starting point. No production template exists for
generic table workflows — build custom via elicitation passes.

## Dataset types

Valid `dataset_type` values for workflows:

| Type | Event source | Primary variables |
|------|-------------|-------------------|
| `patient` | Patient record events | `patient.*`, `mdm_output.*` |
| `appointment` | Appointment events | `appointment.*`, `patient.*`, `mdm_output.*` |
| `generic_table` | Custom table inserts (requires `generic_table_id`) | `generic_table_row.*` |

If unsure which types are available, use `alvera workflows metadata`
to discover them — the API is authoritative.

---

## Liquid variables

### Variable availability by stage

| Variable | Filter | Decision | Action |
|----------|--------|----------|--------|
| `appointment.*` | yes | yes | yes |
| `patient.*` | yes | yes | yes |
| `mdm_output.*` | yes | yes | yes |
| `additional_context.*` | no | yes | yes |
| `patient_id` | yes | yes | yes |
| `checksum` | no | no | yes |
| `action_id` | no | no | yes |
| `decision_key` | no | no | yes |
| `connected_app_form_url` | no | no | yes (if configured) |
| `timezone` | yes | yes | yes |

### Common appointment fields

```liquid
{{ appointment.start }}
{{ appointment.end_time }}
{{ appointment.status }}
{{ appointment.source_uri }}
{{ appointment.minutes_duration }}
{{ appointment.unregulated_appointment_id }}
{{ appointment.identifier[0].value }}
{{ appointment.location_participants[0].location.name }}
```

### Patient fields (via MDM)

```liquid
{{ mdm_output.patient.id }}
{{ mdm_output.regulated_patient.birth_date }}
{{ mdm_output.regulated_patient.gender }}
{{ mdm_output.regulated_patient.name[0].given[0] }}
{{ mdm_output.regulated_patient.name[0].family }}
{{ mdm_output.regulated_patient.identifier[0].value }}
```

### Telecom lookup

```liquid
{% assign phone = mdm_output.regulated_patient.telecom
  | where: "system", "phone" | map: "value" | first %}
{{ phone }}
```

**SMS `to` field requires E.164 format** (`+15551234567`). If the phone
from MDM doesn't include the country code, normalize in the template:

```liquid
{% assign phone = mdm_output.regulated_patient.telecom
  | where: "system", "phone" | map: "value" | first %}
{% assign clean = phone | strip | remove: "-" | remove: "(" | remove: ")" | remove: " " %}
{% if clean.size == 10 %}+1{{ clean }}{% else %}{{ clean }}{% endif %}
```

### Common patterns

**Date formatting:**
```liquid
{{ appointment.start | date: "%Y-%m-%d" }}
```

**Date arithmetic:**
```liquid
{{ appointment.start | date: "%Y-%m-%d %H:%M:%S", "add", "3 hours", timezone }}
{{ appointment.end_time | date: "%Y-%m-%d %H:%M:%S", "add", "7 days", timezone }}
```

**Date arithmetic — use days, not months.** `"12 months"` silently returns
empty. Use `"365 days"` instead. Valid units: `hours`, `days`. Not `months`.

```liquid
{{ appointment.start | date: "%Y-%m-%d", "subtract", "365 days" }}
```

**Age calculation:**
```liquid
{% assign patient_age = mdm_output.regulated_patient.birth_date | age %}
{% if patient_age >= 65 %}true{% endif %}
```

**Recency gate (last 24h):**
```liquid
{% assign appt_date = appointment.start | date: "%Y-%m-%d" %}
{% assign cutoff = "" | now | date: "%Y-%m-%d", "subtract", "24 hours" %}
{% if appt_date >= cutoff %}true{% endif %}
```

**Phone guard:**
```liquid
{% assign phone = mdm_output.regulated_patient.telecom
  | where: "system", "phone" | map: "value" | first %}
{% if phone and phone != "" %}true{% endif %}
```

**Status guard:**
```liquid
{% if appointment.status == "fulfilled"
  or appointment.status == "arrived"
  or appointment.status == "checked_in" %}true{% endif %}
```

**Prior message dedup:**
```liquid
{% if additional_context.message.size == 0 %}true{% endif %}
```

**Combined guards in runtime_filter:**
```liquid
{% assign phone = mdm_output.regulated_patient.telecom
  | where: "system", "phone" | map: "value" | first %}
{% if phone and phone != "" %}
  {% if additional_context.message.size == 0 %}
    {% if appointment.status == "fulfilled" or appointment.status == "arrived"
      or appointment.status == "checked_in" %}true{% endif %}
  {% endif %}
{% endif %}
```

### Bracket notation for spaced keys

If the dataset has columns with spaces (e.g. from a CSV with human-readable
headers), use bracket notation in Liquid templates:

```liquid
{{ generic_table_row["Patient First Name"] }}
{% if generic_table_row["Visit Status"] == "CHK" %}true{% endif %}
```

**Bracket notation is case-sensitive.** The key must match the column name
exactly as stored. Dot notation on spaced keys causes a parse error.

### Filter vs runtime_filter semantics

Both output `"true"` to **proceed**:

| Template | `"true"` means | Empty/nil means |
|----------|----------------|-----------------|
| `filter_config` | Record enters pipeline | Record filtered out |
| `runtime_filter` | Action executes | Action skipped |

---

## Execution and debugging

### Execute vs run-workflow

| | `/execute` | `/run-workflow` |
|---|---|---|
| Scope | Single action, one record | Bulk, SQL-filtered |
| Filter evaluated? | No | Yes |
| Decision evaluated? | No (you supply key) | Yes |

**Single-action:**
```bash
alvera workflows execute <slug> [tenant] \
  --body '{"dataset_id":"<uuid>","decision_key":"<key>","mode":"dry_run"}'
```

**Bulk run:**
```bash
alvera workflows run <slug> [tenant] \
  --body '{"sql_where_clause":"<where>","mode":"dry_run"}'
```

### SQL WHERE patterns

```sql
ri.value = 'EMR-APPT-12345'           -- by EMR ID
a.id = 'uuid-of-appointment'          -- by public UUID
ri.value IN ('appt-001', 'appt-002')  -- multiple records
a.start >= '2026-04-01' AND a.start < '2026-04-17'  -- date range
1=1 LIMIT 1                           -- single record for testing
```

### Checking logs

```bash
alvera workflows workflow-logs <slug>
alvera workflows workflow-log <slug> <id>
alvera workflows workflow-log-download <slug> <id>   # full execution context
```

### Debugging common issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| WEL `filtered` | filter didn't output `"true"` | Check filter logic |
| AEL `skipped` | Runtime filter or idempotency dedup | Check guards |
| `scheduled_count: 0` | decision_key doesn't match | Verify action keys |
| Action not executing | Future trigger_template | Check `scheduled_at` |
| `422` on create | Invalid Liquid or missing field | Check errors array |
| SMS not received | `dry_run` mode or action_window | Verify mode and window |

### Testing recipe

```bash
# 1. Create in draft
alvera workflows create <datalake> --body-file /tmp/workflow.json

# 2. Dry-run one record
alvera workflows run <slug> \
  --body '{"sql_where_clause":"1=1 LIMIT 1","mode":"dry_run"}'

# 3. Check log
alvera workflows workflow-logs <slug>

# 4. Promote to live (confirm first)
# Update status: "draft" → "live"
```
