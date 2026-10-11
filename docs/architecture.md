# 架构设计

## P7 当前实现

已实现配置、日志、FastAPI 工厂、业务服务、输入/输出模型、SQLAlchemy 数据访问与 MySQL 迁移。Settings 实例化时读取环境，导入模块无数据库连接副作用。保留本机演示限制，新增 P2 单次模型分析接口；已接入 RAG，并用 LangGraph 节点与 MySQL 检查点替换手写循环。

## 逐步演进的分层

```text
HTTP API ────────────────→ 业务服务 → SQLAlchemy / MySQL
   │                         ↑
   └→ Agent Runtime → 工具注册与执行
          │                  │
          └→ LLM Client      └→ RAG 检索 → 向量存储
```

- `api/`：HTTP 参数校验、状态码、依赖注入；不包含 Prompt 或 SQL。
- `schemas/`：请求与响应数据结构，不直接暴露 ORM 对象。
- `services/`：设备查询、工单状态约束、事务边界；不依赖 Agent 或 FastAPI。
- `db/`：ORM 模型、Session 生命周期和数据库访问。初期无需为每张表创建通用 Repository 抽象。
- `llm/`：隔离供应商接口、超时、重试和结构化输出校验。
- `tools/`：声明参数和风险级别，校验参数和权限，调用业务服务，返回受控结果。
- `agent/`：管理消息、步骤预算和工具选择。模型决定需要什么信息，程序控制可执行范围。
- `rag/`：文档导入、切分、检索及来源信息，P4 已实现。
- `core/`：配置与日志。基础设施随所属模块组织，不提前引入空的通用框架。

只在对应阶段创建模块，禁止提前建立大量空目录。

## 写操作边界

P3 开放 create_ticket / update_ticket 时就必须具备基础人工审批，不能等 P5 才保护写入。模型提出动作后，程序保存待批准的工具名和参数，展示给用户；审批与具体动作绑定，执行前再次校验权限及参数，处理重复确认。模型不能生成自己的批准凭据。

P5 把已有审批语义迁移到 LangGraph 的状态和检查点。P1 的手动业务接口与 Agent 审批机制分开。P1 使用服务端配置的固定演示员工，创建人不从请求读取；这不是登录认证，仅用于本机。production 模式拒绝启动。参见 ADR 0002。

## 后续可靠性边界

数据库事务由业务服务控制。网络重试限于可安全重试的操作，创建工单需要幂等保护；模型调用不能无限重试。Agent 设置最大步骤、工具白名单与结果长度限制。敏感数据按需读取，禁止任意 SQL 或 Shell 工具。

当前使用普通事件日志；请求 ID、Agent run ID、工具耗时在对应调用链落地时增加，P6 汇总为 Trace 和评估指标。

## P2 模型分析路径

POST /api/v1/analyses → AnalysisRequest → analyze_description → JSONClient →
Chat Completions HTTP → 协议解析 → FaultAnalysis → AnalysisResponse。

这条路径不经过业务数据库。配置与供应商参数位于 llm 层；Prompt 单独管理。
DeepSeek 使用 deepseek-v4-pro 和 JSON Output，再以 Pydantic 校验字段。
模型输出是初步分析，不是已验证诊断，needs_human_review 也不是执行授权。

当前自动测试包含真实 MySQL 回归和模拟模型 HTTP；真实模型连接状态见 P2 报告。

## P3 工具循环与确认

api/agent.py → AgentRuntime → AgentStore / ToolClient。
ToolClient 调用模型，AgentStore 在短事务中执行只读工具或保存待确认动作。
确认接口核对动作 ID，锁定运行行，将工单写入和执行凭据原子提交，然后继续模型循环。

主路径不硬编码查询顺序；工具执行只能来自白名单。
消息不包含密钥，但会持久化用户任务和工具摘要，需按业务数据对待。
具体限制与测试证据见 P3 操作说明和阶段报告。


## P5 图执行与恢复

Runtime 作为创建、确认、恢复入口；graph.py 连接 sync/model/tools/approval/finalize 节点。
MySQLSaver 保存图检查点与 pending writes，AgentStore 保持业务消息、预算和审批凭据的权威性。
节点可能重放，effect_id 和事务凭据防止重复应用。420 秒运行租约与拥有者令牌防止并发及失效执行者写入。
详见 ADR 0006 和 p5-guide.md。后续 Evaluation 与 Observability 尚未实现。

## P6 评测和 Trace

AgentRun 的事件 JSON 增加 trace_version、模型起止、工具耗时与检索来源，白名单投影为 Trace API，不新增表。evaluation 模块在本机测试库的回滚事务内运行固定案例，分别支持受控聊天响应与真实模型；报告保留数据集哈希和各项分母。说明见 [P6 教程](p6-guide.md)。

## P7 演示入口与容器

FastAPI 同源提供静态 HTML/CSS/JavaScript，页面不持有 API Key，不实现业务写权限。Compose 内 db 就绪后 init 迁移并种子导入，随后 app 以受限账号、非 root 用户启动；本机只发布回环端口。数据库、模型缓存、向量索引均持久化。Docker 实跑尚待安装环境后验证。
