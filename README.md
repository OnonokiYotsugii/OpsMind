# OpsMind

企业设备智能运维工单 Agent 学习与求职项目，按阶段构建。

**当前阶段：P3 Tool Calling 与 Agent Loop。** 保留 P1/P2，新增业务工具、多轮 Agent 和持久化人工确认。142 项自动测试通过；P3 真实模型只读、人工确认创建工单与重复确认联调已通过。尚未实现 RAG 或 LangGraph。

最终目标：结合业务数据和知识库诊断设备故障，经人工确认后创建或修改工单。当前 P1 先建立不带 AI 的可靠业务基础。

## 快速开始（Windows / PowerShell）

需要 Python 3.13、uv、Git、已启动的 MySQL 8（CHECK 约束要求 8.0.16+）。所有命令在项目根目录运行；PyCharm 选择已有解释器 `.venv/Scripts/python.exe`。

```powershell
uv sync --locked --cache-dir .uv-cache
# 仅首次配置：本机交互输入管理员密码，创建独立库与专用账号。
.\.venv\Scripts\python.exe scripts/setup_local_mysql.py
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe scripts/seed_demo.py
.\.venv\Scripts\python.exe -m uvicorn opsmind.main:create_app --factory --host 127.0.0.1 --port 8000
```

已配置数据库的机器跳过 setup_local_mysql.py。它不覆盖已有连接配置；若指定库已有表，会停止保护现有数据。脚本只保存生成的应用账号连接串，不保存管理员密码。手动配置可参考 `.env.example`，不要覆盖已有 `.env`。

浏览器打开 [接口文档](http://127.0.0.1:8000/docs)，查询 `EQ-10023`。完整的新手步骤见 [P1 操作教程](docs/p1-guide.md)。

## P3 Agent

新增运行、结果查询和确认接口；只读工具自动执行，写入等待具体动作确认。升级数据库后重启服务，详见 [P3 操作说明](docs/p3-guide.md) 和 [P3 阶段报告](docs/p3-report.md)。

## P2 模型分析

新增 POST /api/v1/analyses，只分析用户输入，不查询数据库或写入工单。用户选择 DeepSeek deepseek-v4-pro；密钥存本机 .env。配置、真实调用验证和错误说明见 [P2 操作教程](docs/p2-guide.md)。

## 已实现接口

| 方法与路径 | 功能 |
| --- | --- |
| POST /api/v1/agent/runs | 创建并推进 Agent 运行 |
| GET /api/v1/agent/runs/{run_id} | 查询运行状态与执行凭据 |
| POST /api/v1/agent/runs/{run_id}/decisions | 确认或拒绝具体写操作 |
| POST /api/v1/analyses | 模型初步分析（不写工单） |
| GET /health | 进程健康检查，不代表数据库连接正常 |
| GET /api/v1/equipment/{equipment_no} | 设备基本信息 |
| GET /api/v1/equipment/{equipment_no}/maintenance-records | 维修历史 |
| GET /api/v1/equipment/{equipment_no}/tickets | 工单历史 |
| POST /api/v1/tickets | 创建工单 |
| PATCH /api/v1/tickets/{ticket_no} | 更新允许的字段 |

历史接口使用 limit（默认 20，最大 100）和 offset（默认 0，最大 10000），按时间、ID 倒序排序，返回 items、limit、offset。不存在的设备返回 404；参数错误返回 422；业务状态冲突返回 409；操作员工无权限返回 403；数据库不可用返回 503。错误响应不回传 SQL 或请求原文。

P1 使用服务端配置的演示员工 `OPSMIND_DEMO_EMPLOYEE_NO`，默认 `EMP-1001`。请求不能指定 created_by。**这不是认证系统，只适合本机演示，不应暴露到公共网络。** production 配置会拒绝启动。P3 Agent 写入必须通过确认接口；P1 的手动工单接口仍是独立的用户主动操作入口。

## 验证

```powershell
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
# 普通测试；真实数据库测试会明确跳过
.\.venv\Scripts\python.exe -m pytest -q
# 完整验收：必须有有效的独立 MySQL 测试库
.\.venv\Scripts\python.exe -m pytest --mysql -q
.\.venv\Scripts\alembic.exe check
```

完整测试在本机已通过 142 项，其中 P2 新增 61 项、P3 新增 37 项。模型 HTTP 使用模拟传输；真实模型检查单独运行，不计入自动测试。测试限定本机 `opsmind_test`，拒绝与应用/迁移库同名；每个测试使用外层事务隔离，结束后回滚。不使用 SQLite 或 Mock 替代 MySQL 的业务与约束测试。错误响应单元测试注入数据库异常，仅验证响应脱敏。

锁定的 Starlette TestClient 对 httpx 及 AnyIO 的兼容接口产生两条上游弃用提示，当前测试仍通过；未隐藏警告。后续升级测试客户端时处理，不影响本阶段接口功能。

## 目录与依赖

```text
src/opsmind/
  main.py          服务入口
  core/            配置、日志、枚举和业务异常
  api/             路由、请求依赖、错误响应
  schemas/         输入校验与输出结构
  services/        查询与工单规则、写事务
  db/              ORM、连接、示例数据
  tools/           工具白名单与执行
  agent/           循环、持久化与确认
alembic/           可版本化的数据库迁移
scripts/           本机数据库配置与数据导入
tests/             单元与真实数据库集成测试
docs/              架构、决策和学习说明
```

| 依赖 | 用途 |
| --- | --- |
| pydantic-settings / Pydantic | 配置、请求和响应校验 |
| FastAPI | HTTP 接口和 OpenAPI 文档 |
| Uvicorn | ASGI 服务运行 |
| SQLAlchemy | ORM 与事务 |
| PyMySQL[rsa] | MySQL 驱动及认证所需的 RSA 支持 |
| Alembic | 表结构迁移 |
| httpx | 模型 HTTP 调用与 HTTP 测试传输 |
| pytest | 自动化测试 |
| Ruff | 代码检查与格式化 |
| Hatchling | src 布局包的构建与安装 |

配置顺序：显式构造参数 > 环境变量 > 根目录 .env > 默认值。日志输出 UTC 时间、级别、模块和事件；禁止记录密码、配置全文和原始业务请求。SecretStr 只是防止意外打印，不是加密或自动日志脱敏。

## 阶段规划

P0 工程基础 → P1 业务后端 → P2 模型客户端 → **P3 手写 Agent 与工具审批** → P4 RAG → P5 LangGraph → P6 评估与观测 → P7 部署展示。

每阶段验收后暂停。详见 [项目要求](项目.md)、[架构](docs/architecture.md)、[数据库](docs/database.md)、[P1 报告](docs/p1-report.md)、[学习与作品证据](docs/learning.md)、[P2 报告](docs/p2-report.md)。
