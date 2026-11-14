# Phase 2 Final Acceptance Summary

**项目**：AI Business Intelligence Platform  
**阶段**：Phase 2 — CSV/Excel → DuckDB → metadata → schema/preview  
**状态**：✅ **正式冻结**（2026-07-21）  
**运行元数据库**：PostgreSQL（Compose `aibi-postgres`，host `:5433`）  
**分析引擎**：DuckDB（每 Workspace 一个 `.duckdb` 文件）

---

## 1. 最终架构状态

```text
Browser (React)
    │  JWT + multipart / REST
    ▼
FastAPI routes  ──auth / workspaces / datasets / health──
    │
    ├─► dataset_service     （业务编排：存盘 → 导入 → 写 PG 元数据）
    │         │
    │         └─► duckdb_service   （分析引擎：import / schema / preview）
    │                   │
    │                   └─► data/duckdb/{workspace_id}.duckdb
    │
    └─► SQLAlchemy models  ──► PostgreSQL（users / workspaces / members / datasets）
```

| 层 | 职责 | 技术 |
|----|------|------|
| 元数据 | 用户、Workspace、成员、数据集登记 | PostgreSQL + Alembic |
| 分析数据 | 上传表内容、查询 preview | DuckDB 文件 |
| 编排 | 上传事务边界、状态 `ready`/`failed` | `dataset_service` |
| 引擎封装 | 不暴露任意 SQL；仅受控 import/preview | `duckdb_service` |
| HTTP | 鉴权、参数、响应模型 | FastAPI routes |
| 前端 | 登录态 + Datasets 工作台 | React + TypeScript |

**明确未包含（停止线）**

- LangGraph / Agent / Text-to-SQL  
- Redis 消费 / Worker  
- `analysis_tasks` / 报告 / 图表分析  
- Dataset DELETE（有意延后，不影响主线）  
- 外部业务库连接、多 sheet 管理  

---

## 2. 已完成能力列表

### Phase 1（冻结，本阶段只复用）

- [x] 注册 / 登录 / JWT / `/me`  
- [x] 默认 Workspace + owner member  
- [x] Dashboard + 刷新保持登录  
- [x] PostgreSQL 正式元数据 + 方言抽象  

### Phase 2（本阶段）

- [x] 存储约定：`UPLOAD_DIR` / `DUCKDB_DIR`（相对路径按仓库根解析）  
- [x] `datasets` 表 + 迁移 `0002_phase2_datasets`  
- [x] CSV 上传导入 DuckDB（含 UTF-8 BOM 处理）  
- [x] Excel `.xlsx` 导入（**仅第一张 sheet**）  
- [x] `schema_json` + `row_count` 写入元数据  
- [x] 数据集列表 / 详情 / preview（受控 `LIMIT`）  
- [x] Workspace 成员鉴权复用（非成员不可访问）  
- [x] 前端 `/app/datasets`：上传、列表、schema、preview  
- [x] 分层：`routes` → `dataset_service` → `duckdb_service`  

### 验收证据（摘要）

- API：`POST upload` → `status=ready`，preview 列与行正确  
- 服务冒烟：CSV + XLSX 导入脚本通过  
- 前端：`npm run build` 通过  
- 运行时：`/health` → `db_dialect=postgresql`；Postgres 容器 healthy  

---

## 3. 前后端接口清单

