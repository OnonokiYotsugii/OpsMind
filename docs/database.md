# 第一版数据库设计（P1 已实现）

P1 使用 MySQL 8 / InnoDB / utf8mb4，由 Alembic 0001 创建 equipment、employee、maintenance_record、ticket。后续 P3–P5 已增加 Agent、知识文档与检查点表，见下文。

P1 业务表约定：主键为 BIGINT 自增；时间为 DATETIME(6)，应用统一写入 UTC，展示时转换时区；created_at 由应用默认写入创建时间，updated_at 在更新时由持久化代码维护；直接 SQL 写入需显式提供这些时间。必填字段默认 NOT NULL，下面标明的字段可空。状态采用 VARCHAR 加 CHECK 约束，应用同步校验；取值在 ORM CHECK 约束及请求模型中固定，代码类与迁移文件分别维护，并通过 alembic check 验证结构。

## equipment

id；equipment_no VARCHAR(64) UNIQUE；name VARCHAR(128)；model VARCHAR(128)；manufacturer VARCHAR(128)；status VARCHAR(32)；location VARCHAR(255)；last_maintenance_at DATETIME(6) 可空；created_at；updated_at。

状态：active、maintenance、inactive。设备编号统一大小写规范，避免数据库排序规则造成不一致。

## employee

id；employee_no VARCHAR(64) UNIQUE；name VARCHAR(128)；department VARCHAR(128)；role VARCHAR(32)；status VARCHAR(32)；created_at。

角色：requester、technician、admin；状态：active、inactive。员工实体不等于认证账户，当前使用固定演示身份，尚未实现登录。

## maintenance_record

id；equipment_id BIGINT 外键；fault_description TEXT；maintenance_action TEXT；result TEXT；maintained_by BIGINT 外键关联 employee；maintenance_at DATETIME(6)；created_at。

索引：(equipment_id, maintenance_at, id)，支持稳定的时间倒序分页。同一事务内维护设备的 last_maintenance_at；补录旧记录不能把该时间回退。

## ticket

id；ticket_no VARCHAR(64) UNIQUE；equipment_id BIGINT 外键；title VARCHAR(200)；description TEXT；category VARCHAR(32)；priority VARCHAR(16)；status VARCHAR(32)；diagnosis TEXT 可空；created_by BIGINT 外键关联 employee；assigned_to BIGINT 外键关联 employee 可空；created_at；updated_at。

初始分类：electrical、mechanical、software、other。优先级：low、medium、high、urgent。状态：open、in_progress、resolved、closed、cancelled；状态迁移：open → in_progress/cancelled；in_progress → resolved/cancelled；resolved → closed/in_progress；closed/cancelled 不再修改。处理中及之后要求处理人，解决及关闭要求诊断。

索引：(equipment_id, created_at, id)。工单编号由程序生成并通过唯一约束防重，不能使用“查询数量加一”。避免以同名员工字符串作为关联键。

## knowledge_document（P4 实现，迁移 0003）

id VARCHAR(32) 主键；title VARCHAR(200)；document_type VARCHAR(32)；source VARCHAR(200)；version VARCHAR(32)；content_hash VARCHAR(64)；index_key VARCHAR(64)；status VARCHAR(16)；chunk_count INTEGER；created_at。

(source, version) 唯一约束。保存来源、内容哈希、索引版本和 indexing/ready 状态等元数据；片段正文、向量和关联信息保存在本机 Chroma。导入完成才标记 ready，查询仅选择兼容索引且 ready 的文档。同源同版本变更内容会拒绝，需新版本或对相同内容显式重建索引。

## 关系与删除

equipment 1:N maintenance_record；equipment 1:N ticket；employee 1:N 维修记录和创建/分配的工单。外键采用 RESTRICT，不级联删除设备历史。首版不提供删除接口；设备和员工通过状态停用。不为所有实体添加软删除字段。

已在真实 MySQL 上验证唯一键、外键、CHECK、事务回滚及分页，SQLite 不替代这些兼容性验证。标识符与状态字段使用 utf8mb4_bin，避免状态大小写被数据库忽略。数据库凭据使用专用应用账号，不使用 root 作为运行账号。

## P3 Agent 运行表（Alembic 0002）

agent_run：32 位随机 id 主键、actor_no、status、messages JSON、events JSON、
pending_action JSON 可空、result TEXT 可空、error_code、步骤/工具计数、
处理耗时与预算、expires_at、created_at、updated_at。

状态有 CHECK 约束。actor_no 保存发起运行的演示员工编号，并在访问/确认时校验。
同一行保存审批凭据，在 SELECT FOR UPDATE 行锁下检查和更新，和工单写入原子提交。
不保存密钥；messages 含用户任务和工具摘要，仅用于本地运行恢复，尚无自动保留期限。


## P5 graph_checkpoint（迁移 0004）

复合主键：(run_id, namespace, checkpoint_id)。run_id 外键关联 agent_run，删除受 RESTRICT 保护。
parent_id 记录父检查点，payload/meta 保存框架 typed serializer 的 Base64 JSON 封装，writes 保存节点部分结果，created_at 为 UTC。
完整快照和部分结果可能异步到达，未完成的占位快照不会被读取为可恢复状态。
agent_run 新增可空 graph_owner 与 graph_lease_until，旧行可直接读取。
检查点可能包含业务文本，仅内部访问；当前无自动清理策略。业务账号仍只需 SELECT/INSERT/UPDATE，迁移由专用账号执行。
