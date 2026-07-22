# P1.1 Implementation Report — Cooperative Cancel / Timeout (+ P1.6)

**Date:** 2026-07-22  
**Sprint:** Phase 1 / Sprint 1  
**Baseline:** thawed from v1.0.0 Feature Freeze  
**Design:** [`P1_1_CANCEL_DESIGN.md`](P1_1_CANCEL_DESIGN.md)  
**Scope:** P1.1 Cooperative cancel/timeout · P1.6 Runtime profile hardening  
**Git:** no push · no release · history not rewritten

---

## 1. Summary

Sprint 1 目标达成：**Run 生命周期更可信**（壁钟 timeout / running cancel 尽快终态 + write 防孤儿写），并并行完成 **production/staging 拒绝 `ANALYSIS_RUNTIME=mock`**。

Spine **未推翻**：

```text
Product Shell → Worker → Kernel → Skill → Policy → Data Plane → Trace / Artifacts
```

---

## 2. What changed

### P1.1 Cooperative cancel / timeout

| 区域 | 改动 |
|------|------|
| Token | `backend/app/workers/run_control.py` — `CancelToken`（cancel/timeout/close fence） |
| Abort 类型 | `agent/run_control.py` — `RunAborted` + `checkpoint(ctx)` |
| Fence | `backend/app/workers/write_fence.py` — 仅 `status==running` 且 token 未 close 可写 |
| Worker | `analysis_worker.py` — abort 时 `shutdown(wait=False)`、短 grace、丢弃晚到 success；注入 token |
| Mock | `mock_runtime.py` — 每步 checkpoint + write |
| Agent 适配 | `agent_runtime.py` — `cancel_check` / token；steps & memory 写前门闩 |
| Context / Request | `AnalysisContext.cancel_check`、`RunRequest.cancel_check` |
| Nodes | `pipeline.py` 各节点入口 `checkpoint(ctx)` |
| Skills | `data.bi` / `data.profile` — execute 前 check；`RunAborted` 上抛给 Worker |
| Lifecycle 文案 | `run_lifecycle.py` limitations 对齐检查点语义 |
| 测试 | `smoke_p1_1_cooperative_cancel.py`；挂入 `smoke_release_gate.py`；`smoke_m2` 兼容 `**kwargs` |

### P1.6 Runtime profile

| 区域 | 改动 |
|------|------|
| Boot | `assert_boot_runtime()` — 非法 runtime 拒绝；**production/staging 拒绝 mock** |
| API / Worker | `main.py`、`analysis_worker.run_forever` 调用断言 |
| Docs / env | `.env.example`、`README.md`、`OPS_CONFIG_MATRIX.md` |
| Smoke | `smoke_config_hardening.py` 扩展 |

**未做：** `run_epoch` migration（MVP 用 status fence 足够）、硬杀 IO、HITL、P1.2–P1.5/P1.10。

---

## 3. Behavior deltas (v1.0 → Sprint 1)

| 场景 | v1.0 | 现在 |
|------|------|------|
| Wall-clock timeout | 常 `wait=True` 等 Skill 完再 `timed_out` | 到点设 token、尽快 `timed_out`，不等满跑 |
| Running cancel | 轮询后仍可能等 Skill 完 | token + 非阻塞 shutdown；检查点停止新工作 |
| Steps after abort | 可能晚写 | fence：终态/closed 后不 INSERT |
| Memory after abort | 可能 remember | fence 跳过 |
| Late success | 可能覆盖 | 终态后丢弃 success 写 |
| prod + mock | 可启动 | **拒绝启动** |

---

## 4. Test results

| Gate | Result |
|------|--------|
| `smoke_config_hardening` | **PASS**（含 P1.6） |
| `smoke_m2_lifecycle` | **PASS** |
| `smoke_p1_1_cooperative_cancel` | **PASS**（timeout ~1.4s vs 4s sleep；fence steps=0；running cancel） |
| `smoke_release_gate`（含 Eval core/quality/profile） | **PASS** |
| Frontend `npm run lint` + `npm run build` | **PASS**（无前端功能改动） |

---

## 5. Spine impact

| Layer | Impact |
|-------|--------|
| Shell | 仅 boot runtime 校验；cancel API 语义不变 |
| Worker | **主改** — 治理仍在此层 |
| Kernel | 透传 `cancel_check`；不改注册模型 |
| Skill | 检查点；不直连 DB |
| Policy | **不变** |
| Data Plane | **不变** |
| Trace | 终态诚实 + incomplete limitations；防孤儿 step |

---

## 6. Risks remaining

| Risk | Notes |
|------|-------|
| 不可中断的长 `sleep`/HTTP/SQL | 线程可能仍跑完；已 fence 写入；日志 warning |
| 容量槽位 | abort 后线程仍可能短暂占 in-flight，依赖 heartbeat reclaim |
| LangGraph 节点漏检 | 已覆盖主节点；新节点需加 `checkpoint` |
| 默认 `analysis_runtime=mock`（代码） | 本地骨架保留；demo/prod 文档与 boot 强制 agent |

---

## 7. Files touched (inventory)

**New:**  
`agent/run_control.py` · `backend/app/workers/run_control.py` · `backend/app/workers/write_fence.py` · `backend/scripts/smoke_p1_1_cooperative_cancel.py` · `docs/P1_1_IMPLEMENTATION_REPORT.md`

**Modified (core):**  
`analysis_worker.py` · `mock_runtime.py` · `agent_runtime.py` · `run_lifecycle.py` · `config.py` · `main.py` · `agent/state.py` · `agent/kernel/types.py` · `agent/runtime.py` · `agent/nodes/pipeline.py` · `agent/skills/data_bi/skill.py` · `agent/skills/data_profile/skill.py` · `smoke_release_gate.py` · `smoke_m2_lifecycle.py` · `smoke_config_hardening.py` · `.env.example` · `README.md` · `docs/OPS_CONFIG_MATRIX.md`

---

## 8. Next (not in this sprint)

- Commit when you authorize（Conventional: `fix(runtime): cooperative cancel/timeout + harden ANALYSIS_RUNTIME`）  
- Sprint 2: P1.2 Refresh revoke · P1.5 list_tasks · P1.3 Memory TTL  

---

**Sprint 1 status:** COMPLETE · **Release Gate:** PASS · **Push/Release:** NOT DONE
