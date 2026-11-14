# SQL Gate 单元测试 — 已知问题记录

> 2026-08-02 | 第一阶段单元测试 (test_sql_gate.py)
> 85 tests passed — 发现 3 个值得关注的代码行为，记录如下。
> 无一属于高危安全漏洞，均为已知局限。

---

## Issue 1: EXPLAIN 绕过 SELECT 类型检查

### 当前行为

```sql
EXPLAIN SELECT 1 FROM ds_test
```

`sqlparse` 将该语句解析为 DML=SELECT（而非独立的 EXPLAIN 类型），因此 Gate 在 DML 类型检查阶段放行。`_FORBIDDEN` regex 中未包含 "EXPLAIN"，该语句可通过全部 Gate 检查并成功执行。

### 是否属于安全风险

**低风险**。EXPLAIN 是只读操作，不会修改数据。但以下场景需要考虑：

- DuckDB 中 `EXPLAIN` 可能暴露查询计划中的敏感信息（如表结构）
- 如果未来有 `EXPLAIN ANALYZE` 等变体，可能触发实际执行

### 建议修复

**建议不修复**。理由：
- EXPLAIN 本质是只读操作，与 Gate 的"只读"原则一致
- 当前用户场景中，用户已经能看到表结构（Schema Linking 阶段），不构成额外信息泄露
- 修复成本（需扩展 sqlparse token 识别逻辑）与收益不成比例

### 优先级：P3（低优先级，可观察）

---

## Issue 2: CTE 别名被 _extract_table_names 提取，需加入 allowlist

### 当前行为

```sql
WITH recent AS (SELECT * FROM ds_test) SELECT * FROM recent
```

`_extract_table_names` 的 regex 会匹配 `FROM recent` 中的 `recent`，将其视为表名。因此 CTE 别名 `recent` 也必须在 allowlist 中，否则 Gate 拒绝。

**允许列表需包含**：`{"ds_test", "recent"}`

### 是否属于安全风险

**无安全风险**，但属于可用性问题。CTE 别名是 LLM 动态生成的临时名称，无法预知，导致：
- 无法提前将 CTE 别名加入 allowlist（除非在 Schema Linking 阶段就注册）
- 实践中限制了 CTE 的使用

### 建议修复

**中优先级修复**。建议方案（二选一）：

**方案 A（推荐）**：在 `_extract_table_names` 中跳过 CTE 定义中的别名
- 识别 `WITH xxx AS (` 模式，将 `xxx` 加入忽略列表
- 正则匹配后过滤掉这些 CTE 别名
- 改动量：约 10 行代码

**方案 B**：在 Gate 调用方动态扩展 allowlist
- 执行前解析 CTE 别名，动态加入 allowlist
- 改动量：约 5 行代码，但调用方需要感知 Gate 内部逻辑

### 优先级：P2（中优先级，建议在支持 CTE 之前修复）

---

## Issue 3: 字符串字面量中的关键词误触发 forbidden 检测

### 当前行为

```sql
SELECT 'DROP TABLE' AS msg FROM ds_test
```

`_FORBIDDEN` regex 是全局匹配，不区分 SQL 关键字和字符串字面量。语句中的 `DROP TABLE` 会触发 forbidden keyword 检测，导致 Gate 拒绝一个合法的只读查询。

### 是否属于安全风险

**无安全风险（仅误拦）**。但会导致：
- 合法查询被拒绝，用户困惑
- 如果用户数据中包含 forbidden 关键词（如产品名含 "DELETE"），无法查询

### 建议修复

**低优先级修复**。建议方案：

- 在 `_FORBIDDEN.search` 之前，先用 sqlparse 移除字符串字面量（替换为占位符）
- 对处理后的 SQL 做 forbidden 检查
- 改动量：约 15 行代码

**但需注意**：修复后，攻击者可能通过字符串拼接绕过检查（如 `SELECT * FROM ds_test WHERE '; DROP TABLE ds_test; --' = ''`），需配合多语句检查（已存在）保护。

### 优先级：P3（低优先级，实际业务场景触发概率极低）

---

## 汇总

| Issue | 风险等级 | 建议修复 | 优先级 |
|-------|---------|---------|--------|
| EXPLAIN 绕过 | 低 | 不修复 | P3 |
| CTE 别名需入 allowlist | 无（可用性） | 修复 | P2 |
| 字符串误触发 | 无（误拦） | 可观察 | P3 |

**测试覆盖状态**：以上 3 个问题在 `test_sql_gate.py` 中均有对应测试用例并已文档化。

---

## Issue 4: Gate 错误消息未被 classify_repair_error 正确分类

