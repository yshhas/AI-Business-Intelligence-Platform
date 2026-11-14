# Data Plane (Wave 3)

Thin read-only SELECT planes behind SQL Gate. Not a Connector Framework.

## Supported `source_type`

| Type | DSN / storage | Bind API |
|------|---------------|----------|
| `file` | Workspace DuckDB file | `POST .../datasets/upload` |
| `postgres_ro` | `POSTGRES_RO_DSN` | `POST .../datasets/postgres-ro` |
| `mysql_ro` | `MYSQL_RO_DSN` (optional) | `POST .../datasets/mysql-ro` |

## Protocol

`agent.data_plane.DataPlane` / `SUPPORTED_SOURCE_TYPES` marks the contract.
Worker binds `execute_select` adapters; Skills never import Shell connectors.

## MySQL MVP notes

- Requires `PyMySQL` and `MYSQL_RO_DSN=mysql://user:pass@host:3306/db`
- Relations are `database.table` (≤2 allowlisted)
- Session forced read-only; Gate re-applied before execute
