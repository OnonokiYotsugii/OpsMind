# P4 操作与学习教程

## 这次增加了什么

P3 的 Agent 可以查询真实业务记录。P4 增加一个“查资料”的只读工具，让它先找到手册片段，再结合记录回答。

流程：文档 → 切分 → 本地 Embedding → Chroma 向量索引 → search_knowledge → DeepSeek 综合回答。

- Chunk：文档的小片段，当前按标题、段落和 100 字符上限切分，保留原始行号；第一版不做重叠切分。
- Embedding：把文字变成一组数字，当前模型生成 384 维向量，用来寻找语义接近的文字。
- Chroma：保存向量、片段文字和位置。MySQL 保存文档名称、版本、来源、导入状态。
- Retrieval：把问题也转换成向量，找接近的片段。默认最多返回 3 段，最大 5 段。
- RAG：把检索结果提供给模型辅助回答。它不训练或微调 DeepSeek。

DeepSeek 仍需要现有 API Key。本地向量模型首次下载后，无需新的 API Key。FastEmbed 使用 ONNX 在 CPU 上运行多语言 MiniLM。首次加载会比后续查询慢。

## 本机已经完成的准备

开发库已升级到迁移 0003。模型已下载到 `.cache/embeddings`，两份演示资料已导入 `.data/chroma`，共 9 个片段。两个目录已被 Git 忽略。

以下所有命令都在 PyCharm 底部 Terminal 中执行，工作目录是 `D:\project\OpsMind`。已运行的旧服务需要停止后重新启动才能加载新接口。

```powershell
.\.venv\Scripts\python.exe -m uvicorn opsmind.main:create_app --factory --host 127.0.0.1 --port 8000
```

## 先独立测试检索

打开 http://127.0.0.1:8000/docs，找到 `POST /api/v1/knowledge/search`，点击 Try it out，填写：

```json
{"query":"DEMO-24V E102 供电电压异常","limit":3}
```

结果中的 items 是检索到的片段。查看 text、title、version、source、heading、line 和 citation。

- citation 是回答可以引用的编号，例如 `[KB-文档ID-1]`。
- distance 越小表示向量越接近，**不是诊断正确率**。默认过滤大于 0.22 的结果。
- items 为空可能是无相关内容、过滤条件不匹配或没有 ready 文档。不要理解成设备不存在或肯定没有故障。

再试 `{"query":"如何制作草莓蛋糕"}`，当前演示资料应返回空数组。

也可以直接执行：

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/knowledge.py search "DEMO-24V E102 供电电压异常"
```

## 再测试 Agent

使用 `POST /api/v1/agent/runs`：

```json
{"message":"仅做只读分析：EQ-10023 出现 E102 报警，请查询设备及维修记录，再检索对应型号知识库，说明可能原因并引用来源。每轮只调用一个工具。"}
```

观察 events 中是否出现 search_knowledge，以及 result 是否带有 `[KB-...]` 和程序追加的参考来源。Agent 自主选择顺序，可能需要补充查询。

如果模型提出写操作，仍会进入 waiting_confirmation，本阶段的检索不会自动批准。查询运行详情不调用模型。

## 导入自己的测试文档

仅支持 UTF-8 Markdown 和 TXT，每份最多 200 KB、1000 个片段。先在 `knowledge/` 放置文件，再执行：

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/knowledge.py import knowledge/demo-power.md --title "DEMO-24V 演示说明书" --source demo-power --version 1.0
```

source 是稳定来源标识，不是让系统访问的 URL；version 是资料版本。相同来源、版本、内容和标题重复导入时返回 reused=true。内容或标题改变必须使用新版本。

导入分两步：先登记 indexing，再生成向量并写入，最后标记 ready。中途失败的片段不会被检索，使用原命令重试会按相同编号恢复。

如果索引目录丢失而 MySQL 登记仍在，用相同文件、相同元数据并加 `--rebuild` 重建：

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/knowledge.py import knowledge/demo-power.md --title "DEMO-24V 演示说明书" --source demo-power --version 1.0 --rebuild
```

第一版导入是维护者本机脚本，不向 Agent 开放任意文件访问，也没有上传接口。多版本可以同时存在；检索可传 source、version 精确筛选，不自动认定最新版本有效。导入命令请串行执行。

## 在另一台机器准备

```powershell
uv sync --locked --cache-dir .uv-cache
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -X utf8 scripts/knowledge.py prepare
.\.venv\Scripts\python.exe -X utf8 scripts/knowledge.py import knowledge/demo-power.md --title "DEMO-24V 演示说明书" --source demo-power --version 1.0
.\.venv\Scripts\python.exe -X utf8 scripts/knowledge.py import knowledge/demo-process.md --title "演示运维规范" --source demo-process --version 1.0 --document-type procedure
```

仍需先配置本机 MySQL 及 `.env`，不要覆盖已有密码和 API Key。prepare 是唯一允许主动下载模型的项目命令；正常查询只读取本地模型。缺少模型返回 embedding_unavailable。

## 验证与边界

```powershell
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
.\.venv\Scripts\python.exe -m pytest --mysql --embedding -q
.\.venv\Scripts\alembic.exe check
```

168 项通过；不加 --embedding 会跳过一个真实语义检索测试。不加 --mysql 会跳过 MySQL 集成测试。自动测试不调用付费聊天 API。

两条已有测试依赖弃用提示仍在；另有 FastEmbed 提醒此模型使用 mean pooling，这是当前新索引使用的行为，不需要改回旧版。下载时 Windows 无符号链接权限提示只影响缓存占用，不需要为此提升整个编辑器权限。

引用校验只保证编号来自工具返回结果，不能证明每一句话都被资料支持。未引用或引用未知编号时，结果替换成校验失败说明。知识内容通过提示隔离为数据；这不等于对提示注入有完整防御。

模型曾把工单和维修记录当成两次独立维修，已增加提示约束，但仍需人工核对。相似度阈值仅经过小规模演示检查，系统不是可独立执行现场诊断的产品。演示资料的报警码不适用于真实设备。

检索超时会停止 Agent 等待，但已启动的本地推理线程可能继续完成只读计算。第一版适合本机小型资料库，不是多租户检索服务。
