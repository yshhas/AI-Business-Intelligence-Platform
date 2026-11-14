# 文档导航

本目录按"架构 / 设计 / 运维 / 测试"组织主文档，历史研发过程统一归档到 `archive/`，避免影响首次阅读。

> 初次访问建议先读根目录 [README.md](../README.md)，再按角色选择下面的入口。

## 按角色阅读

| 角色 | 建议阅读 |
|------|----------|
| HR / 初次了解 | [README.md](../README.md) → [FINAL_RELEASE.md](FINAL_RELEASE.md) |
| 技术面试官 | [PLATFORM_CHARTER.md](architecture/PLATFORM_CHARTER.md) → [PLATFORM_CONTRACTS.md](architecture/PLATFORM_CONTRACTS.md) → [DATA_PLANE.md](architecture/DATA_PLANE.md) → [HITL_SQL_APPROVAL_DESIGN.md](design/HITL_SQL_APPROVAL_DESIGN.md) |
| 想要本地运行 | [demo.md](demo.md) → [OPS_RUNBOOK.md](ops/OPS_RUNBOOK.md) → [OPS_CONFIG_MATRIX.md](ops/OPS_CONFIG_MATRIX.md) |
| 关注质量与安全 | [TESTING_KNOWN_ISSUES.md](testing/TESTING_KNOWN_ISSUES.md) → [SECRETS_AND_COOKIES.md](ops/SECRETS_AND_COOKIES.md) → [API_ERROR_CODES.md](ops/API_ERROR_CODES.md) |

## 架构（architecture）

| 文档 | 内容 |
|------|------|
| [PLATFORM_CHARTER.md](architecture/PLATFORM_CHARTER.md) | 平台定位、边界与不做清单 |
| [PLATFORM_CONTRACTS.md](architecture/PLATFORM_CONTRACTS.md) | Kernel / Skill / Run / Artifact / Tool / Policy 合同 |
| [DIRECTORY_STRUCTURE.md](architecture/DIRECTORY_STRUCTURE.md) | 仓库目录与命名约定 |
| [DATA_PLANE.md](architecture/DATA_PLANE.md) | file / postgres_ro / mysql_ro 数据面 |
| [DUCKDB_TOPOLOGY.md](architecture/DUCKDB_TOPOLOGY.md) | DuckDB 文件与生命周期 |
| [SKILL_DATA_PROFILE_CHARTER.md](architecture/SKILL_DATA_PROFILE_CHARTER.md) | 第二个 Data Skill 的合同证明 |

## 核心设计（design）

| 文档 | 内容 |
|------|------|
| [HITL_SQL_APPROVAL_DESIGN.md](design/HITL_SQL_APPROVAL_DESIGN.md) | SQL 人工审批：暂停、审批、恢复 |
| [WORKSPACE_MEMORY.md](design/WORKSPACE_MEMORY.md) | Schema Linking 记忆与 TTL |
| [ADR_TOKEN_STORAGE.md](design/ADR_TOKEN_STORAGE.md) | Token 存储决策 |
| [PROMPT_CHANGE_GATE.md](design/PROMPT_CHANGE_GATE.md) | Prompt 变更门禁 |
| [MCP.md](design/MCP.md) | 只读 MCP 工具旁路 |
| [OIDC.md](design/OIDC.md) | 可选 OIDC 登录 |

## 运维与安全（ops）

| 文档 | 内容 |
|------|------|
| [OPS_RUNBOOK.md](ops/OPS_RUNBOOK.md) | 启动、探针、排障、Release Gate |
| [OPS_CONFIG_MATRIX.md](ops/OPS_CONFIG_MATRIX.md) | 环境变量矩阵 |
| [OBSERVABILITY.md](ops/OBSERVABILITY.md) | 日志与指标 |
| [SECRETS_AND_COOKIES.md](ops/SECRETS_AND_COOKIES.md) | 密钥与 Token 管理 |
| [API_ERROR_CODES.md](ops/API_ERROR_CODES.md) | HTTP 错误码与 failure_class |

## 测试与发布

| 文档 | 内容 |
|------|------|
| [TESTING_KNOWN_ISSUES.md](testing/TESTING_KNOWN_ISSUES.md) | SQL Gate 已知局限与取舍 |
| [FINAL_RELEASE.md](FINAL_RELEASE.md) | v1.0 发布说明 |
| [demo.md](demo.md) | 端到端演示脚本 |

## 历史归档（archive）

归档保留真实研发过程，仅作审计与面试追溯，**不代表当前实现状态**；冲突时以上述主文档与根 README 为准。

| 目录 | 内容 |
|------|------|
| [archive/phase/](archive/phase/) | 阶段 Checklist / Acceptance / Retrospective |
| [archive/sprint/](archive/sprint/) | Sprint 2–4 设计、实现与审计 |
| [archive/era/](archive/era/) | Era 1–3 阶段总结与价值排序 |
| [archive/hitl/](archive/hitl/) | HITL 实现计划与评审 |
| [archive/roadmap/](archive/roadmap/) | 历史路线图与改进计划（含旧版 project_upgrade_plan） |
| [archive/reviews/](archive/reviews/) | 技术评审、稳定化审查、最终审计 |
| [archive/p1/](archive/p1/) | 取消机制设计文档（P1.1） |
| [archive/interview/](archive/interview/) | 简历亮点与面试准备材料 |
