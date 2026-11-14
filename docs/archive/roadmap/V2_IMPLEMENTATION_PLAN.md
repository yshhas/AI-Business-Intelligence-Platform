# V2 Implementation Plan — Phase 1 → v1.1

**Document type:** Engineering execution plan（**规划 only · 不授权编码**）  
**Date:** 2026-07-22  
**Baseline:** v1.0.0 Feature Freeze · tag `v1.0.0` · commit `ae8dc58`  
**Strategy SSOT:** [`ROADMAP_V2.md`](ROADMAP_V2.md)  
**Constraint:** 不修改代码 · 不创建 issue · 不执行 git · 不进入开发

**Spine (immutable):**

```text
Product Shell → Worker → Kernel → Skill → Policy → Data Plane → Trace / Artifacts
```

---

## 第一部分：执行优先级重新评估

> 对 Phase 1 任务逐项重评。P1.9（Settings/catalog 耦合）标为 P2，**不纳入本计划 Sprint 主线**，仅在附录提及。

### P1.1 Cooperative cancel / timeout

| 维度 | 评估 |
|------|------|
| **为什么现在做** | Stabilization P1：`ThreadPoolExecutor` + `FuturesTimeout` 硬超时后，Skill 线程可能仍写 step / 部分 `result_json`，破坏 Trace 诚实性与终态单一真相。企业试点与面试都依赖「失败诚实」。 |
| **依赖关系** | 无硬前置。与 P1.4（终态 payload 形状）弱相关；应先于任何「增量 steps」幻想。 |
| **修改范围** | 预期：`analysis_worker.py`（取消令牌/检查点）、`run_lifecycle.py`、可选 `agent/runtime.py` / Skill 循环内协作点、smoke（cancel/timeout）；**不**改 Gate 语义。 |
| **风险** | 中高。竞态与「半写」难测；设计不当会假死或丢 Trace。 |
| **预计复杂度** | **High**（设计 + 契约测试） |
| **是否影响 Spine** | **否（强化 Worker→Trace 诚实性）**。不改 Kernel/Policy 合同方向。 |
| **是否影响 Release Gate** | **是**。需扩展/加固 cancel & timeout smoke；Gate 必须仍绿。 |

### P1.2 Refresh revoke / rotation（`jti`）

| 维度 | 评估 |
|------|------|
| **为什么现在做** | `security.py` 已发 `jti` 但未用于吊销；有 Refresh 无收权 = Trust 叙事缺口。试点账号/强制下线刚需。 |
| **依赖关系** | 无。可与 P1.1 并行。P1.8（Cookie）可后置决策，但 revoke API 先落地。OIDC 回调仍走同一 token pair。 |
| **修改范围** | `security.py`、`routes_auth.py`、新表/迁移（refresh sessions）、logout/revoke 端点、frontend auth store 登出清会话；docs `API_ERROR_CODES` / OIDC。 |
| **风险** | 中。迁移与清理策略；多设备会话语义需定义清楚。 |
| **预计复杂度** | **Medium** |
| **是否影响 Spine** | **否**。仅 Shell Auth 面。 |
| **是否影响 Release Gate** | **是**。`smoke_auth_refresh` 需覆盖 revoke / 拒绝已吊销 refresh。 |

### P1.3 Memory TTL + per-workspace 容量帽

| 维度 | 评估 |
|------|------|
| **为什么现在做** | Workspace linking memory 无界增长（P2→升 P0 运营债）；写入路径在 Worker 成功后（`agent_runtime.py`）。 |
| **依赖关系** | 无硬前置。不依赖 Semantic Layer（Phase 2）。 |
| **修改范围** | `workspace_memory.py`、模型/迁移（`expires_at` 或 LRU 元数据）、config 帽、写入前 prune、可选定时清理；docs `WORKSPACE_MEMORY.md`。 |
| **风险** | 低–中。误删同义词影响 linking 质量（可接受，有 Eval）。 |
| **预计复杂度** | **Low–Medium** |
| **是否影响 Spine** | **否**。Shell 旁路服务；Skill 仍经同一 linking 入口。 |
| **是否影响 Release Gate** | **弱影响**。wave3/memory smoke 需覆盖 cap/TTL 行为。 |

### P1.4 `result_json` 热/冷或截断

