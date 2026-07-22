# Enterprise AI Data Platform v2.0 Roadmap

**Document type:** Strategic roadmap（规划 only · **不授权编码**）  
**Date:** 2026-07-22  
**Baseline:** GitHub Release **v1.0.0** · tag `v1.0.0` · commit `ae8dc58` · Feature Freeze  
**Authors role:** Principal Software Architect + AI Platform Product Manager  
**Constraint:** 不修改代码 · 不安装依赖 · 不进入实现 · 不推翻 v1.0 脊柱

**Spine (immutable):**

```text
Product Shell → Worker → Kernel → Skill → Policy → Data Plane → Trace / Artifacts
```

**Related SSOT:** [`FINAL_RELEASE_AUDIT.md`](FINAL_RELEASE_AUDIT.md) · [`FINAL_STABILIZATION_REVIEW.md`](FINAL_STABILIZATION_REVIEW.md) · [`../project_upgrade_plan.md`](../project_upgrade_plan.md) · [`FINAL_RELEASE.md`](FINAL_RELEASE.md)

---

## Vision

把 v1.0.0 从「**可治理、可证明、可演示的 Data Agent 平台脊柱**」演进为：

> **Enterprise AI Data Platform v2.0** — 企业可试点落地的数据分析 Agent 平台：  
> 在同一治理合同下交付更高准确率、可运营的成本/质量闭环、可信身份与审计、可重复的云交付；  
> 并以 **受控的 Agentic BI / Human-in-the-loop** 形成差异化，而不是变成又一个 ChatGPT Wrapper、RAG Demo 或自由 Multi-Agent 玩具。

**v2.0 成功定义（非口号）：**

| 维度 | v1.0 | v2.0 目标 |
|------|------|-----------|
| 身份 | Governed platform spine（面试/演示级） | Pilot-ready enterprise data agent platform |
| 质量 | Eval 门禁存在 | Eval 驱动迭代；SQL 成功率与 repair 可度量提升 |
| 信任 | JWT + OIDC MVP | Refresh 可吊销 · 真实 IdP 联调 · 审计可导出 |
| 交付 | Compose 一键 | 单云可重复部署 + 密钥不落盘明文 |
| 差异化 | 双 Skill + Gate + Trace | Semantic/治理薄层 + HITL + 受控 Agent 协作（非自由 ReAct） |

**明确不追求的 v2.0：** 万能 Data Catalog 厂商、全量 Multi-Agent OS、RAG 问答主产品、多云齐上。

---

## Current v1.0 Assessment

### 1. 项目定位（级别判定）

| 级别 | 是否匹配 | 判定 |
|------|----------|------|
| Demo | ❌ 过低 | 远超「单页 Chat + 一次 LLM」；有 Kernel/Policy/Eval/ACL/Worker |
| Prototype | 🟡 部分 | 有产品壳与合同，但仍有 mock 默认、Compose 级部署 |
| Production Ready | ❌ 过高 | 无云 IaC、无 Refresh 吊销、无真实 IdP 浸泡、timeout 非协作取消 |
| Enterprise Platform | 🟡 脊柱级 | **架构与治理叙事已企业化**；运维/身份/规模化未企业化 |

**结论（诚实标签）：**

> **Enterprise Platform Foundation — Pilot / Interview / Staging-demo Ready**  
> 不是玩具 Demo，不是可对外 SLA 的 Production Ready，而是「企业级平台脊柱已冻结、可试点演示、带明确限制」的交付物。

**为什么：**  
Stabilization 自评约 **88% demo-ready**；脊柱 ~95%；Enterprise deploy **0%**。竞争力在**边界与可证明性**，短板在**落地与深度智能**。

### 2. 当前竞争力（相对常见 AI 项目）

| 常见形态 | 对方卖什么 | 本项目相对优势 |
|----------|------------|----------------|
| **ChatGPT Wrapper** | 对话体验 | Run 生命周期、失败分类、预算/容量、Trace/Artifacts |
| **LangChain Demo** | 快速拼装工具链 | Kernel 合同 + Facade 边界；不把框架当平台 |
| **RAG Demo** | 文档问答正确性 | 产品定义是受控 SQL 分析；Gate + allowlist + ACL |
| **Agent Demo / 自由 ReAct** | 「更智能的自主性」 | 固定 Skill 图可审计；Policy 强制；Eval 可回归 |

**最强资产（勿稀释）：**  
脊柱清晰 · 三重 SQL Gate · ACL→allowlist · ≥2 Skills · Eval + Release Gate · 诚实 `failure_class` · 元库≠数据面。

