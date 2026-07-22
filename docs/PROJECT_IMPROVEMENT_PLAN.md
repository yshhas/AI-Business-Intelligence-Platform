# PROJECT_IMPROVEMENT_PLAN

**Product:** Enterprise Data Agent Platform  
**Document type:** Production Readiness Gap Analysis + Improvement Roadmap  
**Status:** Planning only — **no coding authorized**  
**Date:** 2026-07-22  
**Prerequisite freeze:** Era 1–2 + Era 3 P0/DH + AI engineering fusion (T-01…T-13)  
**Architecture lock:**

```text
Skill → Policy → Data Plane → Trace
```

**Parents:** [FINAL_TECH_REVIEW.md](./FINAL_TECH_REVIEW.md) · [TECH_INTEGRATION_ASSESSMENT.md](./TECH_INTEGRATION_ASSESSMENT.md) · [PLATFORM_CHARTER.md](./PLATFORM_CHARTER.md)

---

## Executive Summary

当前仓库已经具备可讲述、可演示、可回归的 **Governed Data Agent Platform** 脊柱。距离「更完整的企业级平台」的缺口，**不是**缺 RAG / ReAct / Multi-Agent / 微服务，而是：

1. **AI Quality 不可证伪** — Prompt/模型改动没有黄金集与自动回归，成功率靠感觉。  
2. **成本只有观测、没有控制** — Trace 已有 usage，缺预算/配额闭环。  
3. **权限仍停在 workspace+role** — 够 Demo，不够「数据集/表级」企业叙事深化。  
4. **Text-to-SQL 能力面偏薄** — 单表 schema dump + Gate 重试；缺可度量的 schema linking / 受控 repair。  
5. **扩展面「可讲尚未二次验证」** — Lifecycle lite 已有，第二 Skill / 第三 Plane 尚未用契约证明。  
6. **工程质量有若干 Demo 可接受债** — 同步 Worker、SSE 无自动重连、前端状态偏本地、无多 Worker 运维手册硬化。

**推荐优先级原则：**

> 先让现有链路 **可证明、可约束、敢给人用**，再扩 Connector / 第二 Skill。  
> 任何建议必须强化 `Skill → Policy → Plane → Trace`，否则进入 Won't Do。

**建议 Next 顺序（授权前仅规划）：**

| Rank | Theme | Why first |
|------|-------|-----------|
| **P0** | Evaluation Framework | 关闭最大可信度缺口；否则后续一切 AI 改动不可证伪 |
| **P0** | Trace-aligned cost rollup + soft budget | usage 已存在；无控制则企业叙事不完整 |
| **P1** | Thin SQL quality upgrades (schema linking lite + repair metrics) | 提升准确率且不破坏固定图/Policy |
| **P1** | Dataset/table-scoped permission deepen | 企业权限叙事的下一薄刀，不做 IAM |
| **P2** | Second Skill charter · thin Connector interface · ops scale | 扩张平台面；需 Lifecycle + Eval 先行 |

---

## Current Weakness Analysis

> 本节不重复优点。每个问题按统一模板描述，并标注类别：  
> **A** = 真正影响平台能力 · **B** = Demo 可接受 · **C** = 不建议解决（过度工程）

### W1 — AI Quality 不可证伪（A · P0）

| | |
|--|--|
| **问题** | 没有系统性 Evaluation Framework；CI 不测「问句→正确 SQL/结果」 |
| **当前状态** | Gate smoke、生命周期 smoke、LLM client smoke 存在；无黄金题集、无准确率基线、无 Prompt 回归门禁 |
| **为什么是问题** | `data.bi` 是平台第一 Skill；质量靠手工 Demo 无法支撑「企业可信任」 |
| **影响** | Prompt/模型/few-shot 任何改动都可能静默退化；简历/客户演示结果不可复现 |
| **严重程度** | **Critical** |
| **是否必须解决** | **是（P0）** — 平台可信度核心 |

### W2 — Cost 有 Trace 无控制面（A · P0–P1）

