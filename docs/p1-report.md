# P1 阶段报告

## Completed

实现四个业务实体、六个 HTTP 接口、参数与业务校验、基础权限规则、分页、统一错误响应、MySQL 迁移、本机数据库配置脚本及可重复导入的演示数据。

配置使用独立的应用、迁移、测试账号。应用默认连接本机开发库；不开放删除接口。演示数据的维护时间更新和工单写入都使用事务。

## Files Changed

新增 api、schemas、services、db 模块，main.py，alembic 配置与首个迁移，scripts 下两个操作脚本，单元与真实 MySQL 测试，P1 教程和报告。更新依赖与锁文件、配置示例、README 及架构/数据库说明。

## Architecture

同步 FastAPI 路由调用服务，服务管理写事务，SQLAlchemy / PyMySQL 负责 MySQL 持久化。更新工单时使用行锁，防止并发状态变更根据过时状态执行。响应模型标注 UTC 时间，输入拒绝额外字段和不合法的局部更新。

本地演示身份由服务端配置，不能由请求体指定创建人。requester 可以创建但不能分配工单；technician/admin 可以更新。完整认证与 Agent 审批均未实现。

## Verification

已执行：
- uv sync --cache-dir .uv-cache
- ruff check . / ruff format --check .
- alembic upgrade head
- scripts/seed_demo.py 连续两次：首次新增 3 员工、1 设备、1 维修记录、1 工单；第二次全部新增 0。
- pytest --mysql -q：44 项通过，包含 23 项真实 MySQL 测试。
- 集成测试中的 alembic check：数据库与模型没有待迁移差异。
- 实际启动 Uvicorn：/health、/docs、OpenAPI、设备与两类历史请求返回 200，不存在设备返回 404。
- 验证结束后测试库工单数为 0，证明测试事务没有留下工单。

真实数据库验证覆盖查询、分页、创建、完整状态流程、权限限制、非法参数、外键、唯一约束、CHECK、删除限制及事务回滚。不使用 Mock 替代数据库业务测试。

## Problems

P1 仅为本地演示后端，没有登录认证、生产部署、AI、RAG 或 Agent 审批。服务用 production 配置启动会被拒绝。

当前锁定的 Starlette TestClient 对 httpx 和 AnyIO 兼容接口产生两条弃用警告；不影响现有 44 项测试。未用过滤规则隐藏这些警告。

## Next Step

先完成 P1 教程中的手动查询、创建和修改实验，理解 HTTP、请求模型、ORM 与事务，再计划 P2 模型客户端。禁止直接进入 Agent 或 RAG。