### 3. 当前短板

| 域 | 短板 |
|----|------|
| **架构** | Shell↔Kernel 目录耦合气味；Connector 代码三份复制；`DataPlane` protocol 未真正抽象；Worker 批末写 steps（非节点级流） |
| **AI 能力** | 单路径 Text-to-SQL 深度有限；Memory 仅同义词 MVP；无语义层/指标定义；Self-correction 仅 Gate 重试级；无模型路由策略产品化 |
| **产品** | Analyze 缺 Skill picker；无 HITL 审 SQL；无「分析师工作流」产品面；Budget 无 UI |
| **企业落地** | Wave 4 未启动；无 IaC；OIDC/MySQL 未生产浸泡；Secret 仍 `.env` 习惯 |
| **UX / Shell 缺口** | Analyze 仍偏手工 fetch/SSE；长 Run 黑盒感；**后端已有、前端薄或缺失：** Skill picker、`postgres-ro`/`mysql-ro` 绑定 UI、Dataset ACL 管理 UI、OIDC 登录入口 |
| **性能** | `list_tasks` N+1；Gate 最多 3×；`result_json` 膨胀；全局 in-flight 非 per-workspace 公平 |
| **安全** | Refresh `jti` 未吊销；token 在 localStorage；Guardrails 未覆盖 table_preview；timeout 孤儿 step |

---

## Problems

把短板收敛为 **v2.0 必须回答的问题**：

1. **可信运行时：** 超时/取消是否协作式、可审计、无孤儿写入？  
2. **会话与身份：** Refresh 能否吊销？真实 IdP 能否联调？密钥如何托管？  
3. **SQL 质量飞轮：** Linking / Repair / Eval 能否形成「失败→分类→回归」闭环？  
4. **语义与治理薄层：** 业务指标/同义词/表所有权能否进入 Gate 之前，而不做成 Catalog 重力井？  
5. **产品可感知：** Skill 选择、HITL 确认 SQL、预算/审计对用户可见吗？  
6. **可交付：** 他人能否按单云 runbook 重复拉起试点环境？  
7. **差异化边界：** 如何在「更 Agent」的同时**不**滑向自由 ReAct / RAG 主路径？

---

## Strategic Goals

| Goal ID | 目标 | 度量（示例） |
|---------|------|--------------|
| G1 | 运行时诚实与稳定 | cooperative cancel；无孤儿 step；Release Gate 持续绿 |
| G2 | 信任闭环 | refresh revoke；staging IdP；secrets 不进镜像 |
| G3 | AI 质量飞轮 | Eval core/quality 基线↑；repair_class 分布可看板 |
| G4 | 语义薄层进主路径 | 指标/同义词参与 linking；仍强制 Gate |
| G5 | 产品可试点 | Skill picker + HITL SQL approve；预算/审计只读 UI |
| G6 | 单云可交付 | 一家云 IaC + 告警；非多云 |
| G7 | 受控 Agentic 创新 | 规划/多角色仅在合同内；Human-in-the-loop 默认 |

**升级原则（继承并强化）：**

- 只加强化脊柱的能力；热门技术若稀释叙事 → **不做**。  
- Celery / K8s / Multi-Agent / Semantic Catalog **有证据再上**。  
- v2.0 = **Pilot-ready Enterprise AI Data Platform**，不是「技术名词展览馆」。

---

## Phase 1 — 必要优化（Stability & Production Hygiene）

**目标：** 在不解冻「花活」的前提下，把 v1.0 已知 P1/P2 债清到「敢给试点用户」的水位。  
**建议周期：** 4–8 周  
**对应旧 Wave：** Stabilization 遗留 + Wave 4 信任子集（先于重 IaC）

| 项 | 内容 | 优先级 |
|----|------|--------|
| P1.1 | Cooperative Run cancel / timeout（消除孤儿 step） | P0 |
| P1.2 | JWT refresh revoke / rotation（`jti` 落库或等价） | P0 |
| P1.3 | Memory TTL + per-workspace 容量帽 | P0 |
| P1.4 | `result_json` 热/冷或截断策略 | P1 |
| P1.5 | `list_tasks` N+1 / 列表索引与查询整形 | P1 |
| P1.6 | 默认/文档：演示 profile 强制 `ANALYSIS_RUNTIME=agent`；prod 启动校验 | P1 |
| P1.7 | Guardrails 覆盖 table_preview（可选分级） | P1 |
| P1.8 | Cookie vs localStorage 决策落地（或明确风险接受） | P1 |
| P1.9 | 技术债：Settings 注入清理、skill catalog 耦合减薄 | P2 |
| P1.10 | Frontend 壳补齐：Skill picker · RO 绑定 UI · ACL 管理入口 · TanStack/SSE 一致性（OIDC 登录 UI 可跟 Phase 1.2/IdP） | P1 |

