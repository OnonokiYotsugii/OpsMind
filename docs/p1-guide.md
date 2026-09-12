# P1 新手操作教程

## 先认识这次新增的功能

P0 只能读取配置和记录日志。P1 现在能通过 HTTP 请求查询 MySQL，并保存工单。

一次查询经过：浏览器 → Uvicorn 接收连接 → FastAPI 匹配接口 → 业务服务 → SQLAlchemy → PyMySQL → MySQL。结果沿原路返回为 JSON（一种用字段名和值表示数据的文本格式）。

- FastAPI 定义“有哪些接口、输入是什么”。
- Uvicorn 让这个应用在本地端口上持续接收请求。
- SQLAlchemy 把 Python 对象与数据库记录联系起来。
- PyMySQL 负责和 MySQL 通信。
- Alembic 负责建立和演进表结构，不处理日常工单创建。

## 第一次在新机器准备数据库

在 PyCharm Terminal（PowerShell）中：

```powershell
uv sync --locked --cache-dir .uv-cache
.\.venv\Scripts\python.exe scripts/setup_local_mysql.py
```

输入管理员账号（直接回车为 root）和密码（不会显示字符）。不要把密码发到聊天或写入代码。

脚本创建：
- opsmind_dev：日常演示数据。
- opsmind_test：自动化测试数据。
- 应用账号：开发库 SELECT / INSERT / UPDATE。
- 迁移账号：只管理开发库。
- 测试账号：只管理测试库。

生成的账号与密码保存在 .env；root 密码不保存。配置已完成时不必重复运行。脚本发现已有表时拒绝继续，不会删除它们。

然后运行：

```powershell
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe scripts/seed_demo.py
```

upgrade head 表示“把数据库结构更新到项目最新版本”。seed_demo 添加演示设备、员工、维修记录和历史工单；再次运行应显示新增数量全为 0，不覆盖用户修改。

不要在有用的数据上尝试 alembic downgrade：它可以删除表，用于明确需要回退的场合。

## 实验一：启动服务

```powershell
.\.venv\Scripts\python.exe -m uvicorn opsmind.main:create_app --factory --host 127.0.0.1 --port 8000
```

Terminal 会一直被服务占用，这是正常的。保持它打开，用浏览器访问：

- http://127.0.0.1:8000/health ：应显示 {"status":"ok"}。
- http://127.0.0.1:8000/docs ：自动生成的接口操作页面。

127.0.0.1 指自己的电脑；8000 是程序监听的端口；路径 /health 指具体接口。停止服务按 Ctrl+C。提示端口被占用时先检查是否已经运行了一个实例。

/health 只说明程序存活；查询设备成功才说明当前数据库读取可用。

## 实验二：查询设备

在 /docs 中展开 GET /api/v1/equipment/{equipment_no}：

1. 点 Try it out。
2. equipment_no 输入 EQ-10023。
3. 点 Execute。

应返回状态码 200 和设备 JSON。然后把编号换成 EQ-NOTFOUND，应返回 404 和 equipment_not_found。

200 表示请求成功；404 表示找不到对象。错误响应也是后端功能的一部分。

用相同方法查询 maintenance-records 和 tickets，观察 items 数组内的历史记录。limit 控制这一页最多几条，offset 表示跳过前面几条。

## 实验三：创建工单

展开 POST /api/v1/tickets，点 Try it out，把请求体替换为：

```json
{
  "equipment_no": "EQ-10023",
  "title": "开机后持续报警",
  "description": "今天开机后一直报警，请安排检查。",
  "category": "electrical",
  "priority": "high"
}
```

执行后应返回 201 和新的 ticket_no。把编号复制下来，再查询设备的 tickets，应该能看到它。

此时记录已经保存在 MySQL，不是临时显示的文字；重启后端服务后仍然可以查询到。

created_by 来自服务端的演示员工配置，不能由请求体伪造。不要把演示身份误认为已经完成登录认证。

## 实验四：更新工单

找到 PATCH /api/v1/tickets/{ticket_no}，填写刚刚创建的编号，请求体先使用：

```json
{
  "title": "开机后持续报警，等待维修"
}
```

应返回 200。PATCH 表示只修改提供的字段，其余字段保留。

演示维修人员的 ID 可以从 maintenance-records 返回的 maintained_by 获取，不要假定一定是 2。使用实际 ID 替换下方的 2：

```json
{
  "assigned_to": 2,
  "status": "in_progress"
}
```

之后可以提交：

```json
{
  "diagnosis": "检查发现接线松动，处理后恢复正常。",
  "status": "resolved"
}
```

这是学习演示填写的诊断，不是 AI 生成的结果。

最后提交 {"status":"closed"}。关闭后再修改标题会返回 409，说明业务规则拦截了修改。

状态流程：
- open → in_progress 或 cancelled。
- in_progress → resolved 或 cancelled。
- resolved → closed 或 in_progress（重新处理）。
- closed / cancelled 为终态，不再修改。
- 处理中及之后必须有处理人，解决或关闭必须有诊断。

如果直接从 open 跳到 closed，会返回 409。失败不会把同一请求里其他字段偷偷保存一半。

## 实验五：运行测试

新开一个 Terminal，执行：

```powershell
.\.venv\Scripts\python.exe -m pytest --mysql -q
```

应有 44 项通过。运行不带 --mysql 的命令时，真实数据库测试会跳过；不能把跳过当成验收完成。

测试库保留表结构，但每个测试的数据变更会回滚。测试不会清空你的开发库。自增 ID 在回滚后可能出现空号，这是正常现象，ID 不代表记录数量。

## 常见问题

- 503 database_unavailable：检查 MySQL 是否运行、.env 是否配置、迁移是否执行。
- 403 actor_unavailable：检查是否导入员工，以及 OPSMIND_DEMO_EMPLOYEE_NO 是否对应在职员工。
- 422 validation_error：检查请求字段、枚举值或分页参数；错误内容里的 location 指出字段位置。
- 修改 .env 后未生效：停止并重新启动服务；已创建的 Settings 不会自动重新加载。
- 终端显示 Starlette 弃用警告：是当前锁定测试依赖的上游提示，不是业务测试失败。

## 推荐阅读顺序

先亲手查询一次设备，然后阅读：
1. src/opsmind/main.py：服务在哪里创建。
2. src/opsmind/api/routes.py：URL 对应哪个函数。
3. src/opsmind/services/equipment.py：如何查询设备及处理不存在。
4. src/opsmind/db/models.py：Python 字段怎样对应表字段。
5. tests/integration/test_business_api.py：如何自动检查刚才手动做的操作。

不要同时背下所有文件。先能解释一条请求从输入到返回的路线，再学习工单事务和状态规则。
