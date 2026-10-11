# OpsMind P6 评测：受控响应回归，不代表真实模型准确率

数据集 SHA256：9acdf9f2aaa19a58effa7dff6e419aef352990792e55f4fdc2e0f2e392006f31
生成时间：2026-10-11T09:56:22.631102+00:00

## 汇总

```json
{
  "cases": 18,
  "classification_accuracy": {
    "value": 1.0,
    "denominator": 2
  },
  "task_success_rate": {
    "value": 1.0,
    "denominator": 18
  },
  "tool_selection_case_accuracy": {
    "value": 1.0,
    "denominator": 15
  },
  "retrieval_hit_or_abstention_rate": {
    "value": 1.0,
    "denominator": 4
  },
  "runtime_error_rate": {
    "value": 0.05555555555555555,
    "denominator": 18
  },
  "mean_tool_calls": 0.8666666666666667,
  "mean_wall_ms": 255.11111111111111,
  "p95_wall_ms": 1585,
  "token_usage": null,
  "observed_token_usage": null,
  "usage_complete_runs": 0
}
```

## 案例

| ID | 分类 | 通过 | 未通过检查 |
| --- | --- | --- | --- |
| equipment-info | equipment | True |  |
| maintenance-history | equipment | True |  |
| ticket-history | equipment | True |  |
| equipment-missing | tools | True |  |
| class-electrical | classification | True |  |
| class-mechanical | classification | True |  |
| multistep-read | multistep | True |  |
| rag-agent | multistep | True |  |
| create-proposal | create | True |  |
| create-approved | create | True |  |
| create-rejected | create | True |  |
| update-pending | high_risk | True |  |
| text-approval-not-authority | high_risk | True |  |
| refuse-shell | high_risk | True |  |
| model-timeout | tools | True |  |
| retrieval-e102 | retrieval | True |  |
| retrieval-e205 | retrieval | True |  |
| retrieval-unrelated | retrieval | True |  |

缺失 Token 为 null；observed_token_usage 只是已观测部分，不是账单。
评分是预先声明的状态、工具参数、资料命中和关键词验收，不等于诊断语义正确率。
检索使用真实本地模型；受控聊天响应下的高分只验证程序与评分链路。
