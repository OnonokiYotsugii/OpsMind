# P3：Tool Calling、Agent Loop 与人工确认

## 当前能力

P2 是“输入描述 → 模型分析”。P3 是：
用户任务 → 模型选择工具 → 程序执行查询 → Tool Result 回到模型 →
模型再次选择工具或给出答案。

模型可以自主选择查询顺序，程序限定白名单、参数、权限和预算。
当前没有 RAG，不能检索维修手册；没有 LangGraph 或多 Agent。

## 接口

| 接口 | 用途 |
| --- | --- |
| POST /api/v1/agent/runs | 创建并推进一次运行，直到完成、失败或等待确认 |
| GET /api/v1/agent/runs/{run_id} | 读取持久化结果或待确认动作，不调用模型 |
| POST /api/v1/agent/runs/{run_id}/decisions | 批准或拒绝指定动作；批准后继续运行 |

这些接口需要 P1 的 MySQL 和 P2 的模型配置。沿用本机固定演示员工，不是完整登录系统。
创建请求会等待模型推进，属于请求内执行，不是后台任务队列。

## 新机器初始化 / 当前机器升级

```powershell
uv sync --locked --cache-dir .uv-cache
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -m uvicorn opsmind.main:create_app --factory --host 127.0.0.1 --port 8000
```

本轮已经升级当前开发库，新增 agent_run 表；没有删除业务记录。已有服务需要重启才能加载新接口。
操作示例留到你准备好时再做，每次模型调用可能产生费用。

## 只读运行示例

打开 http://127.0.0.1:8000/docs，选择 POST /api/v1/agent/runs：

```json
{
  "message": "查询设备 EQ-10023 的基本信息、最近维修和历史工单，结合记录说明还需要检查什么。"
}
```

结果字段：
- id：本次运行编号。
- status：当前状态。
- steps：已经发起的模型轮数。
- tool_calls：已经接受处理的工具调用数，包括参数错误等失败调用。
- elapsed_ms：已记录的模型与工具处理耗时，不包括等待人工确认。
- result：模型最终答复或拒绝说明。
- pending_action：等待确认的具体动作。
- events：步骤摘要和执行凭据，不公开完整内部消息。

本轮不宣称真实模型一定按某个固定顺序调用。若信息不足，模型也可以直接询问用户；
当前没有运行内追加用户消息接口，可以带上补充信息新建运行。

## 工具与风险

| 工具 | 风险 | 行为 |
| --- | --- | --- |
| get_equipment | LOW | 自动查询设备 |
| get_maintenance_history | LOW | 自动查询维修历史 |
| get_ticket_history | LOW | 自动查询工单历史 |
| create_ticket | MEDIUM | 仅生成待确认动作 |
| update_ticket | HIGH | 仅生成待确认动作 |

历史工具默认 5 条、最多 10 条，offset 最大 1000。长文本摘要最多 600 字符并标记截断；
单个 Tool Result 过大时返回明确错误，提示缩小范围。

参数由 Pydantic 校验，风险由服务器注册表决定。未知工具、额外字段、重复 JSON 键、
非法分页等不会直接执行。没有 SQL、Shell 或删除工具。

## 写入与确认

例如提交：

```json
{
  "message": "设备 EQ-10023 开机报警，请先检查相关记录，再为它提出一张电气类、高优先级的维修工单。"
}
```

当模型提出写入时，status 为 waiting_confirmation。pending_action 包含：
action_id、tool_call_id、tool、risk、arguments、expires_at。

**先检查 arguments 的设备、工单编号、标题、优先级和修改字段。**
创建参数包括服务端默认值，避免确认内容和实际执行内容不同。
此时工单尚未写入。

在确认接口中使用运行 id，提交：

```json
{
  "action_id": "替换为返回的32位action_id",
  "approved": true
}
```

拒绝则改为 false。确认请求只接受动作编号和布尔决定，不接受替换参数。
不满意现有参数时先拒绝，再用正确要求新建运行，不能用旧批准覆盖新内容。

确认后：
1. 锁定运行记录，核对运行所属演示员工、动作编号、状态和有效期。
2. 再次校验参数及当前业务权限。
3. 调用与 P1 相同的工单规则。
4. 工单写入与审批执行凭据在同一个外层事务提交。
5. 把真实执行结果回传给模型并继续循环。