| | |
|--|--|
| **问题** | usage 落在 step/Trace，但无 workspace 预算、无超限策略、无汇总 API |
| **当前状态** | `LLMCallResult.usage` → `output_json.llm`；pipeline 可汇总 tokens；无 cost dashboard / quota |
| **为什么是问题** | 企业 Agent 叙事包含「可计量、可限制」；只有数字没有策略仍是观测玩具 |
| **影响** | 异常循环重试、报告二次 LLM 调用可造成不可预期账单 |
| **严重程度** | **High** |
| **是否必须解决** | **必须有 soft control（P0 thin）**；完整 FinOps dashboard 可 P1/P2 |

### W3 — Permission 停在 workspace role（A 薄 · P1）

| | |
|--|--|
| **问题** | 成员角色决定几乎一切；Dataset/表/列无独立 ACL；无 tenant 层 |
| **当前状态** | `permissions.py`：owner/analyst/viewer；workspace 成员内 viewer 可读全部 Dataset/Run |
| **为什么是问题** | 多数据集、敏感表场景下「同 workspace 全可见」不符合企业最小权限 |
| **影响** | 无法 Demo「某角色只能分析某表」；与 Policy allowlist 未对齐成统一授权故事 |
| **严重程度** | **Medium–High**（多用户前 High；单人 Demo 可接受） |
| **是否必须解决** | **薄加深值得做（P1）**；完整 tenant→column IAM **不建议（C）** |

### W4 — Text-to-SQL schema 理解偏弱（A · P1）

| | |
|--|--|
| **问题** | 全量列名+类型塞进 prompt；无列相关度筛选；无业务同义词；单表假设强 |
| **当前状态** | `prompts_sql.build_text_to_sql_prompts`；few-shot 启发式选 dim/metric；Gate 失败可回 generate（`max_retries`） |
| **为什么是问题** | 宽表/模糊业务用语时，列选错是准确率第一瓶颈，而非 JSON Mode |
| **影响** | policy_denied / 空结果 / 错误聚合；用户感知「AI 不行」 |
| **严重程度** | **High**（对 Skill 质量） |
| **是否必须解决** | **schema linking lite 值得做**；完整 semantic layer / glossary 产品 **暂缓/C** |

### W5 — SQL repair 非结构化（A/B · P1）

| | |
|--|--|
| **问题** | Gate/执行失败仅把 `gate_error` 拼回 prompt 再生成；无分类、无成功率指标 |
| **当前状态** | `route_after_validate` / `route_after_execute` → `generate_sql`；retry_count ≤ max_retries |
| **为什么是问题** | 重试成本不可见；无法区分「语法错 / 表名错 / 语义错」；Eval 难归因 |
| **影响** | token 浪费、Trace 噪音、质量改进无抓手 |
| **严重程度** | **Medium** |
| **是否必须解决** | **结构化 repair + 指标（P1）**；独立「SQL 自愈 Agent」**不做（C）** |

### W6 — 启发式 SQL 逃生舱稀释叙事（B）

| | |
|--|--|
| **问题** | `ALLOW_HEURISTIC_SQL` 无 key 也可跑通，混淆「LLM Skill」与「规则引擎」 |
| **当前状态** | 无 key / LLM 失败时 `_heuristic_sql` |
| **为什么是问题** | Demo 成功可能掩盖真实 LLM 失败率 |
| **影响** | Eval 基线污染；对外讲述需额外 disclaimer |
| **严重程度** | **Medium**（叙事）· Demo 可接受 |
| **是否必须解决** | **Eval 环境强制关启发式（P0 配套）**；产品路径可保留并在 Trace 标记 `sql_source=heuristic` |

### W7 — 协作式 timeout/cancel（B）

| | |
|--|--|
| **问题** | 终态诚实，但不保证立刻中断 LLM HTTP / DB 查询 |
| **当前状态** | Worker 线程池超时 + `cancel_requested` 轮询；文档已诚实披露 |
| **为什么是问题** | 生产可能短暂泄漏算力/连接 |
| **影响** | 成本与连接池压力；非正确性错误 |
| **严重程度** | **Medium**（生产）· Demo **可接受** |
| **是否必须解决** | **不必硬杀（C 若做成分布式 kill）**；可 P2 加 client timeout 收紧与连接上限 |

