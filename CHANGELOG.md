# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] — Unreleased (draft for Sprint 4 exit)

### Added

- Cooperative cancel / timeout with write fence (P1.1)
- Refresh `jti` sessions, rotation revoke, logout (P1.2)
- Workspace memory TTL + per-workspace cap (P1.3)
- Hot `result_json` size bounds with explicit `platform.payload` truncation metadata (P1.4)
- `list_tasks` batched ACL preload (P1.5)
- `ANALYSIS_RUNTIME` boot hardening for prod/staging (P1.6)
- Guardrails covering Run `table_preview` and Dataset `/preview` (P1.7)
- Token storage ADR — localStorage accepted for v1.1; Cookie deferred (P1.8)
- Product Shell: Skill picker, ACL UI, mysql-ro disabled placeholder (P1.10)
- HITL SQL approval **design document only** (no state machine)

### Changed

- Worker persists slim hot results after artifact materialization; Trace `platform.execution` remains on hot path
- Auth refresh reuse after rotation returns 401

### Migration notes

- Apply Alembic through `0014_sprint2_refresh_memory` (refresh_sessions + memory `expires_at`)
- Existing refresh JWTs without session rows require re-login

### Known limitations

- Hot truncation does not add object-store cold blobs in v1.1 (omissions are explicit)
- Cookie / HttpOnly auth not implemented (see ADR)
- HITL approval not implemented (design only)
- Phase 2 (Semantic / Multi-Agent / HITL code) not started

## [1.0.0] — 2026-07-22

### Added

- Enterprise Data Agent Platform spine: Product Shell → Worker → Kernel → Skill → Policy → Data Plane → Trace / Artifacts
- Skills: `data.bi` (Text-to-SQL → table / chart / report) and `data.profile` (deterministic dataset profiling)
- Run governance: timeout, cancel, capacity limits, soft LLM token budget, Idempotency-Key
- Security: short-lived JWT + refresh, rate limits, production JWT hardening, Dataset ACL + table projection, optional OIDC MVP, output guardrails
- Data planes: CSV/XLSX → DuckDB (`file`), Postgres read-only, optional MySQL read-only
- Quality: Eval suites (core / quality / profile), Prompt change gate, `smoke_release_gate`
- Ops: Docker Compose, Prometheus `/metrics`, Worker health endpoint, optional Nginx web profile, structured logs
- Platform proofs: workspace linking memory, MCP read-only HTTP tools, second Skill under the same contracts
- CI: GitHub Actions workflow for release gate / frontend lint & build
- Documentation: FINAL_RELEASE, ops runbooks, interview / resume guides, config matrix

### Known limitations

- Wave 4 (single-cloud IaC / enterprise deploy) not started
- JWT refresh revocation (`jti`) not implemented
- Worker timeout may leave orphan step writers (cooperative cancel deferred)
- OIDC / MySQL RO are MVP surfaces — not production-soaked against a real IdP

### Notes

- **Feature Freeze** for v1.0: no new product features without an explicit new requirement
- Canonical narrative: [docs/FINAL_RELEASE.md](docs/FINAL_RELEASE.md)
- Release notes for GitHub: [RELEASE_NOTES.md](RELEASE_NOTES.md)

[1.0.0]: https://github.com/OWNER/REPO/releases/tag/v1.0.0
