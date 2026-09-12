# P2 阶段报告

## Completed

已实现独立的异步 Chat Completions 客户端、DeepSeek v4 Pro 配置、独立 Prompt、Pydantic 结构化输出、超时和有限重试，以及 POST /api/v1/analyses。

新增本机密钥配置和单次真实调用检查脚本。分析接口只使用提交的故障描述，不读取业务数据库、不保存分析或创建工单。

代码、自动化验证和真实 DeepSeek 调用验证均已完成，P2 验收完成。

## Files Changed

- src/opsmind/llm/：客户端、协议解析、Prompt、类型与安全异常。
- src/opsmind/schemas/analysis.py：输入和输出结构。
- src/opsmind/services/analysis.py：结构校验与分析服务。
- src/opsmind/api/analysis.py：分析接口及 OpenAPI 错误响应。
- scripts/setup_llm.py、scripts/check_llm.py：本机配置和真实调用验证。
- tests/llm/：61 项新增自动测试。
- docs/p2-guide.md、docs/adr/0003-p2-model-client.md：操作教程与决策。
- 更新配置、主入口、异常处理、README 和依赖锁文件。

httpx 从开发依赖移到运行依赖，没有引入 LangChain、LangGraph 或模型 SDK。

## Architecture

HTTP 输入 → AnalysisRequest → 分析服务 → JSONClient 协议 → HTTP 客户端 → 模型供应商 → 协议解析 → FaultAnalysis 校验 → AnalysisResponse。

DeepSeek 特有 thinking 参数仅在客户端中处理。业务服务不依赖供应商 SDK 或 MySQL。

默认单次超时 30 秒、总预算 60 秒、最多 1 次重试、输出上限 1500 tokens。真实调用检查禁用重试。错误响应不包含供应商原文、密钥或 SQL。

## Verification

已执行：
- uv sync --cache-dir .uv-cache：依赖同步成功。
- pytest --mysql -q --tb=short：105 项通过，包括 23 项真实 MySQL 测试和 61 项新增 P2 自动测试。
- ruff check .：通过。
- 模拟 HTTP 验证：正常结果、请求参数、限流、服务器错误、认证、额度、网络异常、单次超时、总时限、重试次数、响应大小、空内容、截断及结构错误。
- API 验证：没有数据库仍可执行模拟分析；非法输入不调用模型；缺密钥返回明确错误；P1 保持可用。

首次真实请求认证失败；用户要求再次验证后，scripts/check_llm.py 成功调用 deepseek-v4-pro，并通过 Pydantic 结构校验。成功请求仅尝试 1 次，耗时 2620 ms；输入 567 tokens，输出 169 tokens，共 736 tokens。输入为合成故障描述，未发送数据库记录。模型返回待补充信息、建议和人工检查标记，possible_causes 为空，未强行给出确定原因。此结果证明当前连接和结构化输出可用，不证明诊断准确率。

## Problems

真实调用认证已通过。Windows 工具输出中的中文出现编码显示问题，但原始模型内容已在程序中成功解析并通过结构校验；未为显示问题重复调用付费模型。

两条既有 Starlette/AnyIO 弃用提示仍存在，未隐藏。当前固定演示身份仍不适合生产部署。

JSON 校验保证字段与类型，不保证事实正确；没有 Agent、RAG、语义评估或人工审批。

## Next Step

P2 验收完成后暂停。可在 /docs 亲自测试 POST /api/v1/analyses，理解模型调用与结构化输出后，再讨论 P3。
