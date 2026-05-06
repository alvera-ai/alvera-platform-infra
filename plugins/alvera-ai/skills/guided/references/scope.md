# Scope

## In scope

| Resource                | Operations                                  |
|-------------------------|---------------------------------------------|
| `datalakes`             | list, get, create, upload-link              |
| `dataSources`           | list, create, update                        |
| `tools`                 | list, get, create, update, delete           |
| `genericTables`         | list, create (with compliance gate + profiling) |
| `actionStatusUpdaters`  | list, create, update                        |
| `aiAgents`              | list, get, create, update, delete           |
| `connectedApps`         | list, get, create, update, syncRoutes       |
| `agenticWorkflows`      | list, get, create, update, delete, execute, run, batch-logs |
| `interopContracts`      | list, get, create, update, delete, run      |
| `dataActivationClients` | list, get, create, update, delete, run-manually, ingest, ingest-file, logs |
| `datasets`              | search, metadata (read-only monitoring)     |
| `mdm`                   | verify (read-only identity resolution)      |
| `ping`                  | health check                                |
| `init`                  | `connected-app`, `infra-setup` (scaffolding)|

## Out of scope (refuse)

- Tenant create / delete (admin-only)
- Datalake **delete** / **update** — the API doesn't expose them.
  Offer to create a new one instead.
- Connected app **page management** — `connected-apps resolve-page` and
  `connected-apps update-message-tracking` are runtime page rendering,
  not provisioning. CRUD + `sync-routes` on connected app resources are in
  scope; page-level endpoints are not.
- Connected app **UI/hosting** — this skill creates the connected app
  *resource* on Alvera (registers URL, syncs routes), but does NOT build
  or host the actual frontend. Frontend app development is a separate
  skill/concern. This skill is data pipeline + backend infrastructure.
- **Invite / team management** — team invites are a domain-specific
  concern handled by the `/healthcare` skill's phase walk, not a general
  provisioning operation. Not available via `/guided`.
- Anything touching another tenant
- Anything not listed in "In scope"

## MDM verify

`alvera mdm verify <datalake> [tenant] --body '<json>'` resolves a
patient identity against the master data model. Body:

```json
{
  "resource_type": "patient",
  "identifier": [{"system": "urn:emr:patient-id", "value": "<patient_id>"}]
}
```

Response contains the resolved patient record (regulated + unregulated
views). Use to verify patient data landed correctly after DAC ingestion.

## Refusal language

When asked for an out-of-scope operation, reply verbatim:

> "I can only set up resources within an existing tenant + datalake. For
> tenant or datalake provisioning, contact your Alvera admin."

If the user pushes back, do not negotiate. Do not invent workarounds.
Do not invoke the CLI for operations not listed in "In scope".
