# Workspace Memory (Wave 3 MVP + P1.3)

Persists **successful** `data.bi` `link_schema` column selections as phrase → column token maps for later Schema Linking.

| Concern | Rule |
|---------|------|
| Table | `workspace_column_memory` |
| Scope | Workspace + Dataset |
| Write | Worker after succeeded `data.bi` Run |
| Read | Merged into `AnalysisContext.schema_synonyms` |
| Toggle | `WORKSPACE_MEMORY_ENABLED` (default true) |
| TTL | `WORKSPACE_MEMORY_TTL_DAYS` (default **90**; `0` = do not set expiry on write) |
| Cap | `WORKSPACE_MEMORY_MAX_ROWS` (default **2000** / workspace) |
| Prune | On write: delete expired (`expires_at <= now`), then LRU by `updated_at` / `hit_count` |
| Grandfather | Existing rows with `expires_at=NULL` remain readable until upsert refreshes TTL |

**Not** chat history, RAG, or cross-tenant memory.
