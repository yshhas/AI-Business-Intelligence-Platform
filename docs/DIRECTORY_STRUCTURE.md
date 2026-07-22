# Directory Structure — v1.0

Feature Freeze 下的规范目录说明。命名约定：文档 `SCREAMING_SNAKE` 或主题名；代码包 `snake_case`。

```text
AI-Business-Intelligence-Platform/
├── README.md                      # 入口 · 快速开始 · 架构图
├── project_upgrade_plan.md        # 路线图 SSOT（Wave 0–3 Done · Wave 4 Pending）
├── .env.example                   # 环境变量模板（含 Wave 3）
├── .gitignore
├── agent/                         # Kernel + Skills（无 FastAPI/SQLAlchemy 持久化）
│   ├── README.md
│   ├── runtime.py                 # Facade → kernel.run
│   ├── kernel/                    # registry · runtime · types · tools · policies
│   ├── skills/
│   │   ├── data_bi/               # Text-to-SQL Skill
│   │   └── data_profile/          # Profile Skill（Wave 3）
│   ├── gates/                     # sql.select_gate
│   ├── nodes/ · graph.py          # data.bi 实现细节
│   ├── guardrails.py
│   └── data_plane.py              # source_type 合同标记
├── backend/                       # Product Shell API + Worker
│   ├── README.md
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py                # version 1.0.0
│   │   ├── api/                   # auth · datasets · tasks · mcp · health
│   │   ├── services/              # tasks · ACL · planes · OIDC · memory · …
│   │   ├── workers/               # analysis_worker · agent_runtime
│   │   ├── models/ · schemas/ · core/
│   │   └── middleware/
│   ├── alembic/versions/          # 0001…0013
│   └── scripts/                   # smoke_* · smoke_release_gate.py
├── frontend/                      # React 工作台
│   ├── README.md
│   └── src/                       # pages · api · components
├── evals/                         # Golden suites: core · quality · profile · llm
│   ├── README.md
│   ├── suites/
│   ├── baselines/
│   └── runner.py
├── docker/                        # Compose · Nginx · Dockerfiles
├── database/                      # 数据约定说明（若有）
└── docs/                          # 交付与阶段文档
    ├── FINAL_RELEASE.md           # v1.0 发布说明 ★
    ├── FINAL_STABILIZATION_REVIEW.md
    ├── RESUME_HIGHLIGHTS.md       # 简历 ★
    ├── INTERVIEW_GUIDE.md         # 面试 ★
    ├── DIRECTORY_STRUCTURE.md     # 本文件
    ├── PLATFORM_CHARTER.md
    ├── PLATFORM_CONTRACTS.md
    ├── API_ERROR_CODES.md
    ├── OPS_RUNBOOK.md
    ├── OPS_CONFIG_MATRIX.md
    ├── PHASES.md
    ├── DATA_PLANE.md · OIDC.md · MCP.md · WORKSPACE_MEMORY.md
    ├── SKILL_DATA_PROFILE_CHARTER.md
    └── …（历史 Phase 冻结文档保留作审计，以 FINAL_RELEASE / plan 为准）
```

## 清理约定（v1.0）

| 保留 | 不保留 / 勿新增 |
|------|-----------------|
| 历史 `PHASE_*` / `ERA_*` 冻结文档 | 未跟踪的 `*.tmp` / 调试脚本 / 本机 `.env` |
| `evals/reports/` 门禁产出（可本地） | 把密钥写入文档 |
| Smoke 脚本 | 绕过 Facade 的「临时」生产路径 |

## 文档权威顺序

1. `docs/FINAL_RELEASE.md` — 对外交付叙事  
2. `project_upgrade_plan.md` — 路线与进度 SSOT  
3. `docs/PLATFORM_CHARTER.md` — 身份与红线  
4. 专题 docs（OPS / API / Skill Charter）  
5. 历史 Phase 文档 — 只读考古，冲突时以前者为准  