### W8 — Redis List 无 visibility timeout 产品化（B）

| | |
|--|--|
| **问题** | BRPOP 后进程崩溃依赖 stale reclaim，非 broker-native lease |
| **当前状态** | E3 reclaim + heartbeat；CAS claim |
| **为什么是问题** | 多 Worker / 脏杀场景下有短暂「任务悬挂」窗口 |
| **影响** | 可靠性边缘 case |
| **严重程度** | **Low–Medium** |
| **是否必须解决** | Demo **可接受**；多 Worker 前强化 runbook（P2）；**不做 Celery/Kafka（C）** |

### W9 — 单 Skill / 薄 Plane 扩展未二次证明（A 叙事 · P2）

| | |
|--|--|
| **问题** | Kernel 可注册多 Skill，产品路径实质锁定 `data.bi`；Plane 仅 file + postgres_ro |
| **当前状态** | Lifecycle enable/version；Facade 固定 skill_id |
| **为什么是问题** | 「Platform」主张仍差一次真实第二能力证明 |
| **影响** | 面试/客户可能质疑「是不是套壳 BI」 |
| **严重程度** | **Medium**（定位） |
| **是否必须解决** | **不阻塞 Eval/Cost**；在 Lifecycle + Eval 后做第二 Skill（P2） |

### W10 — 前端状态与 SSE 韧性偏 Demo（B）

| | |
|--|--|
| **问题** | Analyze 本地 `useState`；SSE 失败切 poll，无指数退避自动重连；错误提示偏粗 |
| **当前状态** | `taskEvents.subscribeTaskEvents` + poll fallback |
| **为什么是问题** | 长 Run / 网络抖动时 UX 不稳 |
| **影响** | Demo 体验；非平台治理正确性 |
| **严重程度** | **Low–Medium** |
| **是否必须解决** | **P2 UX**；不做 WebSocket/token stream（C） |

### W11 — 无多租户 tenant 模型（C 除非触发）

| | |
|--|--|
| **问题** | User→Workspace，无 Org/Tenant |
| **当前状态** | 单层 workspace |
| **为什么是问题** | SaaS 多公司隔离需要；当前产品非该阶段 |
| **影响** | 无法卖「企业租户套件」 |
| **严重程度** | N/A for current thesis |
| **是否必须解决** | **不建议现在做（C）** — 易滑向 IAM/Invite 套件 |

### 分类汇总

| 类别 | 问题 ID |
|------|---------|
| **A 真正影响平台能力** | W1, W2, W3(薄), W4, W5, W9 |
| **B Demo 可接受** | W6(产品路径), W7, W8, W10 |
| **C 不建议解决 / 过度工程** | 完整 IAM/tenant 树, Celery, 硬 kill, semantic layer 产品, 独立自愈 Agent |

---

## Architecture Risk Review

### R1 — Facade 与 Kernel 双入口漂移

| | |
|--|--|
| **风险** | Worker 经 `run_analysis`；若未来有人直接调 graph/nodes，绕过 Trace/Lifecycle |
| **缓解** | 保持 README 禁令 + smoke；第二 Skill 必须只经 Kernel |
| **行动** | P1：Eval/集成测试只允许 Facade/Kernel 入口 |

### R2 — Policy 与 Permission 两套「允许」未统一叙事

| | |
|--|--|
| **风险** | Shell RBAC 决定「能不能跑」；SQL Gate 决定「SQL 能不能碰表」；中间无 Dataset→allowlist 绑定的统一解释 |
| **缓解** | Trace 已有 policy_denied；缺「谁授权了这些表」字段 |
| **行动** | P1 Permission：Dataset 绑定表集合 + Trace 回显 `authorized_tables` |

### R3 — `result_json` 大包兼作 API/Artifact/兼容层

| | |
|--|--|
| **风险** | 长期体积与 schema 漂移；content_ref 依赖 blob 内路径 |
| **缓解** | M6 已拆 metadata；payload 仍在 JSON |
| **行动** | P2：文档化 content_ref 契约；避免过早拆对象存储 |

### R4 — 扩展时引入「框架宗教」

