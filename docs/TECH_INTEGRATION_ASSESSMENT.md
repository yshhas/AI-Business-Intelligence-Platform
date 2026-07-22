# Current Project Technology Integration Assessment

**Product:** Enterprise Data Agent Platform  
**Document type:** Technology fusion decision (assessment only)  
**Companion:** [`FINAL_TECH_REVIEW.md`](./FINAL_TECH_REVIEW.md) · [`PLATFORM_CHARTER.md`](./PLATFORM_CHARTER.md)  
**Status:** Decision record — **no code changes authorized by this document**  
**Question answered:** From the original AI-engineering candidate list, what truly belongs in this Data Agent Platform, what must stay in RepoPilot, and what should never be built here?

---

## Decision summary (one screen)

| Verdict | Meaning |
|---------|---------|
| **Already Integrated** | Candidate tech landed on the existing Kernel → Skill → Policy → Plane spine |
| **Should Integrate Later** | Fits the platform identity; needs a future authorized slice |
| **Not Recommended** | Business mismatch, architecture conflict, or RepoPilot-domain duplicate |

**Core filter used throughout:**

> Does this strengthen **governed Text-to-SQL / Data Skill Runs** (Policy before Plane, honest Trace), or does it pull the product toward chatbots, code agents, or generic LLM platforms?

---

## 1. Input technology list

Original candidate set (as provided at fusion kickoff / this assessment):

| # | Candidate cluster | Typical concrete items |
|---|-------------------|------------------------|
| 1 | **Python 进阶** | Decorator · Async/Await · Pydantic |
| 2 | **HTTP** | REST · WebSocket · SSE |
| 3 | **SQL / JSONB / Transaction** | Relational modeling · JSON columns · ACID edges |
| 4 | **FastAPI** | DI (`Depends`) · Middleware |
| 5 | **React / TypeScript** | Streaming UX · Client state |
| 6 | **Linux** | Process/container ops · compose bring-up |
| 7 | **Prompt Engineering** | Few-shot · delimiters · JSON-mode prompts |
| 8 | **RAG / Embedding** | Retrievers · vector indexes · chunk pipelines |
| 9 | **Agent ReAct / Tool Calling** | Free-form loops · dynamic tool choice · Multi-Agent |
| 10 | **Docker** | Image + Compose for API/Worker/deps |
| 11 | **Redis Cache / Rate Limit** | Response cache · token bucket · API throttles |
| 12 | **Observability** | Request ID · structured logs · Trace correlation |

Related engineering items that appeared in the same fusion discussion (assessed in §4 even if not always named above):

- LLM Client encapsulation · HTTP Retry · SQL JSON Schema  
- Skill Lifecycle · CI Release Gate · Async LLM Client · Evaluation · Cost tracking · Data Lineage  

---

## 2. Match analysis table

Legend for **决策**: `已引入` · `暂缓` · `不做`  
**优先级**: `P0` done this arc · `P1` next-authorized · `P2` later · `—` never here

