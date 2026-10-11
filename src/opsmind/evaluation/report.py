import json
from pathlib import Path


def save_report(report: dict, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    label = "受控响应回归，不代表真实模型准确率" if report["mode"] == "scripted" else "真实模型评测"
    lines = [
        f"# OpsMind P6 评测：{label}",
        "",
        f"数据集 SHA256：{report['dataset_sha256']}",
        f"生成时间：{report['created_at']}",
        "",
        "## 汇总",
        "",
        "```json",
        json.dumps(report["summary"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## 案例",
        "",
        "| ID | 分类 | 通过 | 未通过检查 |",
        "| --- | --- | --- | --- |",
    ]
    for row in report["results"]:
        failures = ", ".join(k for k, v in row["checks"].items() if not v)
        lines.append(f"| {row['id']} | {row['category']} | {row['passed']} | {failures} |")
    lines += [
        "",
        "缺失 Token 为 null；observed_token_usage 只是已观测部分，不是账单。",
        "评分是预先声明的状态、工具参数、资料命中和关键词验收，不等于诊断语义正确率。",
        "检索使用真实本地模型；受控聊天响应下的高分只验证程序与评分链路。",
    ]
    (directory / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
