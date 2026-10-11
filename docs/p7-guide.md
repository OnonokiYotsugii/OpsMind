# P7：启动与演示教程

这一阶段把已有 API 接到中文页面，并提供容器启动配置。前端是 HTML/CSS/JavaScript，由 FastAPI 直接提供，不需要 npm 启动前端。

## 先用现有本机环境

MySQL 保持启动。在 PyCharm 终端进入 `D:\project\OpsMind`，如果旧后端正在运行，按 Ctrl+C 停止后重新启动：

```powershell
.\.venv\Scripts\python.exe -m uvicorn opsmind.main:create_app --factory --host 127.0.0.1 --port 8000
```

打开 [工作台](http://127.0.0.1:8000/)。以前根路径返回 Not Found，现在会显示页面。[Swagger](http://127.0.0.1:8000/docs) 仍可使用。也可运行 `powershell -File scripts/start_local.ps1` 启动。

首页“后端在线”只说明进程可访问，不代表数据库、知识库和模型都可用。选择示例只填入文字，点击“开始处理”才调用模型并消耗额度。模型返回实际写操作时，页面显示参数与有效期，需要再点“确认执行”。

页面提供运行编号查询、刷新状态和恢复执行。运行编号仅保存在当前浏览器会话，完整状态保存在 MySQL。查询和刷新不调用模型；恢复可能调用。执行结果按普通文本呈现，引用来源显示在结果下方，Trace 可展开查看。

如果请求连接中断，不要立即重复提交创建任务。服务器可能仍在运行；已有运行编号时先查询。当前创建接口直到执行返回才提供编号，因此首次请求在收到编号前中断，页面无法自动找回该次任务，这是现阶段限制。

## Docker 是什么

Docker 把程序与运行环境打包。Compose 描述多个服务怎样一起启动。本项目包含：

- db：独立 MySQL 数据库 `opsmind_demo`，不映射主机端口。
- init：等待数据库就绪，执行表迁移和幂等演示数据导入，成功后退出。
- app：使用受限应用账号启动后端和页面，只映射主机 127.0.0.1:8000。

MySQL、向量索引、Embedding 缓存分别使用持久卷。容器里的 0.0.0.0 用于容器网络，主机侧仍只监听回环地址。本机原来的 opsmind_dev 不受影响。

## 在安装 Docker Desktop 后运行

本轮机器未找到 Docker 命令，以下流程尚未实际构建启动验收。应先准备 Docker Desktop 的 Linux 容器环境，执行 `docker version` 和 `docker compose version` 确认可用。Docker 安装参考 [官方 Windows 文档](https://docs.docker.com/desktop/setup/install/windows-install/)。

在项目根目录执行：

```powershell
# 仅第一次：生成容器专用密码，读取现有模型配置，不会打印密钥或覆盖 .env
.\.venv\Scripts\python.exe scripts/setup_docker.py
# 构建镜像并启动；本机旧后端若占用 8000，先 Ctrl+C 停止
 docker compose up --build -d
 docker compose ps -a
 docker compose logs --tail 80 init app
```

生成文件放在被 Git 忽略的 `.data/docker/`。应用配置不包含迁移密码；root 密码只交给数据库容器。密钥仍是本地明文文件，不能上传或分享这些文件。脚本拒绝覆盖已有配置；不要为了重试随意删配置，它与数据库持久卷的密码对应。更换模型密钥时编辑 `.data/docker/app.env` 的对应值，再重新创建 app 容器。

第一轮镜像构建会下载基础镜像和 Python 依赖；知识模型需要单独准备。之后打开首页即可检查页面。RAG 演示前再运行：

```powershell
docker compose exec app python scripts/knowledge.py prepare
docker compose exec app python scripts/knowledge.py import knowledge/demo-power.md --title "演示供电设备手册" --source demo-power --version 1.0
docker compose exec app python scripts/knowledge.py import knowledge/demo-process.md --title "演示维修流程" --source demo-process --version 1.0
```

prepare 下载本地 Embedding 模型，不调用 DeepSeek。资料导入后才可完成带知识库的任务。首次下载可能需要较长时间。

停止：`docker compose down`，保留命名数据卷。后续启动：`docker compose up -d`。不要添加 `-v`，那会删除命名卷数据。迁移和种子导入可重复执行，但不会覆盖已修改的演示记录。

Compose 的健康依赖及一次性初始化顺序参照 [Docker 官方启动顺序说明](https://docs.docker.com/compose/how-tos/startup-order/)，构建采用 [uv 官方容器工作流](https://docs.astral.sh/uv/guides/integration/docker/) 的锁文件安装方式。基础镜像使用版本标签，尚未固定 digest。

## 面试演示顺序

1. 展示页面与架构图，解释设备数据、知识资料和模型各自负责什么。
2. 查询 EQ-10023 的设备与维修记录，展示只读工具调用。
3. 用 E102 示例查看检索来源和执行记录。
4. 请求创建工单，先停在待确认状态，解释为什么不能由模型直接写库。
5. 拒绝一次，再发起另一个任务确认一次，查询实际工单结果。
6. 展示 P6 的评测报告，明确脚本回归与真实模型效果的区别。

第 2–5 步会调用真实模型，留待你统一验收时进行。这轮截图只展示真实页面初始状态，浏览器交互测试使用受控响应，不是模型成功演示录像。

## 验证命令

```powershell
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
.\.venv\Scripts\python.exe -m pytest --mysql --embedding -q
.\.venv\Scripts\python.exe scripts/evaluate.py
```

浏览器回归脚本是 `tests/browser/workspace.cjs`，需要可用的 Playwright Node 模块与 Chrome；它不属于项目运行依赖。指定 NODE_PATH 为你自己的 Playwright 安装目录，CHROME_PATH 为浏览器路径，OPSMIND_WEB_URL 为验证服务 URL，再运行 `node tests/browser/workspace.cjs`。脚本拦截 Agent 接口返回测试数据，仅证明页面交互，业务正确性仍由 MySQL 集成测试验证。

当前没有正式登录、生产权限管理或公网部署。不要将该演示直接对外发布。GitHub 展示准备见 [展示说明](showcase.md)。
