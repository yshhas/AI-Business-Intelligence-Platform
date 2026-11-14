# MCP Read-only Tools (Wave 3 MVP)

HTTP adapter under Product Shell — **not** a full MCP server process.

## Endpoints

- `GET /api/v1/workspaces/{id}/mcp/tools`
- `POST /api/v1/workspaces/{id}/mcp/invoke` `{tool, arguments}`

## Tools

| Tool | Behavior |
|------|----------|
| `sql.gate_validate` | Requires `dataset_id`; allowlist from ACL projection; Gate only — never executes |
| `dataset.schema_get` | Requires `dataset_id`; schema + ACL-projected allowlist — no DSN |

Auth: workspace membership. Caller-supplied `allowed_tables` are ignored.
