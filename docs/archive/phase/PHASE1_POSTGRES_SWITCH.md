# Phase 1 PostgreSQL 切换记录

**日期**：2026-07-21  
**结果**：✅ 通过（正式元数据库 = PostgreSQL）

## Docker / WSL2

| 检查项 | 结果 |
|--------|------|
| Docker CLI | 29.6.2 |
| Docker Compose | v5.3.1 |
| Context | `desktop-linux` |
| WSL distro `docker-desktop` | Running / VERSION 2 |

## 切换内容

1. Compose 仅启动 `postgres`（未启动 Redis）
2. 因本机已有容器占用 **5432**，将 compose 宿主机端口改为 **5433→5432**
3. `.env`：`DATABASE_URL` 从 SQLite 改为 `postgresql+psycopg://…@localhost:5433/aibi`
4. `alembic upgrade head` 在 `PostgresqlImpl` 上执行 `0001_phase1_auth`
5. 重启 API；`/health` → `db_dialect=postgresql`

未改 models / services / routes（方言抽象生效）。

## 验收

| 项 | 结果 |
|----|------|
| Migration | ✅ `Running upgrade -> 0001_phase1_auth` |
| 表创建 | ✅ users / workspaces / workspace_members |
| 注册 → JWT → workspace | ✅ `role=owner`，WS=1 |
| `/me` + 登录 | ✅ |
| 行数一致性 | ✅ users=workspaces=members=owners=1（新库首次注册后） |

## 停止线

未进入 Phase 2；未加 datasets / DuckDB；未启动/使用 Redis；无 Agent/LangGraph。