**Phase 1 退出标准：**

- 超时/取消路径有契约测试；无已知孤儿写入场景  
- Refresh 可吊销；staging 有真实 IdP **或** 明确「仅密码+吊销」范围  
- Memory / result_json 有上限；Release Gate 仍绿  
- UI 可选 `data.profile`；演示默认 agent runtime

---

## Phase 2 — 核心竞争力增强（Differentiation）

**目标：** 让项目在简历与架构评审中，**明显区别于**普通 Agent/RAG Demo。  
**建议周期：** 8–16 周（可与 Phase 1 尾部重叠，但 AI 改动必须带 Eval 基线）

### 2.A AI 方向（受控增强，禁止自由环替换主路径）

| 主题 | v2.0 立场 | 做什么 | 不做什么 |
|------|-----------|--------|----------|
| **Agent 能力** | 加深固定 Skill 图 | Linking 深化、多跳 SQL 计划（仍封闭路径） | 用自由 ReAct 替换 `data.bi` |
| **Multi-Agent** | **有条件** | 「Planner + SQL Writer + Critic」**固定三角**，经 Kernel 编排 | 开放式 Agent 市场 / 自由协作 |
| **Planning** | 值得 | 查询计划节点（表选择→指标→SQL）写入 Trace | 通用任务规划 OS |
| **Memory** | 值得加深 | 分层：linking 同义词 / Run 摘要 / 用户偏好；TTL+ACL | 无限向量记忆当主存储 |
| **Evaluation** | **必须** | 扩展 golden；线上抽样；repair 成功率看板 | 只靠手工 Demo |
| **Self-correction** | 值得 | 按 `repair_class` 分支策略；Critic 只读审 SQL | 无限重试烧 token |
| **Tool orchestration** | 保持 Kernel | Tool 注册 + Policy；MCP 只读扩展 | 任意工具自由调用 |
| **Model routing** | 值得薄做 | 按阶段路由（linking 小模型 / SQL 强模型） | 复杂 AutoML 路由产品 |

### 2.B 数据方向（薄语义层，拒 Catalog 重力井）

| 主题 | v2.0 立场 | 做什么 | 不做什么 |
|------|-----------|--------|----------|
| **Semantic Layer** | **高价值薄层** | Workspace 级 metrics/dimensions/synonyms → linking | 完整 LookML/dbt 语义平台 |
| **Data Governance** | 策略延续 | Gate + ACL + 审计导出增强 | 独立治理套件 |
| **Metadata** | 值得 | Dataset schema 版本 + 质量标记进 Trace | 企业级 MDMS |
| **Lineage** | **轻量** | Run→SQL→tables 血缘边（审计用） | 全仓数据血缘平台 |
| **Knowledge Graph** | 观察 | 仅当同义词/关系爆炸时试点 | 主路径上 Neo4j |
| **Enterprise Data Catalog** | **不做大而全** | 可用「Dataset + ACL + 语义薄层」代替 | Collibra 级 Catalog |

**Phase 2 退出标准：**

- Eval 基线可引用提升或至少不回退  
- 至少一种「受控多角色」或「计划节点」在 Trace 可见  
- Workspace Semantic 薄层参与 linking 并仍过 Gate  
- 文档明确：仍非 RAG / 非自由 Multi-Agent OS

---

## Phase 3 — 企业级能力（Deploy & Trust at Scale）

**目标：** 从「能演示」到「能给企业试点环境」。  
**建议周期：** 一个季度级（原 Wave 4 升级为 v2.0 Phase 3）

### 是否值得加入（裁决）

| 能力 | 裁决 | 说明 |
|------|------|------|
| **Kubernetes** | 🟡 有条件 | Compose 足够个人/小试点；有副本/HPA 需求再上 |
| **Cloud Deployment** | ✅ 值得 | **单云**（AWS **或** 腾讯云二选一） |
| **Terraform / IaC** | ✅ 值得 | 可重复拉起；与 Secrets 一体 |
| **CI/CD 增强** | ✅ 值得 | 现有 CI → staging 部署门禁；非多环境花活 |
| **Monitoring** | ✅ 值得 | Prometheus 已有 → 告警 + 可选 Grafana/OTel |
| **Audit** | ✅ 值得 | Run/Authz/SQL 审计导出与保留策略 |
| **RBAC 增强** | ✅ 薄增强 | 角色细化 + 审计；不做完整 IAM 套件一次做完 |
| **Multi-tenancy** | 🟡 已有雏形 | Workspace 已是租户边界；强化隔离与配额即可 |
| **Billing/Quota** | ✅ 产品化 | 已有 soft token budget → FinOps UI + 更硬配额 |

