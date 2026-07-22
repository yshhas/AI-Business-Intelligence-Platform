# P1.1 Cooperative Cancel / Timeout — Design

**Status:** DESIGN ONLY · awaiting confirmation before coding  
**Sprint:** Phase 1 / Sprint 1  
**Baseline:** v1.0.0 (`ae8dc58`) · Feature Freeze **thawed** for Sprint 1 scope only  
**Parallel (out of this doc):** P1.6 Runtime profile — separate small change set after / beside this design  
**Spine (immutable):**

```text
Product Shell → Worker → Kernel → Skill → Policy → Data Plane → Trace / Artifacts
```

**Non-goals for this design:** P1.2–P1.5, P1.7–P1.10, HITL, Celery, hard-kill OS threads, incremental step streaming product.

---

## 1. 当前 cancel / timeout 流程分析

### 1.1 状态与字段（已有）

| 概念 | 位置 | 含义 |
|------|------|------|
| `status` | `analysis_tasks` | `pending` → `running` → `{succeeded,failed,cancelled,timed_out}` |
| `cancel_requested` | 同表 bool | Shell 请求取消；running 时先置位，由 Worker 协作收尾 |
| `timeout_seconds` | 任务行 / 默认 `RUN_TIMEOUT_SECONDS` | 壁钟预算 |
| `failure_class` | `cancelled` / `timeout` / … | 诚实失败分类 |
| Heartbeat | `last_heartbeat_at` | 仅供 stale reclaim，**不是**取消令牌 |

终态集合：`run_lifecycle.TERMINAL_STATUSES`。

### 1.2 Shell：发起取消

`task_service.cancel_task`：

```text
pending  → 立即 status=cancelled + cancel_requested=True + result_json 平台块
running  → 仅 cancel_requested=True（保持 status=running），return
terminal → 409
```

API 不直接杀线程；running 取消是**信号**，期望 Worker 协作。

### 1.3 Worker：认领与执行包装

`analysis_worker.process_task`：

1. 可选 `reclaim_stale_running`  
2. `pending + cancel_requested` → `_mark_cancelled`（before start）  
3. CAS `pending→running`（要求 `cancel_requested=False`）  
4. 再读一次：若已 `cancel_requested` → `_mark_cancelled`  
5. `_run_with_timeout(db, task, runtime, timeout_seconds)`  
6. 捕获 `_Cancelled` / `_TimedOut` / `AgentAnalysisError` / 其它 → 对应终态  
7. 成功返回后再次检查 `cancel_requested`，可能改为 cancelled（保留 best-effort `result_json`）

### 1.4 `_run_with_timeout`（核心）

```text
ThreadPoolExecutor(max_workers=1)
  submit(_work)   # 独立 Session：mock 或 run_agent_analysis
  loop:
    if monotonic >= deadline → raise _TimedOut
    fut.result(timeout=≤0.25s)
    on FuturesTimeout:
      reload task; if cancel_requested → raise _Cancelled
      maybe touch_heartbeat
```

文档字符串自称 *cooperative; not hard kill*，但实现要点：

- **主线程**用壁钟决定 timeout / 轮询 DB 决定 cancel。  
- **工作线程**内：仅在 `_work` **入口**检查一次 `cancel_requested`；之后整段 Skill **无检查点**。  
- `with ThreadPoolExecutor` 退出时默认 **`shutdown(wait=True)`**：主线程抛出 `_TimedOut`/`_Cancelled` 后，仍会**阻塞等待**工作线程跑完，再把异常抛给 `process_task`。

### 1.5 Skill / 落库时机

| Runtime | 执行 | Steps 落库 |
|---------|------|------------|
| `mock` | `mock_runtime` 逐步 `sleep(0.15)` + **每步 `flush`** | 线程内增量提交意图（随 Session commit） |
| `agent` | Facade `run_analysis` → 整图跑完 | **批末**一次写入全部 `AgentRunStep`（`agent_runtime.py`）；失败 `AgentAnalysisError` 时 `commit` 保留 partial steps |

Agent / LangGraph / Gate / Plane：**零** cancel 感知（`AnalysisContext` 无 cancel 字段）。

### 1.6 旁路：stale reclaim

`runtime_essentials.reclaim_stale_running`：心跳过旧的 `running` → `failed` + `runtime_reclaimed`。  
与 cancel/timeout **正交**；不中止线程，只修僵尸行。

### 1.7 已有测试

