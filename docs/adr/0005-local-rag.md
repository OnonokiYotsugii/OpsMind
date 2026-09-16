# ADR 0005：本地 RAG 与可追溯文档

状态：采用（P4，2026-09-16）。

## 决策

使用 Chroma 1.5.9 本地持久索引、FastEmbed 0.8.0 的多语言 MiniLM ONNX 模型。模型与聊天 API 解耦；正常业务请求禁止隐式下载。新增依赖 chromadb 用于向量索引、fastembed 用于本地推理，传递依赖及版本写入 uv.lock。

最初考虑 E5-small，但安装版本未列为支持模型，最终使用明确支持的 sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2。它采用 mean pooling，384 维，CPU 两线程。

文档身份由来源和版本唯一约束；内容哈希检测同版本变更。MySQL indexing/ready 控制可见性，Chroma 使用稳定文档ID与片段序号 upsert。跨存储不假装拥有原子事务：中途故障留在 indexing，重复执行恢复；显式 rebuild 可恢复丢失的索引。相同来源版本的并发首次导入可能唯一键冲突，维护脚本应串行使用。

索引键 minilm-multi-c100-v1 区分模型和切分版本。更换模型、池化行为或切分策略需新索引键和迁移方案，不能复用不同向量空间。模型权重当前由本地缓存固定，未实现跨机器权重哈希核验。

检索在 Agent SQL 事务外执行，返回至原有运行状态机；执行前检查预算、重复调用ID和运行状态。多工具响应被拒绝并提示模型重选，仍消耗步骤和时间预算。

## 边界

100 字符短片段保留标题及行号，暂无重叠、PDF/OCR、重排、混合关键词检索或自动最新版本策略。距离不是置信度。引用编号校验不等于语义验证。只读检索不能改变人工审批规则。

## 参考

- [Chroma 查询与显式向量](https://docs.trychroma.com/docs/querying-collections/query-and-get)
- [FastEmbed 支持模型](https://qdrant.github.io/fastembed/examples/Supported_Models/)
- [Sentence Transformers 多语言模型](https://sbert.net/docs/sentence_transformer/pretrained_models.html)
- [DeepSeek Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)