| 技术 | 当前是否已有 | 是否适合当前项目 | 当前状态 | 决策 |
|------|-------------|------------------|----------|------|
| Python Decorator | 部分（registry/helpers，非装饰器宗教） | 适合作为惯用法，非独立产品能力 | 够用 | **暂缓**深造装饰器框架 |
| Async/Await | **无**（API sync + Worker sync/`httpx.Client`） | 局部适合；全面 async 重写不适合 | Worker/LLM 同步模型稳定 | **暂缓**（Async LLM Client） |
| Pydantic | **有** | 强适合 | Settings / API / `SqlDraft` | **已引入** |
| REST | **有** | 强适合 | FastAPI 产品壳 | **已引入** |
| WebSocket | **无** | 不适合主路径 | — | **不做** |
| SSE | **有** | 适合 **Task 进度** | `GET .../events` + Analyze | **已引入** |
| SQL / 关系模型 | **有** | 强适合（平台元数据 + 数据面） | Postgres + DuckDB / RO | **已引入** |
| JSON / JSON 列 | **有**（SQLAlchemy `JSON`，非强制 JSONB 方言特性） | 适合 Trace/result/step 载荷 | `result_json` / `output_json` / execution | **已引入**（够用） |
| Transaction | **有** | 强适合 Run/enqueue 一致性 | Session + commit 边界 | **已引入** |
| FastAPI DI | **有** | 强适合 | `Depends(get_db)` / member | **已引入** |
| FastAPI Middleware | **有** | 适合 | CORS · `RequestIdMiddleware` | **已引入** |
| React/TS State | **有** | 适合 Shell | Analyze/Tasks 状态 | **已引入** |
| React Token Streaming | **无** | 不适合（非聊天产品） | — | **不做** |
| Linux / 容器运维 | **有**（Compose 路径） | 适合 Demo/ops | Dockerfile + Compose + CI | **已引入** |
| Prompt Engineering | **有** | 强适合 SQL Skill | `prompts_sql.py` + JSON mode | **已引入** |
| RAG | **无** | **不适合** | — | **不做** |
| Embedding / Vector DB | **无** | **不适合** | — | **不做** |
| ReAct Agent Runtime | **无** | **冲突**（固定 LangGraph Skill） | — | **不做** |
| Dynamic Tool Calling 循环 | **无**（工具经 Kernel 注册，非 ReAct 选工具） | 平台要 **受控 Tool**，不要自由循环 | Kernel Tool 记录 | **不做** ReAct；保留受控 Tool |
| Multi-Agent | **无** | 过早 / 叙事冲突 | 单 Skill `data.bi` | **不做**（第二 Skill 前） |
| Docker | **有** | 强适合 | api/worker/infra | **已引入** |
| Redis 作为队列 | **有** | 强适合 | List + Worker | **已引入** |
| Redis Response Cache | **无** | 不适合 SQL 正确性路径 | — | **不做** |
| Redis Token Bucket | **无** | 可选 ops；非身份核心 | 已有 in-flight/queue 帽 | **暂缓** |
| Observability | **有** | 强适合 | Request ID · JSON log · Trace | **已引入** |
| LLM Client | **有** | 强适合 | `llm_client.py` | **已引入** |
| LLM Retry | **有** | 强适合 | timeout/429/5xx | **已引入** |
| SQL JSON Mode + Schema | **有** | 强适合 | `SqlDraft` | **已引入** |
| Skill Lifecycle lite | **有** | 适合平台叙事 | enable/version pin | **已引入** |
| CI Release Gate | **有** | 适合 | Actions → smoke gate | **已引入** |

### Per-item rationale (suitability · architecture · RepoPilot · priority)

#### Python Decorator
- **适合？** 作为代码风格可选；不是差异化能力。  
- **架构冲突？** 无。用装饰器堆“框架”会噪音。  
- **RepoPilot 重复？** 无关。  
- **优先级：** P2 / 暂缓 — 不单独立项。

#### Async/Await（含 Async LLM Client）
- **适合？** 在高并发 LLM/IO 下有价值；当前负载是 **单 Run 管线 + Worker 线程超时**，同步 `httpx` 已够。  
- **架构冲突？** 全面 async 化会波及 Worker/SQLAlchemy 会话模型，性价比差。  
- **RepoPilot 重复？** RepoPilot 可自有 async 栈；此处不因“对齐技术清单”而重写。  
- **优先级：** P2 暂缓 — 仅在实测 Worker 阻塞成为瓶颈时再开薄切片。

#### Pydantic
- **适合？** 是。API、Settings、`SqlDraft` 校验是平台正确性的一部分。  
- **冲突？** 无。  
- **RepoPilot？** 两边都用 Pydantic 不构成重复建设（通用库）。  
- **优先级：** P0 已完成。

#### REST
- **适合？** 是。产品壳契约。  
- **冲突？** 无。  
- **RepoPilot？** 各自产品 API，不融合。  
- **优先级：** P0 已有。

#### WebSocket
- **适合？** 否。Analyze 需要的是 **任务生命周期事件**，不是双向聊天通道。  
- **冲突？** 与“Trace 为真、SSE 进度”决策重复建设实时层。  
- **RepoPilot？** 若 RepoPilot 用 WS 做工程流，仍属其域。  
- **优先级：** — 不做。

#### SSE
- **适合？** 是（Task/step/status only）。  
- **冲突？** 无（明确禁止 token stream）。  
- **RepoPilot？** 不重复。  
- **优先级：** P0 已完成（T-10）。

#### SQL / JSON 列 / Transaction
- **适合？** 是 — 元数据、Run、Trace、Artifact 都靠关系库诚实落库。  
- **冲突？** 无。JSONB 方言特技非必须；通用 JSON 列已满足。  
- **RepoPilot？** 不同 schema/域。  
- **优先级：** P0 已有。

