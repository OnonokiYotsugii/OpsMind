# P6：评测与执行记录，新手说明

P6 要解决两个问题：程序做得对不对，以及出问题时能否知道是哪一步。Evaluation 是用固定题目验收；Trace 是一次运行的过程记录。

## 这次增加了什么

- `evaluation/cases.v1.jsonl`：18 道题，涵盖设备查询、分类、工具、知识检索、多步骤任务、工单和风险操作。
- `scripts/evaluate.py`：执行题目，检查状态、工具参数、引用和实际数据库变化，生成 JSON 与 Markdown 报告。
- `GET /api/v1/agent/runs/{run_id}/trace`：查看模型调用、工具耗时、检索来源、审批等待与错误。

Trace 不返回完整提示词、工具参数或业务结果；它沿用运行记录的员工访问检查。本项目仍是本机演示身份，并不是生产认证系统。

## 两种评测有什么区别

默认 `scripted` 用事先写好的聊天响应驱动真实 Agent、工具和测试数据库；知识检索仍使用真实本地向量模型。它验证流程和评分程序是否按预期工作，不验证 DeepSeek 的理解能力。

`live` 才会请求配置的真实模型，会消耗额度。同一题模型可能回答不同，因此真实效果必须单独报告。本轮没有运行 live。模拟模型超时案例只属于 scripted，live 会跳过，因此完整 live 集合为 17 道题。

## 以后怎样运行

在项目根目录的 PyCharm 终端执行，MySQL 保持启动。本机测试库和向量模型已准备好：

```powershell
.\.venv\Scripts\python.exe -m pytest --mysql --embedding -q
.\.venv\Scripts\python.exe scripts/evaluate.py
```

第一条运行自动测试，也检查测试库迁移；第二条默认不调用付费聊天模型。终端给出报告路径，打开该目录的 `report.md` 看概要、`results.json` 看逐题检查与 Trace。失败会返回非零退出码。

今后决定做真实联调时，才使用下面的命令：

```powershell
.\.venv\Scripts\python.exe scripts/evaluate.py --mode live --allow-test-writes
```

`--allow-test-writes` 只允许预先声明的测试审批，且待确认工具和参数必须匹配题目。评测强制使用本机 `opsmind_test`，每道题外层事务最终回滚，不写开发业务库。不要把这个开关理解成允许模型任意操作。

## 怎样读分数

| 指标 | 实际含义 |
| --- | --- |
| task_success_rate | 状态、错误、答案检查、工具、检索、写入检查全部通过的题目比例 |
| classification_accuracy | 精确匹配类别标签的比例，本集合只有 2 题 |
| tool_selection_case_accuracy | Agent 题目中必需工具和参数匹配、没有额外越界工具的比例；按题统计，不按每次调用统计 |
| retrieval_hit_or_abstention_rate | 标注资料命中，或无关问题返回空结果；只有 4 题，不是通用检索准确率 |
| mean_tool_calls | Agent 题目的平均已记录工具执行次数，不包括纯检索题；写入提议与审批实际执行分别记录 |
| token_usage | 完整可观测的供应商用量；缺失、重试或旧记录不完整时为 null（未知） |
| observed_token_usage | 仅已收到的有效用量之和，不能作为完整账单 |
| mean_wall_ms / p95_wall_ms | 每题运行耗时，包括需要的资料导入；小样本 p95 不能代表生产性能 |
| runtime_error_rate | 运行失败比例；故意模拟超时也计入，所以任务全通过时它仍可非零 |

报告保留各比例分母。关键词与引用编号检查不能证明诊断在语义上正确，仍需人工评阅真实回答。scripted 的 Token 为 null 是正常现象，因为没有供应商用量。

## 怎样查看一次运行

重启后端，在 `/docs` 里找到 GET Trace 接口，填入正常创建的 `run_id` 执行。`model_start/model_end` 是模型调用；`tool_span` 是工具执行；`retrieval` 保存来源编号和距离；`decision` 是审批结果。

`observed_processing_ms` 仅累计已记录的模型、工具和写入耗时，不含人工等待、检查点 IO，也不保证覆盖进程中断或检索超时前未提交的耗时。`approval_wait_ms` 仅汇总已经作出决定的审批等待，不是当前待审批计时器。旧运行的 coverage 为 legacy_partial，不能补出历史完整指标。

评测事务会回滚，所以评测 run_id 不能事后从 API 查询，使用报告内保存的 Trace。`.data/evaluation` 的临时向量索引与 `.data/evaluation-reports` 报告保留在本机且被 Git 忽略，运行多次后会占用磁盘。

本轮结果见 [P6 阶段报告](p6-report.md)；手动验收和真实模型联调按计划留到最后。