| 维度 | 评估 |
|------|------|
| **为什么现在做** | 大 JSON 落 Postgres 导致表膨胀、备份与列表变慢；Artifacts 已部分外置，热字段可裁。 |
| **依赖关系** | 建议 **在 P1.1 之后**：终态写入路径稳定后再改 payload 策略。与 Trace UI 契约相关。 |
| **修改范围** | Worker 持久化路径、`artifact_service`、可选冷存（对象/表）、API 读路径兼容、前端对缺失大字段兜底。 |
| **风险** | 中。破坏 `result_json` 消费者；需版本化/`platform` 兼容。 |
| **预计复杂度** | **Medium–High** |
| **是否影响 Spine** | **弱影响 Trace 投影**，不改 Kernel→Policy→Plane 方向；Facade 输出形状需向后兼容。 |
| **是否影响 Release Gate** | **是**。契约/smoke 与 Trace 相关用例需更新。 |

### P1.5 `list_tasks` N+1

| 维度 | 评估 |
|------|------|
| **为什么现在做** | 列表规模一上来就痛；改动面小、收益确定；不挡产品叙事。 |
| **依赖关系** | 无。可与几乎任何项并行。 |
| **修改范围** | `task_service.list_tasks`、可能 joinedload/子查询、已有索引审计（`0012_task_list_index` 等）。 |
| **风险** | 低。 |
| **预计复杂度** | **Low** |
| **是否影响 Spine** | **否**。纯 Shell 读路径。 |
| **是否影响 Release Gate** | **基本否**（除非加回归测）。建议补一条列表性能/正确性 smoke。 |

### P1.6 Runtime profile（`ANALYSIS_RUNTIME`）

| 维度 | 评估 |
|------|------|
| **为什么现在做** | 默认 `mock` 易导致「演示翻车」；生产 profile 应拒绝误配置。 |
| **依赖关系** | 无。文档 + 启动校验即可先做。 |
| **修改范围** | `config.py` `assert_boot_*`、`.env.example`、Compose 演示 profile、README/OPS、CI 已用 `agent` 保持。 |
| **风险** | 低。本地骨架开发者需显式 `mock`。 |
| **预计复杂度** | **Low** |
| **是否影响 Spine** | **否**。 |
| **是否影响 Release Gate** | **弱**。config hardening smoke 已存在，扩展断言即可。 |

### P1.7 Guardrails 覆盖 `table_preview`

| 维度 | 评估 |
|------|------|
| **为什么现在做** | 输出脱敏不完整；`table_preview` 可能泄漏邮箱/密钥形态。 |
| **依赖关系** | 无。落在 Facade 输出层（`agent` guardrails），与 Worker 编排无关。 |
| **修改范围** | `agent/guardrails.py`、Facade 调用点、wave3 guardrails smoke、可选分级配置。 |
| **风险** | 低–中。过度脱敏影响 Demo 观感；需可配置。 |
| **预计复杂度** | **Low–Medium** |
| **是否影响 Spine** | **否**。Trace/Artifacts **之后**的输出硬化；不改 Policy SQL 语义。 |
| **是否影响 Release Gate** | **是**。guardrails 用例扩展。 |

### P1.8 Cookie / token 存储策略

| 维度 | 评估 |
|------|------|
| **为什么现在做** | localStorage XSS 风险已知；企业评审常问。但**完整 HttpOnly Cookie 方案**牵涉 CSRF、跨域、刷新流。 |
| **依赖关系** | 建议 **P1.2 之后**：先有 revoke，再决定 Cookie 或「风险接受 + 文档」。 |
| **修改范围** | 决策文档 +（若落地）auth 路由 Set-Cookie、前端去 localStorage、CORS/CSRF；或仅 ADR「接受 localStorage + 短 TTL + revoke」。 |
| **风险** | 落地则中高；仅 ADR 则低。 |
| **预计复杂度** | **决策 Low / 落地 High** |
| **是否影响 Spine** | **否**。 |
| **是否影响 Release Gate** | 落地则是；ADR-only 则否。 |

### P1.10 Frontend UX 壳补齐（+ HITL Design 预研）

| 维度 | 评估 |
|------|------|
| **为什么现在做** | API 已支持 `skill_id` / RO / ACL / OIDC MVP，**产品不可感知**削弱「平台」叙事；Skill picker 成本低、证明双 Skill。HITL **本 Phase 仅设计**，不实现状态机。 |
| **依赖关系** | Skill picker / RO / ACL UI **无硬后端依赖**。OIDC 登录 UI 弱依赖 IdP 配置。HITL Design 依赖对 Run 状态扩展的草案（实现进 v1.2+）。 |
| **修改范围** | `AnalyzePage`、`DatasetsPage`、新 ACL 面板、api client 接线、可选 OIDC 入口；**HITL：仅** `docs/` 设计 + 状态机草图，不改 Worker。 |
| **风险** | UX 中低。避免在 v1.1 偷渡 Phase 2 HITL 实现。 |
| **预计复杂度** | UX **Medium**；HITL Design **Low** |
| **是否影响 Spine** | UX **否**。HITL 实现若偷渡会改 Shell→Worker 状态机——**本计划禁止实现**。 |
| **是否影响 Release Gate** | 前端 lint/build；可选 Playwright/手工清单。后端 Gate 通常不变。 |

