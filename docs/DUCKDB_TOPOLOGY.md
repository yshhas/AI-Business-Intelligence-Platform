# DuckDB Data Plane Topology

**Status:** Wave 2 deployment note

## Single-host shared volume

File-upload datasets land in DuckDB files under `DUCKDB_DIR` (default `./data/duckdb`).
The **API** process ingests uploads and the **Worker** executes queries against the same
DuckDB files. Both must see the **same filesystem path**.

In Docker Compose this is enforced via a shared bind mount:

```
../data:/app/data   # api + worker
```

Do **not** run API and Worker on separate hosts unless you provide a **shared filesystem**
(NFS, EFS, Azure Files, etc.) mounted at the same path on every node. Without shared
storage, upload-on-API / analyze-on-Worker will fail with missing DuckDB files.

## Multi-host constraints

| Layout | Supported? | Requirement |
|--------|------------|-------------|
| Single machine, Compose | Yes | Default `data/` volume |
| K8s single PVC RWX | Yes | ReadWriteMany volume for `/app/data` |
| API + Worker on different nodes, local disks | **No** | Needs shared FS |
| Object storage only (S3) for DuckDB | **Not in Wave 2** | Future migration |

## Postgres RO plane

`postgres_ro` is a separate connection (not DuckDB). Worker reaches it via `POSTGRES_RO_DSN`.
No shared DuckDB volume is required for RO-bound datasets.

See [OPS_RUNBOOK.md](./OPS_RUNBOOK.md) for bring-up order.
