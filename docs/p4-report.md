# P4 阶段报告

## Completed

完成 Markdown/TXT 导入、短片段切分、CPU 多语言 Embedding、Chroma 持久化检索、KnowledgeDocument 登记表、search_knowledge 只读工具与独立检索 API。回答附来源编号、标题、版本和行号；未知或缺失引用返回说明。

同版本重复导入不新增片段，内容变更拒绝；失败导入不可见且可重试，支持显式 rebuild。示例资料标记为虚构演示。

## Files Changed

新增 src/opsmind/rag/、api/knowledge.py、scripts/knowledge.py、alembic/versions/0003_knowledge_document.py、knowledge/ 两份文档、P4 测试、教程和 ADR 0005。修改 Agent Runtime/Store/Prompt、工具注册、配置、环境示例、依赖和 README。

## Architecture

MySQL 管理来源、版本和可见状态；Chroma 保存片段与向量；FastEmbed 在本地生成向量；DeepSeek 根据业务与知识结果生成回答。

检索在数据库事务外执行。引用编号由程序核对，写操作仍沿用 P3 的人工确认与原子执行凭据。

## Verification

- pytest --mysql --embedding -q：168 项通过，较 P3 增加 26 项。
- 覆盖真实 Chroma 持久索引、真实 MySQL、失败恢复、重复导入、版本冲突、索引重建、无关问题、来源过滤、参数与引用校验、Agent 检索接入及预算。
- 真实本地模型命中 DEMO-24V E102 供电电压异常，distance=0.1392；草莓蛋糕问题没有结果。
- MySQL 开发库与测试库迁移到 0003，alembic check 无差异。
- 开发库导入 2 份文档、9 个片段；保留业务工单。

## 真实 DeepSeek 联调（2026-09-16）

首次运行 9c027ee654024ce8bc573d6bbf195536 因多工具响应安全失败，工具执行 0 次。一次仅检查响应结构的诊断发现模型同时选择三个工具；增加有步骤预算的纠正流程，并测试连续违规不会执行工具或无限循环。

成功运行 e762b6b2ae58485d82137b20f3946d39：completed，5 个模型步骤、4 次工具调用，处理时间 11373 ms。顺序为设备 → 维修记录 → 工单历史 → 知识检索 → 总结。引用 KB-155b8d5a36cb4a1ead33480c6cd27640-1 有效。工单数量 3 → 3，无待确认写操作。

本阶段真实聊天调用共 7 次：首次失败 1、诊断 1、成功运行 5；均未启用 HTTP 自动重试。成功运行没有触发协议纠正，纠正流程由自动测试验证。

## Problems

模型把工单和维修记录描述为两次维修，可能实际是同一次事件。已补充防止重复计数的提示，未为该提示再次消耗真实模型调用；不能宣称语义问题已完全解决。

只验证小规模演示资料，无正式检索评测指标。无 PDF/OCR、重排、完整登录、租户隔离或自动版本生效规则。引用检查不验证事实蕴含；超时不强行终止只读本地推理线程。导入建议串行运行。

测试有 3 条提示：已有 Starlette/httpx 与 AnyIO 弃用提示，以及 FastEmbed mean pooling 说明。未隐藏提示。

## Next Step

P4 在此暂停，用户可按 p4-guide.md 在 PyCharm 和 Swagger 自测。下一阶段 P5 需先制定 LangGraph 重构计划并确认；本次未实现 P5。