`smoke_m2_lifecycle.py`：pending cancel + mock + 短 `timeout_seconds` → `timed_out`。  
**不**覆盖：running 中 cancel、timeout 后是否仍写入 steps、Executor wait 行为、agent 路径协作点。

---

## 2. 现有问题复现路径

### 问题 A — 「协作」名不副实（Skill 内无检查点）

**路径：**

1. `ANALYSIS_RUNTIME=agent`，长 LLM / 慢 SQL。  
2. API `POST .../cancel` → `cancel_requested=True`，`status` 仍为 `running`。  
3. Worker 主循环最多 ~0.25s 发现标志并 `raise _Cancelled`。  
4. 但工作线程内 `run_analysis` **继续跑完**当前 LLM/Plane 调用。  
5. 因 `shutdown(wait=True)`，`_mark_cancelled` **推迟到 Skill 结束后**才执行。

**用户可见：** Cancel API 返回后，任务长时间仍为 `running`；SSE 无「正在收尾」语义。

### 问题 B — Timeout 非壁钟生效

**路径：**

1. `timeout_seconds=2`，agent 单次 LLM > 2s。  
2. 主线程到点 `raise _TimedOut`。  
3. Executor `__exit__` **wait** 至 LLM 返回。  
4. 然后才 `_mark_timed_out`。

**用户可见：** 实际耗时 ≫ `timeout_seconds`；`TIMEOUT_LIMITATIONS` 文案已暗示，但与「壁钟预算」产品语义不符。

### 问题 C — 终态后的 step / 副作用（孤儿写）

**路径（mock 更明显）：**

1. 短 timeout；mock 逐步 flush steps。  
2. 若将来改为 `wait=False` 或线程在终态标记后仍 commit：可能在 `status=timed_out/cancelled` **之后**继续 `INSERT agent_run_steps`。  
3. Agent 批末写入：主线程已标终态、线程稍后 `commit` steps → UI 出现「已 timed_out 但仍不断出齐完整 steps / 甚至 memory 写回」（agent 成功路径 memory 在 `run_agent_analysis` 末尾）。

**Stabilization 所述 orphan step writers** 即此类：**终态提交与执行线程落库无同一世代/门闩**。

### 问题 D — 双 Session 竞态

主线程 `db` 与 `_work` 的 `thread_db` 分离：

- 主线程 `_mark_*` commit 终态。  
- 工作线程随后 `commit` steps /（agent）memory。  
- 无「run generation / write fence」→ Trace 与 `status` 短暂或持久不一致。

### 问题 E — 成功与取消交叠

线程跑完全成功返回 + 期间已 `cancel_requested`：主线程成功分支会改为 cancelled（保留 result）——行为可接受，但与「超时放弃结果」策略需在设计中统一。

---

## 3. Cooperative cancel 设计

### 3.1 目标（Sprint 1 验收）

1. **Cancel / timeout 决定后，尽快进入终态**（秒级内，不等待完整 Skill 成功路径）。  
2. **Skill 在检查点停止**开新节点 / 新 LLM / 新 Plane 调用。  
3. **终态之后禁止**新的 `AgentRunStep` 持久化与成功路径副作用（如 memory remember）。  
4. **不**要求打断已发出的阻塞 HTTP/DB（诚实写进 limitations；可选后续加重试取消）。  
5. **不**改变 Spine；Worker 仍是唯一 Run 治理者；仍只经 Facade。

### 3.2 设计原则

| 原则 | 说明 |
|------|------|
| **信号与收尾分离** | Shell 只设 `cancel_requested`；Worker 拥有 `CancelToken` + 终态写入 |
| **检查点协作** | 可中断点抛 `RunCancelled` / 返回 aborted；非 OS kill |
| **单次终态** | CAS：仅 `running` → `cancelled|timed_out`；其后写路径 no-op |
| **世代门闩（run epoch）** | 每次 claim 分配 `run_epoch`；step 写入必须携带同一 epoch |
| **Executor 策略** | timeout/cancel 后 **`shutdown(wait=False, cancel_futures=True)`**（Py3.9+）+ **grace join**；主线程先标终态，再限时等待线程退出 |
| **In-flight 诚实** | limitations 保留「不保证立即中止 HTTP/SQL」；Trace `incomplete=true` |

### 3.3 组件草图