| | |
|--|--|
| **风险** | Skill SDK / Policy Engine / Event Bus / Connector Framework 一次上齐 → 身份漂移 |
| **判断** | **当前架构对下一阶段足够**（见 §4 扩展评估） |
| **行动** | 只补 **最小 interface**，不补平台产品 |

### R5 — Eval 若绕过 Policy

| | |
|--|--|
| **风险** | 离线「只比 SQL 字符串」会放过危险语句或忽略 Gate |
| **行动** | Eval **必须**跑完整 `Skill → Policy → Plane(可 fixture) → Trace` 路径 |

---

## AI Capability Gap

### 当前链路

```text
Question
  → Prompt (schema dump + few-shot + delimiters)
  → JSON Mode
  → SqlDraft
  → Gate (sql.select_gate)
  → Execute (Data Plane)
  → (fail) retry generate with gate_error
  → Charts / Report
```

### SQL 准确率瓶颈（按影响排序）

| # | 瓶颈 | 证据/机制 | 改进方向 |
|---|------|-----------|----------|
| 1 | **列/表选择错误（schema linking）** | 全列塞 prompt；宽表噪声大 | **Schema linking lite**：按问题关键词/类型筛 top-K 列进 prompt；Trace 记录 `selected_columns` |
| 2 | **业务语义缺口** | 无同义词（「销售额」↔`amount`） | **薄 glossary（可选）**：Dataset 级 JSON 映射；**不做**企业词汇表产品 |
| 3 | **方言/引用差异** | DuckDB vs Postgres 限定名 | 已有 dialect 提示；Eval 分 plane 基线 |
| 4 | **聚合/过滤意图误解** | 单轮生成 | Gate/执行错误分类后定向 repair；**不做**多 Agent planner |
| 5 | **JSON/格式失败** | 已有 SqlDraft + legacy fallback | 次要；继续以 Gate 为安全网 |
| 6 | **启发式污染** | Demo 逃生 | Eval 关闭启发式 |

**结论：** 最大瓶颈在 **schema 理解与列选择**，不在「缺 ReAct」。

### 候选能力取舍

| 能力 | 适合本项目？ | 理由 | 建议 |
|------|--------------|------|------|
| **Schema linking (lite)** | **是** | 强化 Skill 质量，仍走固定图 + Policy | **P1** |
| **SQL repair (structured)** | **是（薄）** | 把现有 retry 变成可度量、可分类 | **P1** |
| **Query planning** | **谨慎** | 多步计划易滑向 ReAct；单表场景收益有限 | **P2 仅当多表 JOIN 成为真实需求**；须仍是固定图节点，非自由循环 |
| **Semantic layer** | **薄映射可；产品不可** | Dataset 列别名 OK；指标中台是另一产品 | **P2 可选 glossary JSON** |
| **Business glossary** | **同上** | 与 semantic 合并为薄配置 | 不做独立 CMS |
| **RAG / Embedding** | **否** | 答案应来自 Plane SQL，不是文档块 | **Won't Do** |
| **ReAct / dynamic tools** | **否** | 对抗 Policy-before-execute | **Won't Do** |

### Evaluation 应否第一优先？

**是。** 理由：

1. 没有基线，W4/W5 的任何「准确率提升」无法验收。  
2. Cost/Permission 改动也可能间接影响重试次数与失败类分布，需要同一套回归。  
3. 符合架构：Eval 消费真实 `kernel.run` / Facade，强化而非绕过 spine。  
4. 成本低：golden fixtures + smoke gate 扩展，不必上 LangSmith。

### 黄金数据集如何设计？

**原则：** 小而硬、可自动跑、分平面、分失败类。

```text
evals/
  suites/
    file_duckdb/
      cases.yaml          # id, question, dataset_fixture, expect
    postgres_ro/
      cases.yaml
  fixtures/               # 小 CSV / SQL seed（可复用 docker RO demo）
```

**每条 case 建议字段：**

| 字段 | 含义 |
|------|------|
| `id` | 稳定 ID |
| `question` | 自然语言 |
| `plane` | `file` \| `postgres_ro` |
| `expect.sql_constraints` | 必须含/不得含的表名、关键字（非唯一金 SQL） |
| `expect.gate` | `allow` \| `deny` |
| `expect.row_checks` | 可选：聚合值、行数范围、列名集合 |
| `expect.failure_class` | 负例期望 |
| `tags` | `aggregate` \| `filter` \| `deny_write` \| `wrong_table` |