> 发现于 test_repair_classify.py (2026-08-02)

### 当前行为

`classify_repair_error` 使用关键词匹配（`"allowlist"`, `"forbidden"`, `"gate"`, `"policy"` 等）来分类错误。但 `sql_gate.py` 的部分错误消息不含这些关键词：

| Gate 错误消息 | 预期分类 | 实际分类 |
|---------------|---------|---------|
| `"Multiple statements are not allowed"` | `policy_other` | `unknown` |
| `"Only SELECT/WITH queries are allowed"` | `policy_other` | `unknown` |
| `"Could not resolve table name from SQL"` | `policy_other` | `unknown` |
| `"Empty SQL"` | `policy_other` | `unknown` |

### 是否属于安全风险

**无安全风险**。分类为 `unknown` 不会导致任何安全漏洞，只是影响修复策略的选择（如无法区分"需要调整 prompt"和"需要检查 allowlist"）。

### 建议修复

**低优先级**。方案：在 `classify_repair_error` 中增加 Gate 特定错误消息的匹配关键词，或在 Gate 层面直接附上分类标签。

### 优先级：P3（低优先级，不影响功能正确性）

---

## Issue 5: _LONG_TOKEN regex 无法匹配带中划线分隔的 token

> 发现于 test_guardrails.py (2026-08-02)

### 当前行为

`_LONG_TOKEN` regex 为 `\b(?:sk|pk|rk)[_-][A-Za-z0-9]{16,}\b`，要求前缀后紧跟 16+ 个连续字母数字字符。但 Stripe 等实际 API key 格式为 `sk-live-xxxxxxxxxxxx`，中间的 `-` 会中断字符类匹配，导致 token 不被 redact。

```
输入: "sk-live-1234567890abcdef"
实际: 不 redact（"live-" 中的 "-" 不在 [A-Za-z0-9] 中）
期望: 应被 redact
```

### 是否属于安全风险

**低风险（信息泄露）**。Stripe 格式的 secret key 不会被 redact，可能泄露到输出中。但：
- 实际生产环境中 API key 不应出现在分析数据中
- 这是输出 guardrail 的防御层，不是唯一的防线

### 建议修复

**中优先级**。方案：扩展 `_LONG_TOKEN` 的字符类，允许 `[A-Za-z0-9_-]` 或改为 `\S+` 匹配非空白字符。

```python
# 当前
_LONG_TOKEN = re.compile(r"\b(?:sk|pk|rk)[_-][A-Za-z0-9]{16,}\b")
# 建议
_LONG_TOKEN = re.compile(r"\b(?:sk|pk|rk)[_-][A-Za-z0-9_-]{16,}\b")
```

### 优先级：P2（中优先级，建议修复以增强防御）

---

## 附：Heuristic 回退模式的语义局限（Demo）

> 2026-11-14 | 无 LLM Key 的本地演示说明

### 背景

当未配置 `LLM_API_KEY` 且 `ALLOW_HEURISTIC_SQL=true` 时，`generate_sql` 与
`summarize` 会走确定性规则回退，而不是真实 LLM 调用。该模式用于在没有外部
API 的情况下验证任务生命周期、SQL Gate、Trace、Artifacts 与 UI。

### 具体表现

本地演示问题：

```text
各区域订单总金额是多少？按金额降序
```

heuristic 实际生成的 SQL 为：

```sql
SELECT "product" AS dim, SUM("amount") AS total
FROM "public"."demo_orders"
GROUP BY "product" ORDER BY total DESC
LIMIT 200
```

问题中的"区域"没有被识别，规则回退选择了 `product` 维度。这说明 heuristic
只做关键词/模板匹配，不能保证维度语义正确。

### 影响范围

- **不影响**：任务状态、队列、Worker、SQL Gate、只读执行、Trace、Artifacts、HITL、UI。
- **影响**：答案的语义正确性，以及 `llm_total_tokens` / 真实调用相关断言。
- **不能作为**：真实 LLM 问答质量的证据。

### 定位与使用建议

- 仅用于无 Key 的界面与链路演示；真实问答必须配置 `LLM_API_KEY`。
- 真实/生产环境应保持 `ALLOW_HEURISTIC_SQL=false`。
- 演示文档与截图必须标注运行模式，避免被误解为模型输出。

### 可选改进（本轮不修改核心业务逻辑）

1. 为 heuristic 增加维度词映射（如"区域 → region"）及对应单测；
2. 限制 heuristic 只处理明确支持的模板，无法匹配时直接返回 `skill_error`；
3. 若需要展示真实语义能力，使用真实 LLM 单独截图并标注。

### 优先级：P3（演示说明，不影响主链路正确性）
