# Interview Guide — Enterprise Data Agent Platform v1.0

配合阅读：[`FINAL_RELEASE.md`](FINAL_RELEASE.md) · [`PLATFORM_CHARTER.md`](PLATFORM_CHARTER.md) · [`project_upgrade_plan.md`](../project_upgrade_plan.md)

---

## 1. 面试官可能问什么（Q → 答法要点）

### 产品与定位

**Q: 这和做一个「ChatBI」有什么区别？**  
A: ChatBI 是 Skill；平台是 Shell→Worker→Kernel→Policy→Plane→Trace。面试讲「合同与治理」，不是「会生成 SQL」。

**Q: 为什么说是企业级？**  
A: 企业级首先是边界、审计、权限、失败分类、质量门禁与运维可观测；不是技术名词堆叠。

**Q: 为什么不做 RAG？**  
A: RAG 会把产品改成「文档问答」。本项目答案路径是受控 SQL 分析；向量库会稀释叙事并引入另一套正确性模型。

### 架构决策

**Q: 为什么 Worker 不能直接调 LangGraph？**  
A: 必须经 Facade/`kernel.run`，才能统一 Lifecycle、Trace 投影与 Guardrails，防止绕过 Policy。

**Q: 为什么 Gate 要做三次？**  
A: Skill 节点防坏 SQL；Tool 层强制；Plane 防 Shell 旁路。纵深防御；已知有性能成本，Stabilization 选择保留。

**Q: 为什么第二 Skill 选 profile 而不是第二个 LLM Agent？**  
A: 要证明的是 **合同可复用**，不是再堆一个聊天智能体。`data.profile` 确定性、强依赖 Gate，扩展叙事更干净。

**Q: 元数据库和 RO DSN 为什么分开？**  
A: 平台状态（用户/任务）与企业只读分析库安全域分离；避免用业务库账号跑平台迁移。

### 工程与质量

**Q: 没有 LLM Key 怎么测？**  
A: Eval core 强制关闭 heuristic 依赖；Gate/linking/profile 可确定性跑；llm suite 可选跳过。

**Q: 超时后任务如何诚实？**  
A: Worker wall-clock → `timed_out` + `failure_class`；Trace 保留已有步骤。已知债：线程取消非协作式（面试可主动说）。

**Q: 如何防止 Prompt 越改越差？**  
A: `PROMPT_CHANGE_GATE` + Eval 基线回归进 Release Gate。

---

## 2. 关键设计决策：为什么这样做

| Decision | Why | Alternative rejected |
|----------|-----|----------------------|
| 固定 Skill 图 | 可测、可审计、路径封闭 | ReAct 自由环 |
| sqlparse Gate | 确定性、无模型参与策略 | 仅靠 LLM「自觉」 |
| Redis List + 线程 Worker | 匹配当前负载；复杂度低 | 无证据上 Celery |
| Facade 兼容 `result_json` | 前端/Trace 平滑演进 | 大爆炸换 API |
| ACL 投影进 allowlist | 权限与 SQL 同一真相 | 只做 UI 隐藏 |
| OIDC/MCP 做 MVP | 证明可接企业生态 | 一次做完 IAM/MCP Server |
| Feature Freeze v1.0 | 交付叙事完整 | 无限 Wave 堆功能 |

---

## 3. 与 LangChain / RAG / 多 Agent 的取舍

| Approach | 适合什么 | 本项目为何不作为主路径 |
|----------|----------|------------------------|
| **LangChain 重写主路径** | 快速拼装工具链 | 双栈无收益；治理边界易糊；本仓已有 Kernel 合同 |
| **RAG / Vector DB** | 非结构化知识问答 | 改变产品定义；与 Text-to-SQL 正确性模型冲突 |
| **Multi-Agent** | 多角色协作编排 | 在单 Skill 未证明前是叙事空转；调试/审计成本高 |
| **LangGraph（本项目用法）** | **固定**状态机流水线 | 用作 `data.bi` 实现细节，**不是**平台本身 |
| **自由 Tool Calling** | 探索型助手 | 与 Policy allowlist / 企业最小权限冲突 |

**一句话对比：**  
别人卖「更聪明的对话」；本项目卖「可治理的数据分析 Run」。

---

## 4. 技术深度（面试官听「你懂多少」）

可主动下探的层次（由浅到深）：

1. **合同层：** RunRequest/RunResult · Skill Lifecycle · failure_class 枚举  
2. **执行层：** LangGraph 节点 · Schema Linking v2 · repair_class  
3. **安全层：** Gate AST/关键字黑名单 · allowlist 表抽取 · ACL 交集  
4. **运行层：** CAS claim pending→running · capacity · budget · idempotency SET NX  
5. **证明层：** Eval runner 模式（sql_inject / pipeline）· 基线回归  
6. **扩展层：** 第二 Skill 注册 · Plane source_type 分支 · MCP 只读旁路  

说出 **已知限制** 比假装完美更像资深：  
Refresh 未吊销 · timeout 非协作取消 · `result_json` 膨胀 · Memory 无 TTL · Gate 多次解析成本。

---

## 5. 扩展方向（Freeze 下只谈规划）

| Direction | 条件 |
|-----------|------|
| Wave 4 单云 IaC | 明确云厂商与合规要求 |
| Refresh revoke / Cookie 会话 | 真实用户规模 |
| 协作式取消与步骤增量落库 | Metrics 证明需要 |
| 更多 Data Skill | 先写 Charter + Eval，禁止旁路 Kernel |
| Celery | 队列/延迟证据，而非「看起来专业」 |

**红线仍在：** 不把平台改成 RAG 聊天或 Multi-Agent 操作系统。

---

## 6. 30 秒 / 2 分钟口述稿

**30 秒**  
我做的是企业数据 Agent 平台：用 Kernel 调度 Skill，用 SQL Policy Gate 卡住只读分析，用 Worker 把每次提问做成可超时、可取消、可分类失败的 Run；并且用第二个 Skill 证明扩展走同一合同，而不是再做一个 Demo。

**2 分钟**  
（加上）三重 Gate、元数据库与 RO 平面分离、ACL 投影、Eval Release Gate、Wave 3 的 Memory/OIDC/MCP 都是 MVP、v1.0 Feature Freeze，Wave 4 只谈部署不谈功能膨胀。

---

## 7. 反问面试官（加分）

- 贵司数据 Agent 的「正确答案」是 SQL 结果、文档摘要，还是两者混合？治理边界在哪？  
- 现有权限模型能否投影到查询 allowlist？  
- 质量回归是否已有 Eval/金标，还是只靠人工点检？
