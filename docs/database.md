# 第一版数据库设计（P0 设计稿）

P1 使用 MySQL 8 / InnoDB / utf8mb4，由 Alembic 管理迁移。当前不创建表。

统一约定：主键为 BIGINT 自增；时间为 DATETIME(6)，应用统一写入 UTC，展示时转换时区；created_at 默认创建时间，updated_at 在更新时由持久化代码维护。必填字段默认 NOT NULL，下面标明的字段可空。状态采用 VARCHAR 加 CHECK 约束，应用同步校验；具体取值在 P1 测试中固定。

## equipment

id；equipment_no VARCHAR(64) UNIQUE；name VARCHAR(128)；model VARCHAR(128)；manufacturer VARCHAR(128)；status VARCHAR(32)；location VARCHAR(255)；last_maintenance_at DATETIME(6) 可空；created_at；updated_at。

状态：active、maintenance、inactive。设备编号统一大小写规范，避免数据库排序规则造成不一致。

## employee

id；employee_no VARCHAR(64) UNIQUE；name VARCHAR(128)；department VARCHAR(128)；role VARCHAR(32)；status VARCHAR(32)；created_at。

角色初稿：requester、technician、admin；状态：active、inactive。员工实体不等于认证账户，认证方案在 P1 明确。

## maintenance_record

id；equipment_id BIGINT 外键；fault_description TEXT；maintenance_action TEXT；result TEXT；maintained_by BIGINT 外键关联 employee；maintenance_at DATETIME(6)；created_at。

索引：(equipment_id, maintenance_at, id)，支持稳定的时间倒序分页。同一事务内维护设备的 last_maintenance_at；补录旧记录不能把该时间回退。

## ticket

id；ticket_no VARCHAR(64) UNIQUE；equipment_id BIGINT 外键；title VARCHAR(200)；description TEXT；category VARCHAR(32)；priority VARCHAR(16)；status VARCHAR(32)；diagnosis TEXT 可空；created_by BIGINT 外键关联 employee；assigned_to BIGINT 外键关联 employee 可空；created_at；updated_at。

初始分类：electrical、mechanical、software、other。优先级：low、medium、high、urgent。状态：open、in_progress、resolved、closed、cancelled；状态迁移规则在 P1 业务层明确并测试。

索引：(equipment_id, created_at, id)。工单编号由程序生成并通过唯一约束防重，不能使用“查询数量加一”。避免以同名员工字符串作为关联键。

## knowledge_document（P4 实现）

id；title VARCHAR(255)；document_type VARCHAR(32)；source VARCHAR(512)；version VARCHAR(64)；created_at。

只规划元数据。原文存储位置、文档去重、chunk ID、embedding 模型版本和向量关联在 P4 根据实际导入方案确定。

## 关系与删除

equipment 1:N maintenance_record；equipment 1:N ticket；employee 1:N 维修记录和创建/分配的工单。外键采用 RESTRICT，不级联删除设备历史。首版不提供删除接口；设备和员工通过状态停用。不为所有实体添加软删除字段。

P1 必须在真实 MySQL 上验证唯一键、外键、CHECK、事务回滚及分页，SQLite 不能替代这些兼容性验证。数据库凭据使用专用应用账号，不使用 root 作为运行账号。
