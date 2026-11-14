# Directory Structure — v1.0

Feature Freeze 下的规范目录说明。命名约定：文档 `SCREAMING_SNAKE` 或主题名；代码包 `snake_case`。

```text
AI-Business-Intelligence-Platform/
├── README.md                      # 中文项目入口 · 快速开始 · 架构图 · 截图
├── compose.yaml                   # 根目录 Compose 入口（include docker/）
├── .env.example                   # 环境变量模板
├── .gitignore
├── agent/                         # Kernel + Skills（无 FastAPI/SQLAlchemy 持久化）
│   ├── README.md
│   ├── runtime.py                 # Facade → kernel.run
│   ├── kernel/                    # registry · runtime · types · tools · policies
│   ├── skills/
│   │   ├── data_bi/               # Text-to-SQL Skill
│   │   └── data_profile/          # Profile Skill
│   ├── gates/                     # sql.select_gate
│   ├── nodes/ · graph.py          # data.bi 固定 LangGraph 流水线
│   ├── guardrails.py
│   └── data_plane.py              # source_type 合同标记
├── backend/                       # Product Shell API + Worker
│   ├── README.md
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py
│   │   ├── api/                   # auth · datasets · tasks · mcp · health
│   │   ├── services/              # tasks · ACL · planes · OIDC · memory · …
│   │   ├── workers/               # analysis_worker · agent_runtime
│   │   ├── models/ · schemas/ · core/
│   │   └── middleware/
│   ├── alembic/versions/          # 0001…0016
│   ├── scripts/                   # smoke_* · demo_bootstrap.py
│   └── tests/                     # 后端纯单测
├── frontend/                      # React 工作台
│   ├── README.md
│   └── src/                       # pages · api · components
├── evals/                         # Golden suites: core · quality · profile · e2e · safety · llm · repair
│   ├── README.md
│   ├── suites/
│   ├── baselines/
│   └── runner.py
├── docker/                        # Compose · Nginx · Dockerfiles · 只读演示库初始化
├── database/                      # 数据约定说明
└── docs/
    ├── README.md                  # 文档导航（按角色分流）
    ├── FINAL_RELEASE.md           # v1.0 发布说明
    ├── demo.md                    # 端到端演示
    ├── architecture/              # Charter · Contracts · Data Plane · 目录结构 · 第二 Skill
    ├── design/                    # HITL · Memory · Token ADR · Prompt Gate · MCP · OIDC
    ├── ops/                       # Runbook · 配置矩阵 · 可观测性 · 密钥 · 错误码
    ├── testing/                   # SQL Gate 已知问题
    └── archive/                   # Phase / Sprint / Era / HITL / Roadmap / Reviews / P1 / Interview
```

## 清理约定（v1.0）

| 保留 | 不保留 / 勿新增 |
|------|-----------------|
| 历史 `PHASE_*` / `ERA_*` 冻结文档 | 未跟踪的 `*.tmp` / 调试脚本 / 本机 `.env` |
| `evals/reports/` 门禁产出（可本地） | 把密钥写入文档 |
| Smoke 脚本 | 绕过 Facade 的「临时」生产路径 |

## 文档权威顺序

1. 根 `README.md` — 对外入口与快速开始  
2. `docs/FINAL_RELEASE.md` — v1.0 交付说明  
3. `docs/architecture/PLATFORM_CHARTER.md` — 定位与边界  
4. 专题 docs（architecture / design / ops / testing）  
5. `docs/archive/` 历史文档 — 只读考古，冲突时以前者为准  
