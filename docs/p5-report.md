# P5 阶段报告

## Completed

已用 LangGraph StateGraph 替换手写循环，包含状态、模型/工具/审批/结果节点与条件分支。通过 interrupt/Command 实现持久人工审批，新增 MySQL 检查点和运行恢复接口。

保留原有业务权限、审批动作绑定、预算、RAG 引用与执行凭据语义。新增节点应用防重、运行租约与执行令牌检查，支持旧待确认运行进入新图。

## Files Changed

新增 agent/graph_state.py、graph.py、nodes.py、checkpointer.py、checkpoint_models.py、execution.py，迁移 0004_graph_checkpoint.py，两组 P5 集成测试、教程和 ADR 0006。

修改 runtime.py、store.py、state.py、models.py、api/agent.py、Alembic 模型登记、依赖锁文件及架构/数据库/README 文档。业务工单服务和知识索引不重写。

## Architecture

HTTP → AgentRuntime → LangGraph 节点与条件分支 → 原有 ToolClient / KnowledgeService / AgentStore。

GraphCheckpoint 保存执行位置与部分节点结果；AgentRun 保存业务权威状态。确认后实际工单与执行凭据仍在同一事务。检查点重放通过凭据和 effect_id 避免重复业务效果。

## Verification

2026-10-10：

- `ruff check .`、`ruff format --check .` 通过。
- `python -X utf8 -m pytest --mysql --embedding -q --tb=short`：179 项通过，较 P4 增加 11 项。
- 使用真实 MySQL 和真实本地向量模型；聊天响应受控，不付费调用模型。
- 新进程从已提交 MySQL 检查点继续审批成功，只创建一张测试工单。
- 两个独立运行实例并发确认：只写一次、只保留一条执行凭据，竞争请求可返回 run_busy。
- 注入工单提交后异常再恢复：工单数只增加一次。
- 注入工具应用后异常再恢复：工具计数与结果不重复。
- 验证过期、拒绝、旧确认不能批准新动作、执行令牌失效、恢复接口不能代替审批。
- 开发库和独立测试库迁移到 0004，`alembic check` 无差异。测试清理仅针对自身唯一编号的测试库记录。

## Problems

手动 Swagger 测试与真实 DeepSeek 联调按用户要求留到项目后续统一做，本轮未声称完成。已有阶段的真实模型证据不等于本轮真实模型验收。

本地演示身份仍不是真实认证。检查点未做保留期清理、跨图版本迁移、通用子图适配或分布式队列。强制退出可能需要等待最长 420 秒租约到期。模型调用在保存前宕机可重试，不承诺所有外部操作 exactly-once。RAG 回答正确性边界沿用 P4。

两条依赖提示保留：AnyIO 弃用提示和 FastEmbed 池化说明。新增传递依赖 httpx2 后，原 TestClient 的 httpx 提示不再出现。

实现中遇到检查点后台保存与单连接测试并发、pending writes 先于完整快照两类问题，均已修复并纳入真实数据库测试。

## Next Step

P5 在此暂停。后续 P6 为 Evaluation 与 Observability：先提出评测集、指标及执行记录方案，确认后实施。P4/P5 的手动自测合并到最后验收清单。