```text
┌──────────── Shell ────────────┐
│ cancel_task → cancel_requested │
└───────────────┬───────────────┘
                │
┌───────────────▼───────────────┐
│ Worker process_task           │
│  claim → RunControl.create()  │
│  _run_with_control(...)       │
│    thread: Facade(ctx+token)  │
│    main: poll cancel/deadline │
│  on signal:                   │
│    token.request_*()          │
│    CAS mark terminal          │
│    shutdown wait=False+grace  │
│    discard late success       │
└───────────────┬───────────────┘
                │
┌───────────────▼───────────────┐
│ Facade / Skill                │
│  checkpoint() between nodes   │
│  before LLM / execute_select  │
└───────────────────────────────┘
```

### 3.4 推荐新增类型（名可微调）

- `RunControl` / `CancelToken`（threading）：`cancel_event`, `timeout_event`, `epoch: int`, `is_aborted()`  
- 异常：`RunAborted(reason: cancelled|timeout)`（agent 包或 workers 共享薄模块，**避免** Agent→SQLAlchemy）  
- `AnalysisContext.cancel_check: Callable[[], None] | None` — 触发时抛 `RunAborted`

**依赖方向：** Worker 构造 token → 注入 Context → Skill/节点调用；Agent **不**读 DB 看 `cancel_requested`（由 Worker 轮询 DB 后 `token.request_cancel()`）。

---

## 4. Cancel token 生命周期

```text
[claim success]
    epoch = task.run_epoch  # 见 §8；若无列则用 started_at 哈希 / 内存 dict keyed by task_id
    token = CancelToken(epoch=epoch)

[main poll loop]
    if DB.cancel_requested → token.request_cancel()
    if deadline → token.request_timeout()
    if token.aborted → break loop → finalize_abort()

[worker thread]
    before/at checkpoints → token.raise_if_aborted()
    on RunAborted → flush nothing new; re-raise to _work

[finalize_abort]
    CAS status running → cancelled|timed_out (+ failure_class, limitations, incomplete)
    publish epoch as closed (DB flag or in-memory fence)
    executor.shutdown(wait=False, cancel_futures=True)
    join(thread, grace_seconds=N)  # N 可配置，如 2–5s；超时仅打日志
    ignore subsequent fut success result

[late thread wake]
    step writer / memory: see fence → skip persist
```

**API cancel 与 token：**

- Shell 置 `cancel_requested`（不变）。  
- Worker 主循环读 DB（已有）→ `token.request_cancel()`。  
- 不要求 Redis pub/sub（Sprint 1 保持简单）；0.25s 轮询足够。

**Timeout：**

- 仅主线程壁钟 → `token.request_timeout()`；**先** CAS 终态，**再**放弃等待完整 Skill。

---

## 5. Worker 检查点设计

### 5.1 主线程检查点（已有，需强化）

| 点 | 行为（目标） |
|----|----------------|
| claim 前 | pending+cancel → cancelled（保持） |
| claim CAS | cancel_requested 则失败（保持） |
| 进入执行前 | cancel → cancelled（保持） |
| poll 循环 | cancel/deadline → **set token + CAS 终态 + 非阻塞 shutdown**（改） |
| 成功返回后 | 若已终态 → **丢弃成功结果**，不覆盖 cancelled/timed_out（改强） |

### 5.2 工作线程检查点（新增）

| 点 | mock | agent (`data.bi`) | `data.profile` |
|----|------|-------------------|----------------|
| `_work` 入口 | ✓ 已有 DB 检查 → 改用 token | 同左 | 同左 |
| 每 mock step 前 | ✓ `raise_if_aborted` | — | — |
| LangGraph 节点边界 | — | ✓ `cancel_check` 在 pipeline 节点入口 | 确定性循环每步入口 |
| LLM 调用前 | — | ✓ | — |
| `execute_select` 前 | — | ✓（tool 包装或 ctx 注入） | ✓ 若有 SQL |
| Facade 返回后写 steps 前 | — | ✓ fence：终态则不写 / 或写 aborted 标记 | 同左 |
| memory remember 前 | — | ✓ 禁止 | — |

### 5.3 Executor 改造要点

```text
今日:  with ThreadPoolExecutor() as pool: ... raise → wait=True
目标:  pool = ThreadPoolExecutor(...)
       try: ... poll ...
       finally:
         if aborted: pool.shutdown(wait=False, cancel_futures=True)
         else: pool.shutdown(wait=True)
         # grace join 记录仍存活的线程（daemon=False 时进程退出仍可能挂；文档化）
```

**不做：** `ctypes` 杀线程、改用 multiprocessing（引入新框架/复杂度，禁止）。

---

## 6. Skill 如何响应取消

### 6.1 注入方式（保持 Facade）

```text
Worker._work
  → run_agent_analysis(..., cancel_check=token.raise_if_aborted)
  → AnalysisContext.cancel_check = ...
  → run_analysis(ctx)   # 仍唯一入口
```

