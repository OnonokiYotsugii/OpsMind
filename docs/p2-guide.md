# P2：模型调用与结构化分析

## 本阶段做了什么

新增 POST /api/v1/analyses。输入一段故障描述，调用 DeepSeek，校验模型结果后返回 JSON。

本阶段没有 Tool Calling、Agent Loop、RAG，也不查询或修改业务数据库。即使描述中有 EQ-10023，模型也只看到这段文字，不会自动读取这台设备的历史记录。

## 1. 配置本机密钥

先同步依赖：

```powershell
uv sync --locked --cache-dir .uv-cache
```

推荐在 PyCharm Terminal 执行本机交互脚本：

```powershell
.\.venv\Scripts\python.exe scripts/setup_llm.py
```

输入 API Key 时不显示字符。脚本把密钥写入 Git 忽略的 .env，保留已有数据库设置。空输入取消。不要将密钥发到聊天、截图或提交到 Git。

也可以手动在 .env 增加以下内容，真实密钥只填在本地：

```dotenv
OPSMIND_LLM_PROVIDER=deepseek
OPSMIND_LLM_BASE_URL=https://api.deepseek.com
OPSMIND_LLM_MODEL=deepseek-v4-pro
OPSMIND_LLM_API_KEY=
OPSMIND_LLM_TIMEOUT_SECONDS=30
OPSMIND_LLM_TOTAL_TIMEOUT_SECONDS=60
OPSMIND_LLM_MAX_RETRIES=1
OPSMIND_LLM_MAX_OUTPUT_TOKENS=1500
```

模型名字是 deepseek-v4-pro，不是 v4pro。API Key 未配置时，P1 的查询和工单仍可使用，分析接口返回 503 llm_not_configured。

base URL 由本机环境配置，不从 HTTP 请求接受。其他兼容服务可选择 openai_compatible，以省略 DeepSeek 的 thinking 参数；兼容性仍需逐个验证，不能保证任何服务都支持 JSON Output。

## 2. 一次真实调用验证

```powershell
.\.venv\Scripts\python.exe scripts/check_llm.py
```

脚本发送一条合成故障描述，最多一次请求，不自动重试。会产生供应商 API 用量。成功后输出经过校验的分析、模型名、用量及耗时；失败时只输出安全错误码，不显示密钥或供应商响应全文。

它检查连接与结构化输出是否可用，不证明模型诊断一定正确。

## 3. 在 /docs 操作

如果后端已经运行，按 Ctrl+C 停止并重新启动，让新代码和配置生效：

```powershell
.\.venv\Scripts\python.exe -m uvicorn opsmind.main:create_app --factory --host 127.0.0.1 --port 8000
```

打开 http://127.0.0.1:8000/docs，选择 POST /api/v1/analyses → Try it out，填写：

```json
{
  "description": "演示设备 EQ-DEMO 开机后持续报警，没有报警码，也没有测量信息。"
}
```

执行后观察：
- analysis.summary：问题摘要。
- possible_causes：可能原因，不是确定诊断。
- missing_information：还缺少的信息。
- suggested_actions：初步建议。
- needs_human_review：模型判断是否需要人工检查。
- scope=user_input_only：程序固定声明本次只使用用户输入。
- model：供应商返回的模型标识。
- usage：供应商提供的 Token 用量；没有提供时为 null，不伪造为 0。
- attempts：本次程序实际发起的 HTTP 尝试次数。
- latency_ms：包括重试等待的客户端耗时。

只发送可以提交给模型供应商的信息。P2 不自动附带数据库、员工记录或配置。

## 4. JSON 格式正确，还需要什么？

供应商 JSON Output 帮助模型返回合法 JSON；Pydantic 再验证字段、类型和长度。

例如模型返回 {"answer":"可能是电池问题"} 虽是合法 JSON，但不符合本项目分析模型，所以返回 502 llm_invalid_output。

本项目不会自动删代码围栏、补缺失字段、填假默认值或把格式失败当成功。坏输出也不会触发额外的“修复生成”请求。

