# Resume Highlights — Enterprise Data Agent Platform

**项目名（建议写法）：** Governed Enterprise Data Agent Platform（可治理企业数据 Agent 平台）  
**角色：** 独立设计与实现（架构 + 后端 + Agent Kernel + Eval + 前端工作台）  
**版本：** v1.0 Feature Freeze

---

## 1. 一句话亮点（选 3～5 条写入简历）

1. 设计并实现 **Product Shell → Worker → Kernel → Skill → Policy → Data Plane → Trace** 企业数据 Agent 脊柱，拒绝 Chat Demo / 自由 ReAct 叙事。  
2. 落地 **三重 SQL Gate** 与 Dataset ACL→allowlist 投影，保证分析 SQL 只读、可审计、最小权限。  
3. 在同一 Kernel/Lifecycle 合同下交付 **第二 Data Skill（`data.profile`）**，证明平台可扩展而非单 Skill 应用。  
4. 建立 **Eval 黄金集 + Release Gate**（core/quality/profile），将 Prompt/Skill 变更纳入可回归质量门禁。  
5. 完成 Run 治理闭环：timeout/cancel/`failure_class`、容量与软成本预算、JWT Refresh、可选 OIDC/MCP MVP。  

---

## 2. STAR 描述（可贴「项目经历」）

**Situation**  
企业数据分析场景需要「可问数、可治理、可证明」的 Agent 能力，但市面常见方案是 Chat + LangChain/RAG/多 Agent，边界模糊、难审计、难作为企业试点。

**Task**  
独立构建一套 Enterprise Data Agent Platform：以固定 Skill 图完成 Text-to-SQL 分析，同时用平台合同承载权限、数据面、生命周期与质量门禁；并证明可扩展到第二个 Data Skill。

**Action**  
- 冻结架构脊柱并实现 FastAPI 产品壳、Redis Worker、LangGraph 固定流水线 Skill、sqlparse Policy Gate、DuckDB/Postgres（可选 MySQL）只读平面。  
- 实现 Execution Trace / Artifacts / `failure_class`、Dataset ACL、Schema Linking、Eval 套件与 Compose/Prometheus 运维面。  
- Wave 3 以统一接口交付 `data.profile`、Workspace Memory、Idempotency、Guardrails 与可选 OIDC/MCP；Stabilization 加固 SSRF/state、MCP ACL、幂等与文档对齐后 **v1.0 Feature Freeze**。

**Result**  
形成可演示、可回归、可讲述取舍的企业级平台叙事；Release Gate（Smoke + Eval + Lint + Build）全绿；明确 Won't Do 与 Wave 4 仅部署深化，避免范围膨胀。

---

## 3. 面试可重点讲解的技术点

| 主题 | 你要会讲清的点 |
|------|----------------|
| 为什么不用 ReAct 主路径 | 治理优先：工具选择必须受 Policy/合同约束，自由环难审计 |
| 三重 Gate | Skill validate · Tool wrapper · Plane re-gate；纵深防御而非重复劳动口号 |
| Facade 边界 | Worker 只调 `run_analysis`，禁止直接 import graph/nodes |
| 元数据库 ≠ 数据面 | `DATABASE_URL` vs `POSTGRES_RO_DSN` / `MYSQL_RO_DSN` |
| Skill 扩展证明 | `data.profile` 共享 registry/lifecycle/worker，无特殊分支 |
| Eval 门禁 | heuristic 强制关闭；基线回归；Prompt 变更有 gate 文档 |
| 失败诚实性 | `timed_out` / `cancelled` / `policy_denied` / `budget_rejected` 等 |
| ACL→Gate | `tables_json` 与 allowlist 交集，权限故事与 SQL 故事合一 |

---

## 4. 企业级能力体现（对照「玩具 Demo」）

| 企业关切 | 本项目对应 |
|----------|------------|
| 最小权限 | Workspace 角色 + Dataset ACL + Gate allowlist |
| 可审计 | Trace steps · Artifacts · authorization snapshot |
| 可运维 | Compose · health/ready · `/metrics` · Worker health · release gate |
| 可限流/可预算 | Redis rate limit · soft token budget · capacity |
| 可身份接入 | JWT refresh · 可选 OIDC（issuer-host SSRF guard + state） |
| 可变而不瞎改 | Eval + Prompt Change Gate + Feature Freeze |
| 边界清晰 | Won't Do 清单写进路线图与交付文档 |

---

## 5. 简历条目示例（中英可择一）

**中文示例**  
> 独立设计实现 Enterprise Data Agent Platform（v1.0）：Kernel 调度多 Data Skill，Policy 强制只读 SQL，Worker 治理 Run 生命周期；含 ACL、Eval 回归门禁与可选 SSO/MCP；相对 Chat/RAG Demo 强调可治理与可证明。

**English example**  
> Designed and shipped a governed Enterprise Data Agent Platform (v1.0): Kernel-hosted Data Skills behind a deterministic SQL Policy Gate, with Run lifecycle governance, ACL→allowlist projection, and eval-backed release gates—positioned against chat/RAG demos as an auditable data-agent spine.