Mock：`run_mock_analysis` 增加可选 `cancel_check` 参数（仅 Worker 调用）。

### 6.2 节点约定

- 每个节点 / mock step **开头**调用 `cancel_check()`（若存在）。  
- 捕获 `RunAborted`：节点标记 `status=aborted`（若仍允许写最后一条 step），图短路 END。  
- **禁止**在 abort 后调用 LLM / Plane。  
- Policy Gate **不**因 cancel 改变语义；未发出的 SQL 不执行即可。

### 6.3 与 Kernel 关系

- Kernel `run()` 可在调度 Skill 前后调用 `cancel_check`（薄）。  
- **不**把 cancel 做成 Policy；**不**经 Data Plane 传取消（Plane 无状态）。

### 6.4 无法协作的区间

- 已发出的 `httpx` LLM 请求、已在执行的 DuckDB/Postgres 查询：Sprint 1 **不**强制中断。  
- limitations 文案更新为更准确：「检查点后停止；进行中的 IO 可能跑完但不提交成功终态 / 不写 memory」。

---

## 7. Trace / Artifact 一致性保证

### 7.1 不变量

| ID | 不变量 |
|----|--------|
| T1 | 任一时刻最多一个非终态 Run 执行世代；终态 CAS 成功后不得改回 `running` |
| T2 | `status ∈ {cancelled,timed_out}` ⇒ `platform.run.failure_class` 匹配；`execution.summary.incomplete=true`（已有逻辑保留/强化） |
| T3 | 终态 commit **之后**，禁止新 `AgentRunStep` INSERT（同 task_id），除非带 `aborted` 收尾一步且受 fence 允许的一次性写 |
| T4 | 终态之后禁止 workspace memory `remember_*` |
| T5 | Artifacts materialize **仅**由 Worker `_mark_*` / 成功路径调用；工作线程禁止独立 materialize |
| T6 | 晚到的成功 `result_json` **不得覆盖** cancelled/timed_out 行 |

### 7.2 实现手段（选一为主，编码阶段定）

**推荐：Write fence（DB）**

- 列 `analysis_tasks.write_generation` 或复用 / 新增 `run_epoch INT`：claim 时 +1。  
- `persist_steps(task_id, epoch, steps)`：`UPDATE ... WHERE id=? AND status='running' AND run_epoch=?` 失败则丢弃。  
- 或：终态后 `status!=running` → step writer no-op。

**辅助：Token fence（内存）**

- `token.is_closed()` 在线程侧跳过 persist；进程内有效，需与 DB CAS 配合防双 Worker（现有单消费者假设下可接受）。

### 7.3 Partial Trace

- Abort 前已产生的 in-memory steps：允许 **一次** 尽力写入并全部标 `incomplete` / 最后一步 `aborted`。  
- 若 CAS 终态已成功且 fence 关闭 → **宁可少 step，不可晚写**（优先 T3）。

### 7.4 Artifacts

- `_mark_cancelled` / `_mark_timed_out` 继续 `_materialize_artifacts`（基于当时 `result_json`，可能几乎为空）。  
- 不要求 abort 时补全 charts/report。

---

## 8. 状态机变化（如有）

### 8.1 对外状态枚举

**不新增**业务状态值。仍为：

```text
pending → running → succeeded | failed | cancelled | timed_out
         ↘ cancelled (pending cancel)
```

`failed` + `runtime_reclaimed` 仍仅 reclaim 使用。

### 8.2 内部扩展（实现细节，可迁移）

| 字段 | 动作 | 必要性 |
|------|------|--------|
| `run_epoch` (INT) | claim 时递增 | **建议**（fence）；若想零迁移，可用「仅 status=running 才允许写 steps」作 MVP |
| 无新 status | — | — |

**推荐 Sprint 1：**  

- **MVP 可无 migration：** step/memory 写入前 `SELECT status`，非 `running` 则 skip。  
- **若测试暴露 TOCTOU：** 再加 `run_epoch` migration（授权范围内允许）。

### 8.3 语义微调（行为，非枚举）

| 场景 | v1.0 行为 | 目标行为 |
|------|-----------|----------|
| running + cancel | 等 Skill 完再 cancelled | 检查点停止 + 尽快 cancelled |
| timeout | 常 wait Skill 完再 timed_out | 到点 CAS timed_out，丢弃晚到 success |
| cancel + 已算完 result | 可带 full result 标 cancelled | **保持可接受**；timeout **不**升级为 succeeded |

