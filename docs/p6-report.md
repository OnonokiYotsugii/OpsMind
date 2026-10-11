# P6 阶段报告

## Completed

完成 18 题、7 类场景的版本化评测集，隔离测试库执行器、确定性评分、JSON/Markdown 报告，以及按运行查询的安全 Trace 接口。区分脚本回归和真实模型评测；本轮未调用付费模型。

## Files Changed

新增 evaluation 数据集、evaluation/ 评测模块、observability/ Trace 模块、llm/telemetry.py、scripts/evaluate.py、评分器单测与 Trace 集成测试、教程和本报告。调整模型客户端、Agent 节点/事务事件、审批计时及 API。P6 不增加依赖或数据库迁移，沿用 P5 的 0004。

## Architecture

模型客户端只提取经过校验的供应商用量。节点记录调用起止，业务事务记录工具结果和检索来源；Trace 通过字段白名单输出。评测使用独立本机 opsmind_test，每题外层事务回滚，审批必须与预设工具参数匹配，检查实际工单变化与成功凭据。

## Verification

2026-10-11：Ruff 检查与格式检查通过；包含 MySQL 和本地 Embedding 的自动测试 208 项通过，数据库模型无新增迁移差异。P6 相比 P5 新增 29 项测试，覆盖评分失败条件、用量缺失、访问控制、重复审批和图重放统计。

本地 scripted 评测 18/18 通过，分类 2/2、工具选择案例 15/15、检索命中或正确空返回 4/4。平均工具调用 0.8667 次；本次平均每题 255.11 ms、p95 1585 ms。Token 未知，不伪造。运行错误 1/18 来自预设超时题，该题正确处理错误，因此验收通过。

可追溯基线见 [完整脚本评测报告](evaluation/p6-scripted-baseline.md)。本机 JSON 详细结果保存在 `.data/evaluation-reports/eb7c096e28034c83ba2d17ff74bf46db/results.json`。

## Problems

18 题只是小型回归集；脚本响应通过不代表 DeepSeek 准确率。关键词和来源编号不能验证完整语义。Token 是可观测用量而非账单；进程异常中断可能留下不完整事件。现有依赖产生 AnyIO 弃用和 FastEmbed 池化提示，未造成测试失败。保留本机演示身份限制。

## Next Step

P6 在此暂停。P7 可进行部署和展示；手动接口验收、真实模型效果及付费调用留待后续统一验证。