#### FastAPI DI / Middleware
- **适合？** 是 — 工作区成员注入、Request ID、CORS。  
- **冲突？** 无。  
- **RepoPilot？** 通用模式，非能力搬迁。  
- **优先级：** P0 已有。

#### React/TS State（非 token stream）
- **适合？** 是 — Shell UX。  
- **冲突？** Token streaming UI 与产品定位冲突 → 排除。  
- **RepoPilot？** 不同前端产品。  
- **优先级：** State 已有；Streaming tokens — 不做。

#### Linux / Docker 运维面
- **适合？** 是 — Demo 可复现、CI 可跑。  
- **冲突？** 无（Compose 止步，不做 K8s）。  
- **RepoPilot？** 各自部署，不共享集群叙事。  
- **优先级：** P0 已完成（T-12/T-13）。

#### Prompt Engineering
- **适合？** 是 — 直接提升 `data.bi` SQL 质量与注入面。  
- **冲突？** 无。  
- **RepoPilot？** Prompt 模式可相似，**内容域不同**（SQL vs 代码），不搬业务 Prompt。  
- **优先级：** P0 已完成（T-05/T-06）。

#### RAG / Embedding / Vector DB
- **适合？** **否** — 产品答案来自 **绑定数据面 + Policy SQL**，不是文档召回。  
- **冲突？** 会把平台改写成知识库聊天，稀释 Gate/Plane 证明。  
- **RepoPilot？** 若 RepoPilot 做代码检索 RAG，应留在那边；此处不复制。  
- **优先级：** — 不做。

#### ReAct / 自由 Tool Calling / Multi-Agent
- **适合？** **否** — 与固定 LangGraph Skill + Policy-before-execute 冲突。  
- **冲突？** **高** — 自由循环破坏 allowlist 纪律与 Run 诚实性。  
- **RepoPilot？** 工程 Agent 的 ReAct/工具循环属于 RepoPilot 叙事；**禁止迁入**。  
- **优先级：** — 不做。

#### Docker（作为融合项）
- **适合？** 是。  
- **冲突？** 无。  
- **RepoPilot？** 不重复业务能力。  
- **优先级：** P0 已完成。

#### Redis Cache
- **适合？** **否**（对 LLM SQL 草稿/结果）— 错误缓存比慢更贵。  
- **冲突？** 与“每次 Run 可审计、可复现失败类”不一致。  
- **RepoPilot？** 缓存策略各自决定。  
- **优先级：** — 不做 LLM/SQL cache。

#### Redis Token Bucket / API Rate Limit
- **适合？** 运维上可选；**身份上非必须** — 已有 `RUN_MAX_IN_FLIGHT` + `ANALYSIS_QUEUE_MAX_DEPTH`。  
- **冲突？** 低；但易滑向“再造一套限流产品”。  
- **RepoPilot？** 可有各自限流；不因 RepoPilot 有就搬。  
- **优先级：** P2 暂缓 — 有滥用证据再做。

#### Observability
- **适合？** 是 — Request ID、JSON log、Trace、LLM usage。  
- **冲突？** 引入 LangSmith 双轨会冲突（已 Won't Do）。  
- **RepoPilot？** 可共享“理念”，不共享供应商强绑定。  
- **优先级：** P0 已完成（T-07/T-08）；APM 暂缓。

---

## 3. Tiered decisions

### Already Integrated

进入本平台、且已落在当前代码/门禁上的候选能力：