### 3.1 后端 HTTP（现行）

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/health` | 否 | 探活 + `db_dialect` |
| POST | `/api/v1/auth/register` | 否 | 注册 + 默认 WS + JWT |
| POST | `/api/v1/auth/login` | 否 | 登录 + JWT |
| GET | `/api/v1/auth/me` | Bearer | 当前用户 |
| GET | `/api/v1/workspaces` | Bearer | Workspace 列表 |
| GET | `/api/v1/workspaces/{id}` | Bearer + 成员 | 详情 |
| PATCH | `/api/v1/workspaces/{id}` | Bearer + 成员 | 改名 |
| GET | `/api/v1/workspaces/{wid}/datasets` | Bearer + 成员 | 数据集列表 |
| POST | `/api/v1/workspaces/{wid}/datasets/upload` | Bearer + 成员 | multipart：`file` + 可选 `name` |
| GET | `/api/v1/workspaces/{wid}/datasets/{id}` | Bearer + 成员 | 详情（含 schema） |
| GET | `/api/v1/workspaces/{wid}/datasets/{id}/preview?limit=` | Bearer + 成员 | 表格预览 |

**上传成功响应要点**：`id`, `name`, `schema_json[]`, `row_count`, `status=ready`, `duckdb_table`  

**Preview 响应**：`{ columns: string[], rows: object[], row_count: number }`  

### 3.2 前端页面与调用

| 路由 | 页面 | 主要 API |
|------|------|----------|
| `/login` `/register` | 登录注册 | auth |
| `/app` | Dashboard | workspaces |
| `/app/datasets` | Datasets | datasets upload/list/preview |

前端客户端：`frontend/src/api/{auth,datasets,client,health}.ts`  
会话：`localStorage`（`aibi_access_token` 等）

---

## 4. 当前目录结构变化（相对 Phase 1）

```text
AI-Business-Intelligence-Platform/
├── agent/                    # 仍仅占位（无 Graph）
├── backend/
│   ├── alembic/versions/
│   │   ├── 0001_phase1_auth.py
│   │   └── 0002_phase2_datasets.py          ← Phase 2
│   ├── app/
│   │   ├── api/routes_datasets.py           ← Phase 2
│   │   ├── core/storage_paths.py            ← Phase 2
│   │   ├── models/__init__.py               ← + Dataset
│   │   ├── schemas/dataset.py               ← Phase 2
│   │   └── services/
│   │       ├── dataset_service.py           ← Phase 2 编排
│   │       └── duckdb_service.py            ← Phase 2 引擎
│   ├── scripts/
│   │   ├── smoke_duckdb_import.py
│   │   └── _xlsx_smoke.py / _phase1_db_check.py
│   └── requirements.txt                     ← + duckdb, openpyxl, multipart
├── data/
│   ├── uploads/                             ← 上传原文件（gitignore 内容）
│   ├── duckdb/                              ← *.duckdb（gitignore）
│   └── aibi_phase1.db                       ← 历史 SQLite 冒烟残留（非运行库）
├── database/README.md                       ← 约定更新
├── docker/                                  ← Postgres only（Phase 1+）
├── docs/
│   ├── PHASE2_CHECKLIST.md
│   └── PHASE2_ACCEPTANCE.md                 ← 本文档
└── frontend/src/
    ├── pages/DatasetsPage.tsx               ← Phase 2
    ├── api/datasets.ts
    └── types/dataset.ts
```

---

## 5. Phase 3 前置条件检查（不开始编码）

Phase 3 目标（回顾）：**异步任务骨架**（`analysis_tasks` + Redis 队列 + Worker mock），仍 **不含** LangGraph / Text-to-SQL。

| 前置项 | 状态 | 说明 |
|--------|------|------|
| Phase 1 Auth/Workspace 冻结 | ✅ | 可稳定拿 `workspace_id` + JWT |
| Phase 2 数据集可 preview | ✅ | 任务可绑定 `dataset_id` |
| PostgreSQL 元数据可用 | ✅ | Compose healthy |
| DuckDB 引擎可查询 | ✅ | `duckdb_service.preview_table` |
| Redis **容器**（Compose 已定义） | ⚠️ 可选 | Phase 3 才需 `up redis`；**应用消费逻辑尚未写** |
| `analysis_tasks` / `agent_run_steps` 表 | ❌ 未建 | Phase 3 Step |
| Worker 进程 | ❌ 未建 | Phase 3 Step |
| SSE / 任务轮询 | ❌ 未建 | Phase 3 Step |
| LangGraph / SQL Gate | ❌ 禁止 | Phase 4–5，勿提前 |

**建议 Phase 3 入口条件（全部满足后再开编码）**

1. 本文档验收确认  
2. 本地可登录并至少有一个 `ready` 数据集  
3. 明确 Phase 3 仍冻结：不做 NL 分析、不做报告/图表  

---

## 6. 冻结声明

**Phase 2 正式冻结。**  

后续变更若触及上传/DuckDB/datasets 主路径，应作为 hotfix 或单独小版本说明，不得借机引入 Agent / 任务 / 报告。

**下一步**：待你确认本验收总结后，再输出 Phase 3 实施 checklist（仍先设计、后编码）。

---

## 7. 一句话交付

> 平台已具备「可登录工作台 + 可上传表格进 DuckDB + 可看 schema/preview」的数据准备能力；AI 分析编排留给后续阶段。