结构校验只能证明格式符合要求，不能证明诊断正确或完全遵循 Prompt。提示词要求区分事实和推测，但没有实现语义安全证明、现场验证或系统评估。

## 5. 超时与重试

- 单次 HTTP 阶段超时默认 30 秒。
- 总时限默认 60 秒，覆盖读取、重试等待等整个调用。
- 默认最多重试 1 次，也就是最多 2 次 HTTP 尝试。
- 对 429、500、502、503、504 和传输错误进行有限重试。
- 采用短退避等待；支持 0—5 秒的数字 Retry-After，其他值使用退避。
- 认证失败、额度问题、请求格式错误不重试。
- 空响应、截断、非正常结束、非法输出不重试。
- 输出默认最多 1500 tokens，响应体最多 256000 字节。
- P2 显式关闭 DeepSeek thinking，先验证简单稳定的结构化输出。
- 超时或网络失败不代表供应商没有生成内容；再次请求可能产生额外费用。不会把重试当作免费操作。

## 6. 错误排查

| 错误码 | 意思 / 下一步 |
| --- | --- |
| llm_not_configured | 在本机配置 API Key 并重启服务 |
| llm_authentication_failed | 检查密钥及模型访问权限；不会自动重试 |
| llm_balance_unavailable | 检查供应商账户额度 |
| llm_request_rejected | 检查模型名、base URL 和协议参数 |
| llm_timeout | 超过单次或总时限 |
| llm_connection_failed | 网络、TLS 或连接失败 |
| llm_rate_limited | 限流，有限重试后仍失败 |
| llm_unavailable | 上游暂不可用 |
| llm_empty_response | 上游没有返回内容 |
| llm_output_truncated | 达到输出限制，未接收完整结果 |
| llm_invalid_output | JSON 内容不符合分析模型 |
| llm_invalid_response | 上游 HTTP 正文不符合协议结构 |

HTTP 客户端关闭自动重定向和环境代理继承，避免密钥被无意转发。当前需要显式代理的网络环境可能无法连接，不会偷偷关闭 TLS 校验。

P2 的错误响应已声明在 OpenAPI 中。日志只记录固定事件、错误码、次数和耗时，不记录 Prompt、模型原文和密钥。

## 7. 测试和源码

```powershell
.\.venv\Scripts\python.exe -m pytest --mysql -q
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
```

自动测试通过 httpx.MockTransport 模拟模型服务，验证真实客户端的请求、重试及解析行为，不消耗模型额度。它们与真实模型 smoke check 是两种证据，不能互相替代。P1 集成测试仍使用真实 MySQL。

阅读路线：
1. [分析接口](../src/opsmind/api/analysis.py)
2. [输入和输出模型](../src/opsmind/schemas/analysis.py)
3. [业务服务](../src/opsmind/services/analysis.py)
4. [Prompt](../src/opsmind/llm/prompts.py)
5. [HTTP 客户端](../src/opsmind/llm/client.py)
6. [协议解析](../src/opsmind/llm/protocol.py)

当前自动测试通过 105 项，其中 P2 新增 61 项。两条既有 Starlette/AnyIO 弃用提示仍保留。

## 8. 本阶段学什么

- LLM Client：负责向模型服务发请求的代码。
- Prompt：给模型的任务说明和上下文；不是权限控制器。
- Structured Output：可供程序继续处理的结构化结果。
- Protocol：定义服务需要的客户端能力，方便替换实现。
- async / await：等待网络时允许事件循环执行其他任务。
- Timeout：限制等待时间。
- Retry：有上限地重新尝试，不代表一定成功。
- Token：模型接口统计输入输出量的单位，不等同于字符数。

完成 P2 后暂停。P3 才让模型选择 Tool；不要把当前单次分析接口称为 Agent。

## 官方依据

核对日期：2026-09-12。
- [DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)：模型名称、thinking 开关及请求协议。
- [DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode/)：JSON 模式、Prompt 要求及空内容限制。