| 技术 | 落点（代表） | 融合价值 |
|------|--------------|----------|
| FastAPI + DI + Middleware | `backend/app/main.py`, routes, `RequestIdMiddleware` | 产品壳与横切关注点 |
| Pydantic / Settings | schemas · `SqlDraft` · config | 契约与 SQL JSON 校验 |
| REST | `/api/v1/...` | Shell 主协议 |
| SSE（Task 进度） | `task_events.py` · Analyze | 可见 Run，而非聊天 |
| SQL + JSON 载荷 + Transaction | models · task/artifact services | Run 诚实落库 |
| React/TS 状态驱动 UI | `frontend/src/pages/*` | Demo 工作台 |
| Prompt Engineering + JSON Mode | `prompts_sql.py` · `schemas_llm.py` | Skill 质量与可控输出 |
| LLM Client + Retry | `llm_client.py` | 可测试、可恢复的模型边 |
| LLM Usage → Trace | step `output_json.llm` | 成本/延迟可观测 |
| Observability（Request ID / JSON log） | `observability.py` | API↔Worker↔Trace 关联 |
| Redis **Queue**（非 Cache） | analysis Worker List | 异步治理 Run |
| Docker Compose API/Worker | `docker/*` | 一键可运行 |
| CI Release Gate | `.github/workflows/ci.yml` | 固化已有 smoke |
| Skill Lifecycle lite | `skill_lifecycle.py` | 平台感（enable/version） |
| 固定 LangGraph Skill（非 ReAct） | `agent/graph.py` · pipeline | 受控 Agent 路径 |

### Should Integrate Later

有业务价值、**不违背** Charter，但需未来显式授权切片：

| 主题 | 业务价值 | 为何是“Later” |
|------|----------|----------------|
| **Connector Framework（薄）** | 更多受控数据面，同一 Policy | M3 只证明薄 RO；框架是下一叙事，不是现在补清单 |
| **More Skills（第二 Skill）** | 证明平台 ≠ 单应用 | 需 Lifecycle 纪律；禁止借机上 Multi-Agent |
| **Permission 增强** | 多角色/资源 ACL 深化 | M5 已够 Demo；有真实权限痛再加 |
| **Data Governance lite** | 更强 allowlist / 契约 | 加深 Gate 信任，不做 Catalog 巨兽 |
| **Evaluation Framework** | 让 Prompt/LLM 改动可证伪 | 缺黄金集时改 Prompt 靠感觉 |
| **Cost Control** | 预算/告警 | T-07 已有 usage 字段；控制层未建 |
| **Async LLM Client** | Worker 吞吐 | 无阻塞证据前不重写 |
| **Redis Token Bucket** | 防刷 / 租户公平 | 队列帽已讲容量故事 |
| **Policy Trace  enrichment** | Demo 可解释性 | 附属增强，非新引擎 |
| **Data Lineage（加深）** | Artifact/Run 血缘 | M6 lineage 已起步；全链路治理另开 |

### Not Recommended

明确 **不进入** 本仓库产品身份：

| 技术 | 原因类型 | 一句话 |
|------|----------|--------|
| RAG | 业务不匹配 | 答案在数据面 SQL，不在文档块 |
| Embedding / Vector DB | 业务不匹配 | 无检索索引需求 |
| ReAct Runtime | 架构冲突 | 对抗固定 Skill 图 + Policy |
| Multi-Agent 编排 | 架构冲突 / 过早 | 单 Skill 未尽，先别演戏 |
| WebSocket | 无价值 / 重复 | SSE 已覆盖进度 |
| Token Streaming UI | 业务不匹配 | 非聊天产品；易泄中间推理 |
| Redis LLM/SQL Cache | 正确性风险 | 错缓存 > 慢 |
| LangSmith 双轨 Tracing | 架构冲突 | Run Trace 已是真源 |
| Code Agent / Git / Patch | RepoPilot 域 | 反目标：第二 RepoPilot |
| K8s / Helm / Terraform / 云 CD | 超范围 | Compose+CI 已闭环本弧 |

---

## 4. Missing but worth revisiting

Items that appeared in the original engineering discussion / adjacent shortlist, **not fully built**, yet **legitimately relevant** later:

| 技术 | 当前缺口 | 为何现在不做 | 何时再议 |
|------|----------|--------------|----------|
| **Async LLM Client** | 仍为同步 `httpx.Client` | Worker 模型与超时线程池已工作；async 是吞吐优化不是正确性 | 实测 LLM 等待占满 worker 时 |
| **Redis Token Bucket** | 无 API/LLM 令牌桶 | 已有 Run in-flight + queue depth；再做易叠床架屋 | 多租户滥用或供应商硬限额成为事实痛点 |
| **Evaluation System** | 无系统化黄金题/门禁集 | 本弧优先把调用链工程化；评测是下一质量闸 | Prompt/模型频繁变更前 |
| **Cost Tracking（控制面）** | Trace 有 usage，无预算策略 | 有数无限额仍可 Demo | 真实账单或配额需求出现 |
| **Data Lineage（端到端）** | Artifact lineage 轻量 | 全治理平台会滑向 Catalog/ETL | Connector / 多平面之后 |
| **APM / metrics 后端** | 日志 + Trace | DH 明确不做 SIEM/APM 产品 | 运维证据要求升高时 |
| **JSONB 特化查询** | 通用 JSON 列 | 无慢查询证据 | Trace 分析查询成为瓶颈 |
| **Decorator-heavy 框架化** | 未做 | 增加抽象不增加 Data Agent 证明 | 永不作为目标 |