**评价 Text-to-SQL「成功率」建议采用分层指标（不要只报一个 %）：**

| 指标 | 定义 | 用途 |
|------|------|------|
| **Gate Pass Rate** | 最终 SQL 通过 Gate 的比例 | 安全/格式 |
| **Execute Success Rate** | 执行无 connector/skill 错 | 可运行性 |
| **Result Match Rate** | 结果满足 `row_checks` / 关键约束 | **主准确率** |
| **Exact SQL Match** | 可选、弱指标（同义 SQL 过多） | 仅回归哨兵 |
| **Repair Rate / Tokens per success** | 重试次数与 token | 成本与稳定性 |
| **Heuristic Avoidance** | Eval 中 heuristic 使用率应为 0 | 叙事诚实 |

**自动回归接入：**

```text
CI (existing release gate)
  └─ smoke_release_gate.py
       └─ (+P0) smoke_eval_golden.py --suite core --no-heuristic
```

- PR：跑 **core 小集**（秒–分钟级，可 mock LLM 的负例 Gate 集 + 可选录制响应）。  
- Nightly / 手动：跑 **full 集**（真实 LLM，需密钥，不挡每个 PR）。  
- 失败：输出 case id、实际 SQL、Gate reason、failure_class、Trace 摘要。

---

## Security & Governance Gap

### 当前 RBAC

```text
workspace
  └── member role (owner | analyst | viewer)
        ├── viewer: read Dataset/Run/Trace/Artifact
        └── owner/analyst: upload/bind/Analyze/cancel(creator|owner)
```

### 企业权限目标树 vs 本项目

```text
企业常见:
tenant → workspace → dataset → column/table policy → user role

本项目应追求（薄）:
workspace → dataset ACL → table allowlist (aligned with Policy) → role
         ↘ Trace 可解释「谁/何角色/何表」

不应追求（C）:
完整 tenant 套件 / SSO / SCIM / ABAC 引擎 / 列级动态脱敏产品
```

### 还差什么？

| 缺口 | 值得做？ | 说明 |
|------|----------|------|
| Dataset 级 read/run 授权（非成员即可见全部） | **P1 是** | viewer 可被限制到指定 dataset |
| Table allowlist 与 Dataset bind 显式绑定并进 Trace | **P1 是** | 统一 Permission ↔ Policy 叙事 |
| Column-level policy | **大多否** | 复杂度高；可用「禁止选敏感列」的 Gate 扩展作 P2 可选 |
| Tenant/Org | **否（现阶）** | 触发条件：真实多公司售卖 |
| Invite/SSO/IAM 套件 | **否** | Charter 禁区 |
| 行级安全 (RLS) 产品 | **否** | 交给源库 RO 角色；平台不重建 |

### Permission 建议薄切片（P1）

1. `dataset_acl` 或成员属性：`allowed_dataset_ids`（空=沿用今日全可见，兼容）。  
2. `run.create` 检查 dataset ACL。  
3. Trace/execution 增加 `actor_role` + `authorized_tables`。  
4. **不**把 RBAC 搬进 Kernel。

---

## Cost Control 深评估

| 问题 | 判断 |
|------|------|
| 当前 usage Trace 是否足够？ | **观测足够起步；控制不足** |
| token budget | **P0 soft**：workspace 或全局日/月 token 软上限，超限拒绝 **新** enqueue（429 + failure_class） |
| model routing | **P2**：仅当成本证据出现；简单 `LLM_MODEL` 配置已够 Demo |
| cost dashboard | **P1 thin**：Tasks 过滤 + 聚合 API（sum tokens by workspace/day）；不做 FinOps 产品 |
| quota | 与 budget 合并为同一控制面；按 workspace 即可 |

**P0 最小方案：**

- 从既有 steps/`platform.execution` 汇总 tokens。  
- Settings：`LLM_TOKEN_BUDGET_PER_DAY`（0=关闭）。  
- enqueue 前检查今日累计；超限 → 429。  
- Trace 标记 `budget_remaining`（可选）。  