**Phase 3 退出标准：**

- 他人按 runbook 在目标云拉起 API/Worker/依赖  
- 密钥走云 Secret；告警覆盖队列深度/`failure_class`/5xx  
- 审计导出可用；配额对管理员可见

---

## Phase 4 — 高级创新方向（Resume-deep · Controlled）

**目标：** 技术深度与简历竞争力，**不牺牲治理叙事**。  
**建议周期：** Phase 2–3 稳定后的 Initiative；默认**不并行全面铺开**

| 方向 | 价值 | 进入条件 | 风险 |
|------|------|----------|------|
| **Agentic BI** | 高 | Phase 2 语义薄层 + Eval 健康 | 被理解成「会聊天的 BI」 |
| **Autonomous Data Analyst** | 高（叙事） | HITL 默认开；自治仅在沙箱数据集 | 幻觉与越权 |
| **Multi-Agent Collaboration** | 中高 | 固定角色图 + Policy；禁止自由发现工具 | 调试/审计成本爆炸 |
| **Human-in-the-loop** | **极高** | Phase 1 UX 后即可启动 | 流程变慢（可接受） |
| **AI Data Governance** | 高 | Gate 决策可解释 + 策略版本化 | 做成合规空壳产品 |
| **Multimodal Analytics** | 低–中 | 独立 Initiative；有明确客户场景 | 稀释 Text-to-SQL 主叙事 |

**Phase 4 推荐切入顺序：**  
1) Human-in-the-loop SQL approve → 2) Agentic BI（计划+多步仍封闭）→ 3) 固定三角 Multi-Agent → 4) AI Governance 策略版本 → 5) Multimodal（最后/可外置）

---

## Technology Decisions

每个建议均按「技术 / 为什么 / 问题解决 / 收益 / 复杂度 / 风险 / 是否值得 / 优先级」裁决。

### D1. Cooperative cancel / timeout

| 字段 | 内容 |
|------|------|
| **技术** | 协作式取消令牌 / 阶段检查点；禁止硬杀后继续写 step |
| **为什么需要** | v1.0 已知 P1：超时可留孤儿 step，破坏 Trace 诚实性 |
| **解决什么问题** | 运行时真相与资源泄漏 |
| **收益** | 企业试点可信；面试可讲「诚实失败」落地 |
| **复杂度** | 中高 |
| **风险** | 改 Worker/Skill 契约；需回归 Eval |
| **是否值得** | ✅ 必须 |
| **优先级** | P0 · Phase 1 |

### D2. Refresh token revoke (`jti`)

| 字段 | 内容 |
|------|------|
| **技术** | Refresh `jti` 存储 + 吊销/轮换 API |
| **为什么需要** | 有 refresh 无吊销 = 会话治理缺口 |
| **解决什么问题** | 账号泄露、强制下线、离职收权 |
| **收益** | Trust 叙事完整 |
| **复杂度** | 中 |
| **风险** | 存储与清理策略 |
| **是否值得** | ✅ |
| **优先级** | P0 · Phase 1 |

### D3. Workspace Semantic Layer（薄）

| 字段 | 内容 |
|------|------|
| **技术** | metrics/dimensions/synonyms 配置 → schema linking |
| **为什么需要** | 纯 token-overlap 无法承载企业口径 |
| **解决什么问题** | 「销售额」等多义词；提升 SQL 准确率 |
| **收益** | 相对 RAG/Chat Demo 的数据域差异化 |
| **复杂度** | 中 |
| **风险** | 做成 Catalog 重力井 |
| **是否值得** | ✅（保持薄） |
| **优先级** | P1 · Phase 2 |

### D4. Fixed-role Multi-Agent（Planner / Writer / Critic）