---

## 9. 测试方案

### 9.1 保留

- 现有 `smoke_m2_lifecycle`（pending cancel + mock timeout）必须继续 PASS。  
- 全量 `smoke_release_gate`。

### 9.2 新增（建议 `smoke_p1_1_cooperative_cancel.py` 或扩展 m2）

| 用例 | 断言 |
|------|------|
| **C1** running cancel（mock 放慢） | API cancel 后，在 Skill 理论总时长前进入 `cancelled`；之后无新 steps（或仅 aborted 收尾） |
| **C2** wall-clock timeout | `timeout_seconds` 小；`finished_at - started_at` 上界合理（含 grace，但 ≪ 无协作时的满跑）；`failure_class=timeout` |
| **C3** timeout 后无 success 覆盖 | 不得出现最终 `succeeded` |
| **C4** fence | 终态后强制调用 persist_steps 模拟 → 0 行新增 |
| **C5** agent 检查点（可选 CI） | mock cancel_check 或短假 LLM；至少单元级 token 检查点 |
| **C6** pending cancel | 回归现有 |

### 9.3 单测（无 Redis 可测部分）

- `CancelToken` request/raise  
- `persist_steps` fence 逻辑（内存/DB）

### 9.4 P1.6（并行，非本设计正文）

- config hardening：demo/docs/`assert_boot` 与 `ANALYSIS_RUNTIME`；既有 `smoke_config_hardening` 扩展。  
- **编码阶段**另报；不阻塞本设计确认。

### 9.5 Frontend

- Sprint 1 **无前端改动要求**；完成时跑 `npm run lint && npm run build` 确认未破坏（或 CI 同款）。

### 9.6 Release Gate

- 将新 smoke 挂入 `smoke_release_gate.py`（或作为明确子步骤）。  
- Gate 红不准合入 Sprint 1 完成声明。

---

## 10. 风险清单

| ID | 风险 | 影响 | 缓解 |
|----|------|------|------|
| R1 | `shutdown(wait=False)` 后线程仍长时间占用 in-flight 槽位 | 容量虚假占满 | grace 后依赖 heartbeat stale reclaim；文档说明；可选 abort 时仍 touch 直至线程死 |
| R2 | 无法中断 httpx/DB | 取消「慢」 | 检查点 + 诚实 limitations；不假装硬杀 |
| R3 | 双 Session TOCTOU | 终态后仍 insert step | status/epoch fence；测试 C4 |
| R4 | LangGraph 节点漏加 check | 某路径仍跑满 | 清单覆盖 generate/validate/execute；code review 清单 |
| R5 | 改 Executor 行为导致 smoke 絮叨/flaky | CI 不稳 | 放宽时间断言；专用慢 mock |
| R6 | Agent 包引入 DB 依赖 | 破 Facade | **禁止**；只注入 callback |
| R7 | 范围滑到 HITL/增量 steps | Spine/范围失控 | 本设计 Non-goals；评审卡点 |
| R8 | `run_epoch` migration 与多 Worker 未来 | 过度设计 | MVP 先 status fence；必要再 migration |
| R9 | 取消后仍 materialize 空 artifacts | 噪音 | 可接受；与 v1.0 一致 |
| R10 | 与 reclaim 竞态 | 双重终态 | CAS WHERE status=running；reclaim 同条件 |

---

## 11. 建议实现切片（确认设计后编码顺序）

> 仍待你确认本设计后再动代码。

1. **Token + fence 辅助**（纯逻辑 / 单测）  
2. **Worker Executor + finalize_abort**（主路径行为）  
3. **Context.cancel_check + mock 检查点**（可测 C1/C2）  
4. **agent pipeline / profile 检查点**  
5. **steps/memory writer 守门**  
6. **limitations 文案 + docs**  
7. **smoke + release gate 挂钩**  
8. **并行：P1.6**（config/docs/hardening）

每步按你的要求报告：修改文件 · 原因 · 测试 · Spine 影响。

---

## 12. 设计确认清单（请你回复）

请确认或勾选修订：

- [ ] 接受 **不硬杀 IO**，以检查点 + fence 为 Sprint 1 Definition of Done  
- [ ] 接受 Executor **`wait=False` on abort** + grace join  
- [ ] MVP **优先 status fence**；`run_epoch` migration 仅在必要时  
- [ ] **不**改对外状态枚举  
- [ ] 设计批准后进入编码切片 1  

---

**Document status:** READY FOR REVIEW · **Code changes:** NONE · **Next:** 等待设计确认后编码