**不做：** 按 token 计费引擎、多供应商套利路由、实时流式计费。

---

## Engineering Debt

### Backend

| 区域 | 现状 | 债等级 | 建议 |
|------|------|--------|------|
| FastAPI 结构 | routes → services → models 清晰 | Low | 保持；禁在 route 调 graph |
| Service 层 | task/dataset/permission/artifact 拆分合理 | Low | Permission 加深时避免上帝类 |
| Worker 可靠性 | reclaim/heartbeat/CAS 已有；同步 LLM | Medium | P0 Eval 优先；Async LLM 仅 P2 |
| Redis Queue | List + 深度帽；无 ack/lease | Medium (B) | 多 Worker runbook；不换 Celery |
| DB 模型 | Task/Steps/Artifacts/JSON 平台字段 | Medium | 文档化 JSON 契约；防无迁移改列 |
| Migration | Alembic 顺序良好 | Low | Eval 表若需要再开 0010+ |

### Frontend

| 区域 | 现状 | 债等级 | 建议 |
|------|------|--------|------|
| 状态管理 | 页内 useState + authStore | Low (B) | 够用；勿上重型状态框架 |
| SSE | 有 fallback poll；无自动重连 | Medium (B) | P2：断线后有限次重订阅 |
| 错误处理 | ApiError 字符串 | Low | 映射 429 capacity/budget 友好文案（随 P0） |
| UX | Trace/Artifacts 已有；成本不可见 | Medium | P1 展示 token 汇总 |

### DevOps

| 区域 | 现状 | 债等级 | 建议 |
|------|------|--------|------|
| Docker | api+worker+deps Compose | Low–Solid | 保持 |
| CI | release gate；无 LLM Eval | **High for AI** | P0 接入 golden gate（core） |
| 环境管理 | `.env.example` + OPS matrix | Solid | budget/eval 开关写入 matrix |
| 日志 | Request ID + JSON + run 字段 | Solid | cost/eval run 复用 |
| 部署 | Compose；非 K8s | 有意 | **Won't Do K8s**（本弧） |

---

## 平台扩展能力评估

```text
Kernel → Skill → Policy → Plane
```

### 若增加…

| 扩展 | 当前是否足够？ | 需提前补什么？ | 保持现在？ |
|------|----------------|----------------|------------|
| **第二个 Skill** | Lifecycle lite **基本够** | 书面 Skill charter；Eval 套件；Facade 勿写死业务假设 | **够用**；**不需要**完整 Skill SDK/marketplace |
| **新数据库 Connector** | 模式已证（注入 `execute_select`） | **薄** `DataPlaneExecutor` protocol（execute + health + dialect）；仍 Policy-first | **够用**；**不要** Connector Framework/Catalog |
| **更多 Policy** | registry 可挂多 policy_id | 第二 gate **函数**（如 row_budget）+ Trace；**不要** Policy DSL 引擎 | **够用** |
| **多租户** | **不够也不该现在补齐** | — | **保持** workspace 模型直至真实触发 |

### Skill SDK / Connector interface / Policy registry / Event system

| 提案 | 建议 | 原因 |
|------|------|------|
| **Skill SDK** | **不需要独立 SDK 包** | 现有 `RunRequest`/`RunResult`/registry 即契约；再包一层易成框架秀 |
| **Connector interface** | **P2 薄 Protocol** | 第三 plane 前用 typing Protocol 固化；禁止配置中心/凭证库产品 |
| **Policy registry** | **已有；深化即可** | 缺的是第二 *gate 种类*，不是 registry 重写 |
| **Event system** | **不需要** | SSE 轮询 DB 已够；上 Event Bus 是过度工程 |

**结论：保持现在的脊柱；扩展用「薄契约 + 新 Skill/Executor」，不预建平台中间件。**

---

## Prioritized Roadmap

### P0 — 必须解决（影响平台可信度）

#### P0-1 Evaluation Framework