| 字段 | 内容 |
|------|------|
| **技术** | Kernel 内固定三角；Critic 只产出 accept/reject+reason |
| **为什么需要** | 简历深度 + SQL 自检；仍可审计 |
| **解决什么问题** | 单模型一次生成脆弱 |
| **收益** | 「受控 Multi-Agent」叙事，区别于自由 Agent Demo |
| **复杂度** | 高 |
| **风险** | 成本×3；延迟；若设计成自由环则毁脊柱 |
| **是否值得** | 🟡 有条件（Eval 证明提升后） |
| **优先级** | P2 · Phase 2/4 |

### D5. Human-in-the-loop SQL approval

| 字段 | 内容 |
|------|------|
| **技术** | Run 状态 `awaiting_approval`；UI 展示 SQL+Gate 结果；通过后执行 |
| **为什么需要** | 企业不敢「自动跑库」；合规与信任 |
| **解决什么问题** | 自动执行恐惧；审计签字 |
| **收益** | 极高产品/面试差异化 |
| **复杂度** | 中 |
| **风险** | 流程变慢；状态机变复杂 |
| **是否值得** | ✅ 强烈建议 |
| **优先级** | P1 · Phase 2（可早于 Multi-Agent） |

### D6. Model routing（薄）

| 字段 | 内容 |
|------|------|
| **技术** | 按节点/阶段选择 model；统一 LLMClient |
| **为什么需要** | 成本与质量平衡；厂商锁定风险 |
| **解决什么问题** | 全程大模型贵；小模型写 SQL 弱 |
| **收益** | FinOps + 质量 |
| **复杂度** | 低–中 |
| **风险** | 配置爆炸 |
| **是否值得** | ✅ 薄做 |
| **优先级** | P2 · Phase 2 |

### D7. Single-cloud IaC + Secrets

| 字段 | 内容 |
|------|------|
| **技术** | Terraform（或云原生 IaC）+ Secret Manager；一家云 |
| **为什么需要** | Compose ≠ 企业试点交付 |
| **解决什么问题** | 不可重复部署、密钥落盘 |
| **收益** | Production path 可信 |
| **复杂度** | 高 |
| **风险** | 范围膨胀到多云/K8s |
| **是否值得** | ✅ |
| **优先级** | P1 · Phase 3 |

### D8. Kubernetes

| 字段 | 内容 |
|------|------|
| **技术** | Deploy/HPA/Secrets |
| **为什么需要** | 仅当多副本与弹性有证据 |
| **解决什么问题** | 单机 Compose 扩展上限 |
| **收益** | 运维叙事完整 |
| **复杂度** | 很高 |
| **风险** | 无流量证据时纯复杂度税 |
| **是否值得** | 🟡 有条件 |
| **优先级** | P3 · Phase 3 可选 |

### D9. Celery / 重队列

| 字段 | 内容 |
|------|------|
| **技术** | Celery/RQ 等 |
| **为什么需要** | 仅 Metrics 证明队列/延迟瓶颈 |
| **解决什么问题** | 吞吐与可见性 |
| **收益** | 规模化 |
| **复杂度** | 高 |
| **风险** | v1.0 红线「无证据先上」 |
| **是否值得** | ❌ 默认不做 |
| **优先级** | 触发器制 |

### D10. RAG / Vector 主路径

| 字段 | 内容 |
|------|------|
| **技术** | Embedding + Vector DB |
| **为什么需要** | 文档问答场景——**不是本产品定义** |
| **解决什么问题** | 非本平台主问题 |
| **收益** | 简历关键词（假收益） |
| **复杂度** | 高 |
| **风险** | 产品身份被改写 |
| **是否值得** | ❌ |
| **优先级** | Won't Do |

### D11. Lineage（轻量）

| 字段 | 内容 |
|------|------|
| **技术** | 从 Trace/SQL Gate 抽表级边持久化 |
| **为什么需要** | 审计「这次分析碰了哪些表」 |
| **解决什么问题** | 合规与影响分析入口 |
| **收益** | 治理叙事增强 |
| **复杂度** | 低–中 |
| **风险** | 做成全仓血缘平台 |
| **是否值得** | ✅ 轻量 |
| **优先级** | P2 · Phase 2/3 |

### D12. OpenTelemetry

| 字段 | 内容 |
|------|------|
| **技术** | OTel traces/metrics export |
| **为什么需要** | 跨 API/Worker/LLM 关联 |
| **解决什么问题** | 排障与延迟定位 |
| **收益** | 企业可观测完整度 |
| **复杂度** | 中 |
| **风险** | 先于告警策略则噪音 |
| **是否值得** | 🟡 在 Prometheus 告警之后 |
| **优先级** | P2 · Phase 3 |

---

## Risks