### 优先级重排（执行视角）

| 秩 | ID | 理由 |
|----|-----|------|
| 1 | **P1.1** | 诚实运行时；企业/面试核心可信度；唯一真正触及「Run 终态正确性」的硬伤 |
| 2 | **P1.2** | Trust 闭环；与 P1.1 正交可并行，但叙事上并列 P0 |
| 3 | **P1.6 + P1.5** | 低成本卫生项，快速降低演示翻车与列表债 |
| 4 | **P1.3 + P1.7** | 运营/合规边界，复杂度可控 |
| 5 | **P1.10** | 产品可感知；证明双 Skill；HITL 只设计 |
| 6 | **P1.4** | 有价值但契约面大，放在 cancel 稳定后 |
| 7 | **P1.8** | 先 ADR；完整 Cookie 不挡 v1.1 退出（除非选落地） |

---

## 第二部分：推荐执行顺序（Sprints）

> 假设 **4 个 Sprint × ~1–2 周**（合计约 4–8 周，对齐 Roadmap Phase 1）。仍 **不授权编码**。

### Sprint 1 — Runtime Honesty Foundation

| 字段 | 内容 |
|------|------|
| **目标** | 消除超时/取消孤儿写入；确立协作取消契约 |
| **任务** | P1.1 设计评审 → 实现协作检查点 → cancel/timeout 契约测试；并行启动 P1.6 配置/文档硬化 |
| **涉及模块** | `backend/app/workers/analysis_worker.py`、`run_lifecycle.py`、可选 `agent/runtime.py` / Skill 循环；`config.py`、`.env.example`、OPS docs |
| **验收标准** | 超时与取消后：终态唯一；无新增 step 写入；`failure_class` 正确；演示 profile 文档强制 `agent`；prod/staging 启动校验覆盖 runtime |
| **测试要求** | 扩展 smoke：cancel-before-start / cancel-during / timeout；Release Gate 全绿；禁止跳过既有 lifecycle smoke |

### Sprint 2 — Trust & Read-path Hygiene

| 字段 | 内容 |
|------|------|
| **目标** | Refresh 可吊销；列表与 memory 边界可控 |
| **任务** | P1.2 `jti` 存储 + revoke/logout；P1.5 `list_tasks` 查询整形；P1.3 TTL/容量帽 |
| **涉及模块** | `security.py`、`routes_auth.py`、Alembic、frontend auth；`task_service.py`；`workspace_memory.py` + 模型 |
| **验收标准** | 吊销后 refresh 401；logout 失效既有 refresh；任务列表无 N+1（查询次数有断言或 explain）；memory 超帽拒绝/淘汰有文档行为 |
| **测试要求** | `smoke_auth_refresh` 扩展；memory/wave3 smoke；可选列表查询计数单测；Release Gate 全绿 |

### Sprint 3 — Product Shell Visibility

| 字段 | 内容 |
|------|------|
| **目标** | 双 Skill / RO / ACL **可被用户操作**；输出脱敏补全；HITL 仅设计 |
| **任务** | P1.10 Skill picker + RO 绑定 UI + ACL 管理入口 + Analyze SSE/Query 一致性；P1.7 `table_preview` guardrails；**HITL Design 文档**（状态：`awaiting_approval` 草案、API、不实现） |
| **涉及模块** | `frontend/src/pages/*`、`api/*`、`components/*`；`agent/guardrails.py`；`docs/` HITL ADR |
| **验收标准** | UI 可选手动 `data.profile`；可绑定 postgres-ro（mysql-ro 至少有入口或明确 disabled）；ACL 可读写可见表集；guardrails 单测覆盖预览脱敏；HITL ADR 评审通过且标明 **Non-goal for v1.1 code** |
| **测试要求** | frontend lint/build；guardrails smoke；手工 UX 清单（写入 `docs/demo.md` 补丁计划，实现阶段再改） |

### Sprint 4 — Payload Discipline & Token ADR → v1.1 Freeze