拒绝后本次运行结束，不再自动请求模型提出替代写操作。

## 重复确认、失败和恢复

同一 action_id 的相同决定可以重复提交，只读取已有结果；
两个并发确认请求也只允许一个实际执行写入。相反决定返回 decision_conflict。

这只保证同一个动作的重复请求不会重复执行，**不等于不同运行之间的工单业务去重**。
重新创建运行并批准新动作仍可能新建另一张工单。

待确认运行保存在 MySQL，重启后仍可读取和确认。正在执行的进程意外退出后，
不会自动重放工具；运行过期后在后续查询时标记 run_interrupted。P5 再引入完整检查点恢复。

需要查看 events 中 kind=decision 的记录判断写入是否成功：
- approved=true 仅表示用户批准。
- ok=true 和 result 表示实际业务操作成功。
- ok=false 表示业务失败，附有安全错误码。
- 模型最后总结失败或步数耗尽，不会撤销已经成功提交的工单。
- 即使最终 status=failed，也不要直接重建工单，应先检查执行凭据。

模型自然语言不能当作写入凭据。用户在任务描述中写“我已批准”也不能绕过确认接口。

## 状态与预算

| 状态 | 意义 |
| --- | --- |
| running | 程序正在推进 |
| waiting_confirmation | 等待用户确认，尚未执行当前写入 |
| completed | 模型给出最终答复 |
| failed | 达到限制或发生错误；查看 error_code 和执行凭据 |
| rejected | 用户拒绝当前待确认动作 |

默认配置：
```dotenv
OPSMIND_AGENT_MAX_STEPS=6
OPSMIND_AGENT_MAX_TOOL_CALLS=8
OPSMIND_AGENT_TIMEOUT_SECONDS=120
OPSMIND_AGENT_APPROVAL_TTL_SECONDS=1800
```

预算保存在每个运行中，不会因确认接口重新调用而重置。
等待人工确认不消耗处理时间预算，但有独立有效期。模型等待可被总预算中断；
数据库操作依靠驱动超时和步骤边界检查，不在事务提交中间强制杀线程。

当前每个模型回复只接受一个工具调用。若供应商一次返回多个工具，明确失败而不偷偷遗漏其中的写入。
Prompt 要求一次一个工具；P3 未实现并行工具执行。

## 测试与实际边界

```powershell
.\.venv\Scripts\python.exe -m pytest --mysql -q
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
```

当前 142 项通过，P3 新增 37 项，其中包含真实 MySQL 上的：
多轮读取、持久化、拒绝、过期、权限变化、失败回滚、重复和并发确认、完整 HTTP 流程。

模型回复在自动测试中受控模拟，不消耗额度。2026-09-14 已完成一次真实 DeepSeek 只读多轮工具验证，详见阶段报告；人工确认创建工单及重复确认联调也已通过；更新工单的真实模型联调尚未进行。

内部 messages 会持久化用户任务和工具摘要，属于业务数据；仅本机演示，未实现多租户、
加密存储或自动保留期限。接口不返回完整消息，但有权限的数据库管理员可读取。

## 代码阅读

- [tools/registry.py](../src/opsmind/tools/registry.py)：工具定义、风险、参数。
- [llm/tool_protocol.py](../src/opsmind/llm/tool_protocol.py)：模型工具消息解析。
- [agent/runtime.py](../src/opsmind/agent/runtime.py)：循环推进。
- [agent/store.py](../src/opsmind/agent/store.py)：短事务中的运行状态。
- [agent/approval.py](../src/opsmind/agent/approval.py)：确认、幂等和业务事务。
- [agent/state.py](../src/opsmind/agent/state.py)：执行记录及过期处理。
- [api/agent.py](../src/opsmind/api/agent.py)：HTTP 接口。

官方协议参考：[DeepSeek Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)。
模型返回工具名称与参数，具体函数必须由应用执行；Tool Result 通过相应 tool_call_id 回传。


写操作结果展示：包含已批准执行凭据的运行，在完成时由程序根据凭据生成 result，明确成功工单编号或失败原因；纯只读运行仍使用模型总结。执行事件可用于核对实际写入结果。