| 风险 | 影响 | 缓解 |
|------|------|------|
| **范围膨胀** | v2.0 变成 Catalog + Multi-Agent OS + 多云 | 本文件 Won't Do + 分 Phase 门禁；每 Phase 退出标准 |
| **自由 Agent 诱惑** | 毁掉 Gate/审计叙事 | Multi-Agent 仅固定角色图；Critic 不可直接执行 SQL |
| **过早 K8s/Celery** | 复杂度税、无收益 | Metrics 触发器；Compose/单云 VM 先试点 |
| **语义层做大** | 第二个产品重力井 | 仅 Workspace 配置；禁止独立 Catalog 服务优先 |
| **Eval 不随 AI 改动** | 质量不可证伪回退 | AI 切片强制带基线对比 |
| **安全表象** | 有 OIDC 无吊销/无 Secret | Phase 1 Trust 先于 Phase 4 花活 |
| **简历关键词堆砌** | 面试被问穿 | 每个技术对应问题/收益表（上文 Decisions） |

### Won't Do（v2.0 仍继承）

- RAG / Vector 作为主答案路径  
- 自由 ReAct 替换固定 Skill  
- LangChain/LlamaIndex 重写主路径  
- WebSocket token 聊天化  
- 无证据 Celery / 过早多云  
- Connector Framework / 全量 Data Catalog  
- Code Agent 域融合  

---

## Timeline

> 日历为规划建议，**需显式解冻授权后**才进入实现。v1.0.0 在授权前保持 Feature Freeze。

```text
Now (Frozen v1.0.0)
    │
    ├─ Phase 1  必要优化          ████████        ~4–8 weeks
    │            Trust + Runtime honesty + UX hygiene
    │
    ├─ Phase 2  核心竞争力        ████████████    ~8–16 weeks
    │            Semantic thin layer + Eval flywheel
    │            HITL + (optional) fixed-role agents
    │
    ├─ Phase 3  企业交付          ██████████      ~1 quarter
    │            Single-cloud IaC + Audit + Quota UI
    │            (K8s only if evidence)
    │
    └─ Phase 4  创新 Initiative   ████  (optional / parallel late)
                 Agentic BI · Autonomous analyst (sandboxed)
                 AI Governance versioning · Multimodal last
```

| Milestone | 一句话 |
|-----------|--------|
| **M1 — v1.1 Trust** | Phase 1 完成：可吊销会话 + 诚实取消 + 内存/结果上限 |
| **M2 — v1.5 Differentiated** | Phase 2 核心：语义薄层 + HITL + Eval 飞轮 |
| **M3 — v2.0 Pilot** | Phase 3 完成：单云可交付 + 审计/配额 |
| **M4 — v2.x Innovation** | Phase 4 选做：受控 Agentic BI / 固定 Multi-Agent |

**建议的「解冻第一刀」（需你确认其一，本文件不授权编码）：**

1. **P1.1 Cooperative cancel** — 若最在意运行时诚实性  
2. **P1.2 Refresh revoke** — 若最在意给真实用户/试点账号  
3. **P1.10 + HITL 原型设计**（先设计后编码）— 若最在意产品差异化  

---

## Appendix A — v1.0 → v2.0 Capability Map

| Capability | v1.0 | v2.0 Target |
|------------|------|-------------|
| Spine | ✅ Frozen | ✅ Keep |
| Dual Skills | ✅ | ✅ + UX picker |
| Gate + ACL | ✅ | ✅ + explainability |
| Eval Gate | ✅ | ✅ Flywheel |
| Memory | MVP | TTL + layered |
| OIDC / MCP | MVP | Soak + audit |
| Deploy | Compose | Single-cloud IaC |
| Agent depth | Fixed graph | Plan + optional fixed multi-role |
| HITL | ❌ | ✅ |
| Semantic | Synonyms only | Thin metrics layer |
| Catalog / RAG / free ReAct | ❌ | ❌ still |

---

## Appendix B — How to use this document

1. **本文件是 v2.0 战略规划**；实现仍须显式授权，并建议同期更新 `project_upgrade_plan.md` 实施切片。  
2. 未列入 Phase / Decisions / 触发器的工作 **默认不做**。  
3. 任何「更 Agent / 更智能」提案必须回答：是否仍经 Kernel→Policy→Plane→Trace。  
4. **保持 v1.0.0 Feature Freeze**，直到你选择解冻第一刀。

---

**Document status:** COMPLETE · **Code changes:** NONE · **Implementation authorized:** NO · **Baseline freeze:** v1.0.0 MAINTAINED