**原则：** “清单里有” ≠ “现在缺”；只有 **强化 Skill→Policy→Plane→Trace** 的缺口才进入 Later。

---

## 5. Final technology roadmap

```text
Current Version (Frozen arc)
        ↓
Next Version (authorized thin slices)
        ↓
Future Platform (multi-skill / multi-plane)
```

### Current Version — “Governed Data Skill Platform (operable)”

| | |
|--|--|
| **技术目标** | 固定 `data.bi` + Policy + 双平面；LLM 工程化；SSE 进度；Compose+CI |
| **业务价值** | 可演示、可回归、可讲述的 Enterprise Data Agent（非 BI 玩具） |
| **为什么此时做** | 身份已立；缺口在调用质量与可运维，不在新 Agent 范式 |

### Next Version — “Quality, cost, and second surface (thin)”

| | |
|--|--|
| **技术目标** | Evaluation 黄金集 · Cost 控制读 Trace · Permission/Governance 加深 · 可选 Async LLM / Token Bucket（有证据才上） |
| **业务价值** | 模型改动可证伪；成本可控；多用户更敢用 |
| **为什么此时做** | Current 已冻结调用链；下一步是 **证明与约束**，仍不做 RAG/ReAct |

### Future Platform — “Multi-skill / multi-plane Data Agent”

| | |
|--|--|
| **技术目标** | 第二 Skill（经 Lifecycle）· 薄 Connector Framework · 更深 Lineage |
| **业务价值** | 平台叙事闭环：多能力、多平面、同一 Kernel/Policy/Run |
| **为什么此时做** | 仅当单 Skill 与单薄 RO 平面的故事已被市场/简历证明“不够用” |

**Never on this roadmap:** RAG 栈、ReAct 运行时、Multi-Agent 网格、Code Agent、WebSocket 聊天、Token streaming、LLM SQL cache、云原生 CD 平台。

---

## 6. Direct answer to the fusion question

> **最初给出的所有 AI 工程技术里，哪些真正应该进入 Enterprise Data Agent Platform，哪些应该永远保持在 RepoPilot 或不实现？**

### Should enter **this** platform（已进或可 Late）

- **工程底座：** Pydantic · FastAPI DI/Middleware · REST · SQL/JSON/Transaction · Docker · CI  
- **交互：** SSE **任务进度**（不是 WS/token stream）· React 状态 UI  
- **LLM 工程：** Client · Retry · JSON Mode/Schema · Prompt 防护 · Usage→Trace · Observability  
- **平台感：** Skill Lifecycle lite ·（未来）More Skills · Connector 薄切片 · Eval · Cost control  
- **Redis：** **Queue / 容量治理**（不是 LLM cache）

### Keep in **RepoPilot**（或仅留在那边）

- Code / Git / Patch Agent 能力与工程工具循环  
- 任何以 **代码仓库为真源** 的 ReAct/检索/补丁工作流  
- 与工程变更绑定的专用限流、缓存、评测集  

> 两边可以共享“受控 Agent”**思想**，禁止共享 **代码域实现**。

### Never implement **here**

- RAG · Embedding · Vector DB  
- ReAct Runtime · Multi-Agent 编排  
- WebSocket 主协议 · Token Streaming 聊天  
- Redis LLM/SQL Response Cache · LangSmith 双轨 Trace  
- 把本仓做成第二 RepoPilot 的一切

---

## 7. Relationship to Final Tech Review

| Document | Job |
|----------|-----|
| [`FINAL_TECH_REVIEW.md`](./FINAL_TECH_REVIEW.md) | What was **built** and frozen |
| **This file** | What the **original candidate list** maps to: integrate / later / never |

Together they close the loop from “technology shopping list” → “architecture-faithful fusion” → “freeze.”

**End of Technology Integration Assessment.**  
No code or feature work is implied.
