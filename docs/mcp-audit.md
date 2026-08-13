# CockroachDB Cloud MCP usage

RouteRecall uses two CockroachDB tools required by the challenge:

1. **Distributed vector index** is part of the runtime memory path. It retrieves prior preferences and outcomes using cosine distance from `agent_memories.embedding`.
2. **CockroachDB Cloud managed MCP Server** is the review and operations path. A judge or developer can connect Claude Code, Cursor or VS Code to the cluster and inspect persisted state without a custom proxy.

The repository includes `.vscode/mcp.json`, configured for the RouteRecall cluster with OAuth and no stored credentials. In VS Code, start the `cockroachdb-cloud` server, choose **Authenticate**, sign in to CockroachDB Cloud, and grant **read-only** permission. Suggested judge queries:

Replace `RR-CLOUD-...` below with the case ID printed by `database/bootstrap_cloud.py`.

```sql
SELECT id, passenger_id, status, current_step, version
FROM recovery_cases
ORDER BY updated_at DESC;

SELECT case_id, step, version, created_at
FROM workflow_checkpoints
WHERE case_id = 'RR-CLOUD-...'
ORDER BY version;

SELECT recovery_case_id, action_type, idempotency_key, output
FROM action_ledger
WHERE recovery_case_id = 'RR-CLOUD-...';
```

The demo UI labels these reads as MCP audit events. It does not claim the MCP server executes passenger-facing writes; runtime writes go through a least-privileged application database user. This separation keeps the story technically accurate and makes auditing straightforward.