| 字段 | 内容 |
|------|------|
| **目标** | `result_json` 膨胀受控；Cookie 策略落地为 ADR 或最小实现；准备 v1.1 Release |
| **任务** | P1.4 截断/冷热策略（兼容读）；P1.8 ADR（推荐默认）或经批准的 Cookie MVP；全量回归；撰写 v1.1 notes |
| **涉及模块** | Worker 持久化、artifacts、API 读兼容、前端兜底；auth ADR；CHANGELOG/RELEASE_NOTES（实现阶段） |
| **验收标准** | 大结果不撑爆热表（有上限或外置）；旧客户端仍可读关键字段；ADR 明确 XSS/CSRF 取舍；Release Gate + Eval core/quality/profile 绿 |
| **测试要求** | 契约/smoke 覆盖裁剪后 Trace；全量 `smoke_release_gate`；前端 build |

```text
Sprint 1: P1.1 + P1.6
Sprint 2: P1.2 + P1.5 + P1.3
Sprint 3: P1.10 + P1.7 + HITL Design-only
Sprint 4: P1.4 + P1.8(ADR) + v1.1 exit
```

---

## 第三部分：架构影响分析

| 改动 | Shell | Worker | Kernel | Skill | Policy | Data Plane | Trace | 如何保持脊柱 |
|------|:-----:|:------:|:------:|:-----:|:------:|:----------:|:-----:|--------------|
| **P1.1** | ○ | ● | ○ | ◐ 检查点 | ○ | ○ | ● 终态诚实 | 取消/超时仍只经 Worker 治理；Skill 仅响应协作信号，**不**绕过 Facade；终态与 Trace 仍由 Worker 落库 |
| **P1.2** | ● | ○ | ○ | ○ | ○ | ○ | ○ | 纯 Auth；Analyze 链路不变 |
| **P1.3** | ● 服务 | ◐ 写回 | ○ | ○ linking 消费 | ○ | ○ | ○ | Memory 仍是 Shell 旁路；Skill 不直连 DB |
| **P1.4** | ◐ 读兼容 | ● 写策略 | ○ | ○ | ○ | ○ | ● 投影 | Facade 合同保持；冷热是持久化策略，不是新执行路径 |
| **P1.5** | ● | ○ | ○ | ○ | ○ | ○ | ○ | 只读 API |
| **P1.6** | ● 配置 | ◐ 分支已有 | ○ | ○ | ○ | ○ | ○ | 不新增 runtime 类型 |
| **P1.7** | ○ | ○ | ○ | ○ | ○ | ○ | ◐ 展示数据 | Guardrails 挂在 Facade 输出之后，**不**进 Policy 替代 Gate |
| **P1.8** | ● | ○ | ○ | ○ | ○ | ○ | ○ | 会话存储与 Run 脊柱正交 |
| **P1.10** | ● UI | ○ | ○ | ○ 可调用已有 | ○ | ◐ 绑定已有 API | ◐ 展示 | UI 只消费现有 API；禁止前端直连 Agent；HITL **设计不落代码**以免偷改状态机 |

**图例：** ● 主要改动 · ◐ 次要/协作 · ○ 无

**脊柱不变量（实现阶段检查清单）：**

1. Worker **只**调用 `agent.runtime.run_analysis`（Facade）。  
2. SQL 仍必须经 Policy Gate（及 Plane re-gate）；Guardrails ≠ Gate。  
3. 新 Run 状态（若未来 HITL）必须先改 Shell 合同文档，再改 Worker，**禁止** Skill 自行「聊天确认」。  
4. 元数据库 ≠ RO 数据面 DSN 分离保持。  
5. Eval / Release Gate 红则禁止标 v1.1。

---

## 第四部分：v1.1 Release 定义

### Enterprise AI Data Platform v1.1

| 字段 | 定义 |
|------|------|
| **Release Goal** | 在 **不推翻 v1.0 脊柱、不进入 Wave 4 重 IaC / Phase 2 语义花活** 的前提下，交付 **Trust + Runtime Honesty + Product Visibility** 的小版本，使试点用户与面试官可感知「可取消、可收权、可选手动 Skill、结果与记忆有界」。 |
| **Version** | `1.1.0`（建议 tag `v1.1.0`，基于解冻后的 main） |
| **Feature Scope** | P1.1 Cooperative cancel/timeout · P1.2 Refresh revoke · P1.3 Memory TTL/cap · P1.4 result 边界 · P1.5 list_tasks · P1.6 runtime profile · P1.7 table_preview guardrails · P1.8 Token 策略 ADR（或已批准 Cookie MVP）· P1.10 Frontend 壳（Skill picker / RO / ACL UI）· HITL **设计文档 only** |
| **Non-goals** | 单云 Terraform/K8s · 真实 IdP 生产浸泡（可列为 staging 可选）· Semantic Layer · 固定 Multi-Agent · HITL **代码** · Celery · RAG/ReAct · Catalog · Cookie 完整方案若未在 Sprint 4 显式批准 · P1.9 大重构 |
| **Exit Criteria** | ① Release Gate + Eval core/quality/profile **PASS** ② cancel/timeout/revoke 有自动化覆盖 ③ UI 可演示 `data.profile` 与 ACL/RO 之一 ④ Memory/`result_json` 有文档化上限 ⑤ `ANALYSIS_RUNTIME` 演示/生产路径无默認翻车 ⑥ CHANGELOG + RELEASE_NOTES + 审计文档更新 ⑦ **未**引入 Won't Do 项 |

