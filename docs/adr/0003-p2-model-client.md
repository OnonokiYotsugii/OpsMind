# ADR 0003：独立 HTTP 模型客户端与双层输出校验

状态：接受。日期：2026-09-12。

采用 httpx AsyncClient 直接调用兼容 Chat Completions 的服务，业务层依赖 JSONClient Protocol。模型名称、地址、密钥来自统一配置，DeepSeek thinking 参数仅在 llm 客户端中添加。

用户选择 deepseek-v4-pro。P2 使用非 thinking 模式、JSON Object 输出；Prompt 独立并标记版本，用户输入放在单独 user 消息中。先验证供应商协议，再使用 Pydantic 校验业务输出。

不引入 SDK、LangChain、LangGraph 或重试依赖。已有 httpx 从开发依赖移到运行依赖。每次分析创建一个 HTTP 客户端并在请求结束时关闭；将来依据实际负载再考虑应用级连接池复用。

使用总时间预算、HTTP 超时、有限重试和响应大小限制。非正常模型结束、非法 JSON 或 Schema 不匹配明确失败，不使用隐式修复和免费假设。

P2 不依赖数据库，不执行工具、不保存分析、不创建工单。needs_human_review 是模型输出，不能用作自动写入授权。JSON 结构校验不保证事实或推理正确，系统评估留待 P6。

自动测试模拟模型 HTTP 边界，不替代一次真实供应商调用验证；MySQL 回归继续使用真实数据库。