| | |
|--|--|
| **目标** | 让 Text-to-SQL / Gate / Plane 改动可证伪、可回归 |
| **解决** | W1、支撑 W4/W5/W6 |
| **方案** | golden suites（file + postgres_ro）；分层指标；`smoke_eval_golden.py`；CI core 集；Eval 强制 `ALLOW_HEURISTIC_SQL=false` |
| **涉及文件（预期）** | `backend/scripts/smoke_eval_golden.py` · `evals/**`（新）· `smoke_release_gate.py` · `.github/workflows/ci.yml` · `docs/OPS_CONFIG_MATRIX.md` |
| **风险** | 金 SQL 过拟合；真实 LLM 不稳定 → core 集以 Gate/结果约束为主，LLM full 集夜间跑 |
| **验收标准** | 见 § Acceptance Criteria |

#### P0-2 Soft Cost / Token Budget

| | |
|--|--|
| **目标** | usage 从「看得见」变成「超限可拒」 |
| **解决** | W2 |
| **方案** | 日/workspace token 累计（从 steps 或 execution 汇总）；settings 开关；enqueue 前检查；429 + `failure_class`；日志/Trace 字段 |
| **涉及文件（预期）** | `config.py` · `task_service.py` · `runtime_essentials.py` 或新 `cost_budget.py` · `execution_trace` 汇总 · OPS matrix |
| **风险** | 汇总不准 / 时区；先做保守估算 + 文档限制 |
| **验收标准** | 超限无法 Analyze；未超限黄金路径不变 |

### P1 — 应该增强（企业级能力）

| ID | 主题 | 目标 | 要点 |
|----|------|------|------|
| **P1-1** | Schema linking lite | 提高列选择准确率 | top-K 列入 prompt；Trace `selected_columns`；进 Eval |
| **P1-2** | Structured SQL repair | 可度量重试 | 错误分类（gate_syntax / gate_table / execute）；指标进 Trace |
| **P1-3** | Permission deepen | Dataset ACL + allowlist 叙事 | Shell only；Trace `authorized_tables` |
| **P1-4** | Cost rollup API / UI | 运营可见 | workspace token 汇总；Analyze 显示本次 usage |
| **P1-5** | Eval full suite + nightly | 真实 LLM 回归 | 不挡每个 PR |

### P2 — 长期优化（规模化以后）

| ID | 主题 | 触发条件 |
|----|------|----------|
| **P2-1** | Second Skill（薄） | Lifecycle + Eval 稳定 + 书面 charter |
| **P2-2** | DataPlaneExecutor Protocol + 第三 RO 源 | 有真实第二库需求 |
| **P2-3** | Async LLM Client | Worker 阻塞成实测瓶颈 |
| **P2-4** | SSE 自动重连 / 友好 429 UX | Demo 投诉或长任务常态 |
| **P2-5** | 多 Worker 运维手册 + 连接上限 | 多进程部署前 |
| **P2-6** | 薄 glossary JSON | 业务同义词成为准确率主因 |
| **P2-7** | 固定图内「多表 plan」节点 | JOIN 成为真实产品需求（仍非 ReAct） |

---

## Implementation Plan

> **仍不授权编码。** 下列为建议切片顺序，供人工确认后开 checklist。

### Phase A — Evaluation Foundation（建议第一刀）

1. 定义 `evals/` 目录与 8–15 条 core cases（含 deny 负例）。  
2. Runner：经 Facade/Worker 或同进程 `run_analysis` + fixture plane。  
3. 指标报告 JSON + 非零退出码。  
4. 接入 `smoke_release_gate`（core）与 CI。  
5. 文档：如何加 case、如何解读指标。

### Phase B — Soft Budget

1. 汇总函数（task/workspace/day）。  
2. Settings + enqueue gate。  
3. Smoke：压满预算 → 429。  
4. OPS matrix 更新。

### Phase C — SQL Quality lite（依赖 A 的基线）

1. Schema linking lite + Trace 字段。  
2. Repair 分类。  
3. 对比 Eval 前后 Result Match / Repair Rate。

### Phase D — Permission deepen

1. Dataset ACL 薄模型。  
2. API 403/404 行为与 M5 一致精神。  
3. Smoke + Trace 字段。

