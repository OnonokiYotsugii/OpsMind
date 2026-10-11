# ADR 0006：LangGraph 与 MySQL 持久检查点

状态：采用，2026-10-10。

## 决策

将手写 Agent Loop 替换为 StateGraph，节点为 sync、model、tools、approval、finalize。工具选择仍由现有 ToolClient 决定，模型供应商不与图框架绑定。

增加 langgraph 依赖，uv.lock 锁定本次安装的 langgraph 1.2.14、langgraph-checkpoint 4.2.0。新增 MySQLSaver 适配本项目的单图、顺序执行场景，避免引入第二种业务数据库。

graph_checkpoint 保存完整序列化快照、元数据、父检查点和 pending writes。使用框架默认 typed serializer，未启用 pickle fallback；序列化二进制以 Base64 放入 MySQL JSON。按 task/index 保存结果，保留普通写入首值、允许框架特殊通道更新。支持 pending writes 先于完整 checkpoint 到达，此时存占位记录，查询不会把占位当作可恢复快照。

使用 durability=sync。框架可能并行安排部分结果保存，同一次运行的数据库访问与检查点 IO 使用同一进程锁串行化；不同运行可独立推进。MySQL 运行行锁和 420 秒租约负责跨请求排他，ContextVar 传递执行令牌，状态/检查点写入前核对拥有者。单次图调用限时 330 秒，模型及工具还有原有最大 300 秒处理预算。

## 业务一致性

MySQL agent_run 是消息、预算、待审批参数、执行凭据和结果的权威来源。GraphState 只保存推进节点所需的状态。图检查点与业务提交分开，因此明确处理业务提交成功而检查点失败的窗口。

- 普通节点通过 effect_id 与结果同事务记录，重放不重复应用。
- 审批节点先 interrupt，再执行已有审批服务；写入和执行凭据仍原子提交。
- 审批重放发现凭据就跳过写入，旧 action_id 不可确认新动作。
- 恢复接口不授予权限；每次入口、动作和写入都继续验证员工与参数。

P4 留下的待确认运行可以在首次确认时进入图，保留原动作身份。P5 运行标记 graph_enabled：执行中不因停机耗尽墙钟有效期，但继续保留步骤和处理预算；待审批的绝对有效期不变。

## 取舍

全量快照简化恢复但存储增长较快，未提供历史删除/时间旅行/分支接口。协议适配仅覆盖本项目使用方式，不宣称兼容全部 LangGraph 子图或分布式运行能力。

模型响应保存之前的宕机可能导致再次请求模型，并继续消耗步骤。数据库工单的防重保证来自业务凭据，不能推广为所有外部副作用的 exactly-once 保证。强制终止后的运行锁最长等待 420 秒。

## 验证

已有 168 项回归通过；新增 11 项验证 MySQL 序列化、pending write 顺序、暂停和拒绝、已执行节点重放、提交后故障、旧确认隔离、锁接管与失效执行者、过期审批、旧运行适配、恢复接口，以及独立 Python 进程恢复和并发确认。

## 参考

- [LangGraph Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [LangGraph Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- 适配实现同时核对本机已锁定版本 BaseCheckpointSaver、CheckpointTuple、InMemorySaver 的接口与写入规则。
