# Databricks Free Edition setup

`counter-copilot` uses Databricks as its **primary** data source (with SQLite as a transparent fallback). This is the "live warehouse" story documented in the architecture.

## Why Databricks (Option A in the plan)

- Demonstrates the agent talking to a real lakehouse, not a toy DB.
- Unity Catalog tags appear in every tool's `source` field — the trace panel proves the integration is live.
- If the Databricks warehouse is cold or rate-limited, the `FailoverSource` silently routes to SQLite. The demo never breaks; the trace just shows `source: sqlite(failover)` instead.

## One-time setup

1. Sign up at [databricks.com/learn/free-edition](https://www.databricks.com/learn/free-edition). No credit card required.
2. In your workspace, create a **Serverless SQL Warehouse**. Note its `Server Hostname` and `HTTP Path`.
3. Create a **Personal Access Token** under *User Settings → Developer*.
4. Import the notebook `databricks/notebooks/01_seed_delta.py` and run it once. It will:
   - Create catalog `counter_copilot` and schema `core`.
   - Create the six Delta tables (counters, counter_health, transactions, modules, counter_modules, field_notes).
   - Seed them from a CSV export of the local SQLite (uploaded as a workspace file).
5. Add the connection details to your Render service env vars:
   ```
   DATABRICKS_HOST=<server-hostname>
   DATABRICKS_HTTP_PATH=<http-path>
   DATABRICKS_TOKEN=<pat>
   DATABRICKS_CATALOG=counter_copilot
   DATABRICKS_SCHEMA=core
   ```

## Verifying the integration

After deploy, hit `/status` — `datasource_active` should be `failover` and `datasource_healthy: true`.
Then run any agent query and inspect the trace panel: each tool's `source` chip will read `databricks`. Disconnect the warehouse to confirm fallback to `sqlite(failover)` is silent.

## Notes

- The Databricks Free Edition warehouse has cold-start latency (~30s). The `FailoverSource` enforces a 5s timeout and trips a 60s circuit breaker so production demos stay snappy.
- Write paths (sessions, traces, drafts) stay on SQLite — Databricks Free has tight write quotas and these are runtime artefacts, not warehouse data.