**v1.1 一句话定位：**  
> v1.0 = 可治理脊柱已冻结；**v1.1 = 敢交给试点的诚实运行时与可见产品壳**。

---

## 第五部分：第一刀建议

### 推荐启动项：**P1.1 Cooperative cancel / timeout**

| 维度 | 论证 |
|------|------|
| **技术收益** | 修复 Run 终态与 Trace 一致性这一**结构性**缺陷；为后续 P1.4、未来增量 steps、HITL 状态机提供正确前提。 |
| **风险** | 中高但可隔离在 Worker（+少量 Skill 检查点）；不碰 Gate/Plane 语义；可用现有 cancel/timeout smoke 做安全网。 |
| **简历价值** | 能讲清「壁钟超时 vs 协作取消」「孤儿 writer」「failure_class 诚实性」——比 UI 壳或纯 CRUD revoke **更像资深运行时/平台**。 |
| **企业落地价值** | 试点最怕「取消了还在写库 / 超时状态撒谎」；这是信任前提，而非锦上添花。 |

### 为什么现在做它？

- Stabilization 已标 **P1** 且延期理由是「需要设计」，不是「不重要」。  
- 当前实现已有 cancel 标志与 `FuturesTimeout`，但协作深度不足——属于**完成正确性**，不是新功能冲动。  
- 不依赖云、IdP、前端大改，可在 Freeze 解冻后单刀切入。

### 为什么不是其他？

| 选项 | 为何不作为第一刀 |
|------|------------------|
| **P1.2 Refresh revoke** | 收益高且可并行，但是 **Auth 面**；不修复「分析 Run 是否撒谎」。可作 Sprint 2 首项或与 Sprint 1 **双轨**（若人力≥2）。单人时仍建议先 P1.1。 |
| **P1.10 + HITL Design** | 产品可见性好、简历「有界面」，但若运行时仍可能孤儿写，UI 更光鲜也难称企业试点。HITL **实现**更不应第一刀（状态机膨胀）。Design-only 可作 Sprint 1 文档旁路，不替代 P1.1。 |
| **P1.5 / P1.6** | 优秀「热身」，应作 P1.1 的并行小切片，不能当主叙事第一刀。 |

### 完成后项目能力提升

1. **诚实运行时：** cancel/timeout 后 Trace 与 DB 终态一致，可对外讲述。  
2. **试点信心：** 管理员取消分析不会留下幽灵写入。  
3. **架构债权下降：** 为 v1.1 其余项与未来 HITL 扫清「终态模型」地雷。  
4. **Gate 更强：** 强制补齐 lifecycle 自动化，回归网更密。

### 解冻后建议动作（仍不在本文执行）

1. 显式授权：「解冻 v1.0.0，启动 P1.1」。  
2. 先写 Phase Checklist / 设计短文（取消令牌、检查点、禁止点）。  
3. 再编码；红 Gate 不准合入。

---

## Appendix — Out of Sprint Mainline

| ID | 处理 |
|----|------|
| **P1.9** | Settings 注入 / skill catalog 耦合 → v1.1 后或穿插 refactor day；不挡 Exit Criteria |
| **HITL 实现** | 归 v1.2 / Phase 2；本计划仅 Design |
| **OIDC 登录 UI** | 可跟 P1.10；无 IdP 时用 feature flag 隐藏 |
| **Celery / K8s / Semantic** | 明确 Non-goals |

---

## Document control

| Item | Value |
|------|--------|
| Status | COMPLETE · planning only |
| Code changes | **NONE** |
| Git / Issues | **NONE** |
| Implementation authorized | **NO** |
| Baseline freeze | **v1.0.0 MAINTAINED** until explicit thaw |

**Next human decision:** 是否采纳「第一刀 = P1.1」，以及是否允许 Sprint 1 并行 P1.6。
