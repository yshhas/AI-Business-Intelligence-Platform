# Workspace Memory (Wave 3 MVP)

Persists **successful** `data.bi` `link_schema` column selections as phrase → column token maps for later Schema Linking.

| Concern | Rule |
|---------|------|
| Table | `workspace_column_memory` |
| Scope | Workspace + Dataset |
| Write | Worker after succeeded `data.bi` Run |
| Read | Merged into `AnalysisContext.schema_synonyms` |
| Toggle | `WORKSPACE_MEMORY_ENABLED` (default true) |

**Not** chat history, RAG, or cross-tenant memory.
