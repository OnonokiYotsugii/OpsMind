# OpsMind

企业设备智能运维工单 Agent，作为 Python 后端与大模型应用开发的学习及求职项目，按阶段构建。

**当前阶段：P0 工程基础。尚无业务 API、数据库表或 AI 功能。** 不将规划中的能力写成已经实现的成果。

最终场景：输入设备编号和故障描述，结合设备信息、维修历史、工单及知识库提出有依据的诊断；写操作必须经过人工确认。

## 本地开始

需要 Python 3.13、uv 和 Git。MySQL 8 在 P1 才需要启动和配置。

在项目根目录用 PowerShell 执行：

```powershell
uv sync --locked
Copy-Item .env.example .env
uv run python -c "from opsmind.core.config import Settings; from opsmind.core.logging import configure_logging; configure_logging(Settings()).info('configuration ready')"
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

仅在首次配置时复制 `.env`，避免覆盖已有配置。uv 创建项目独立 `.venv`；无需修改 Anaconda 全局环境。若系统 uv 缓存不可写，可在命令中加入 `--cache-dir .uv-cache`。需要联网下载依赖；已锁定版本见 `uv.lock`。

## 工程约定

- 使用 `src` 布局，通过安装包导入，避免依赖当前目录偶然导入成功。
- 配置入口：`src/opsmind/core/config.py`。环境变量优先于根目录 `.env`，再使用默认值。
- 日志入口：`src/opsmind/core/logging.py`。由未来应用启动时显式配置，输出 UTC 时间到 stderr。
- 密码使用 `SecretStr` 避免意外打印，但禁止主动解密后写日志；不记录原始请求、Prompt 或数据库连接串。
- 测试不依赖真实数据库或付费模型。P1 增加真实 MySQL 集成测试，不能用 Mock 替代数据库约束验证。

## 依赖用途

| 依赖 | 用途 |
| --- | --- |
| pydantic-settings | 环境配置读取和类型校验，间接引入 Pydantic |
| pytest | 自动化测试 |
| ruff | 静态检查、导入排序和格式化 |
| hatchling | 构建并安装 src 布局的 Python 包 |

FastAPI、SQLAlchemy、PyMySQL、Alembic 在 P1 引入；不提前安装 LLM、RAG 或工作流框架。

## 分阶段交付

| 阶段 | 验收结果 |
| --- | --- |
| P0 | 工程配置、日志、架构和数据库设计 |
| P1 | 可运行的业务后端、MySQL 初始化、测试数据和接口测试 |
| P2 | 独立模型客户端、结构化输出和异常处理 |
| P3 | 手写工具循环、步数限制、基础人工审批 |
| P4 | 可追溯的知识检索和联合诊断 |
| P5 | LangGraph 状态、检查点和审批恢复 |
| P6 | 固定评估集、执行追踪和量化指标 |
| P7 | 部署、展示界面和演示材料 |

每个阶段完成后停下验收，再进入下一阶段。详见 [原始要求](项目.md)、[架构](docs/architecture.md)、[数据库](docs/database.md)、[技术决策](docs/adr/0001-project-foundation.md)、[学习与作品证据](docs/learning.md)。