### Phase E — Expansion（仅当 A–D 稳定）

1. Second Skill charter → 实现。  
2. 或 thin Connector Protocol → 第三 plane。

---

## Acceptance Criteria

### Evaluation Framework（P0-1）

- [ ] 存在可运行的 golden core suite（file + 至少若干 Gate 负例）。  
- [ ] Eval **默认关闭启发式 SQL**。  
- [ ] 报告输出分层指标（Gate / Execute / Result Match / Repair）。  
- [ ] `smoke_release_gate`（或 CI）失败当 core 退化。  
- [ ] Eval 路径经过 Policy（deny 例必须 `policy_denied`，不得 execute）。  
- [ ] 不引入 LangSmith/RAG/ReAct。

### Soft Cost Budget（P0-2）

- [ ] 可从既有 Trace/steps 得到 token 累计（允许文档化近似）。  
- [ ] 配置开启后超限 enqueue 返回 429 且 task 诚实失败类。  
- [ ] 关闭预算时行为与今日一致。  
- [ ] 无独立计费微服务。

### Schema linking / Repair（P1）

- [ ] Trace 可见 selected columns / repair class。  
- [ ] Eval Result Match 相对基线不回退（或有说明的有意变更）。  
- [ ] 仍为固定 LangGraph；无自由 tool loop。

### Permission deepen（P1）

- [ ] 可限制某成员对某 Dataset 的 Analyze。  
- [ ] Kernel 仍不导入 permissions。  
- [ ] 无 SSO/Invite/tenant 表（除非未来单独授权）。

---

## Won't Do

| Won't Do | 原因 |
|----------|------|
| **RAG / Embedding / Vector DB** | 产品答案在受控 SQL，不在文档检索；稀释 Policy/Plane |
| **ReAct / 自由 Tool Calling** | 对抗固定 Skill 图与 Policy-before-execute |
| **Multi-Agent 网格** | 单 Skill 质量未证伪前是戏剧；与 Charter 冲突 |
| **WebSocket** | SSE 已覆盖任务进度 |
| **Token Streaming / ChatGPT UX** | 非聊天产品；易泄中间推理 |
| **LangSmith 双轨 Trace** | Run Trace 已是真源 |
| **LLM/SQL Response Cache** | 错缓存成本高于延迟 |
| **Celery / Kafka / Event Store 改写** | Redis List + E3 已够 Demo/ops 命题 |
| **重构成微服务** | 边界已在进程内清晰；拆服务只加运维税 |
| **Kubernetes / Helm / Terraform / 云 CD** | 本弧止于 Compose + CI |
| **完整 IAM / SSO / SCIM / Invite 套件** | M5 薄 RBAC 是天花板直至硬触发 |
| **Tenant 树 + 列级 ABAC 引擎** | 过度工程；与 Data Agent 主线无关 |
| **Connector Framework / Catalog / ETL** | M3 证明薄平面即可；框架是另一公司 |
| **Report Center / PDF CMS / Artifact 市场** | 滑向 BI 文档产品 |
| **Code Agent / Git / Patch** | RepoPilot 域 |
| **独立 Skill SDK / Policy DSL / Event Bus「平台中间件」** | 现有契约足够；预防框架宗教 |
| **保证硬杀 in-flight LLM/DB** | 分布式杀进程产品；终态诚实已足够 |

**决策规则：** 若提案不能增强 `Skill → Policy → Data Plane → Trace`，默认拒绝。

---

## Final Recommendation（给决策者的一页）

| 现在就该授权的下一刀 | **Evaluation Framework（P0-1）** |
|----------------------|----------------------------------|
| 紧随其后 | Soft Token Budget（P0-2） |
| 有基线后再做 | Schema linking lite + Structured repair（P1） |
| 企业叙事加深 | Dataset ACL（P1），不是 IAM |
| 平台扩张 | 第二 Skill / 薄 Connector（P2），且需 charter |
| 明确不做 | RAG · ReAct · Multi-Agent · K8s · 微服务拆分 |

**本文件不授权任何编码。** 确认 P0-1 后，再单独开 checklist / 开发任务。

---

*End of PROJECT_IMPROVEMENT_PLAN.*
