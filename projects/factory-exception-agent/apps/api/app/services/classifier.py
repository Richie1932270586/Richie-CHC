from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ClassificationResult:
    issue_type: str
    matched_keywords: list[str]
    sensitive_reasons: list[str]
    high_risk_keywords: list[str]


class IssueClassifier:
    DEFAULT_RULES: dict[str, list[str]] = {
        "高优先级停线风险": ["停线", "断料", "线边断供", "马上缺料", "紧急", "高优先级"],
        "短缺": ["短缺", "缺料", "不够", "不足", "缺件", "少料"],
        "错发": ["错发", "发错", "标签和实物不一致", "标签错贴", "标签错", "错料", "混料", "货不对板"],
        "不良品": ["不良品", "不良", "瑕疵", "破损", "损坏", "疑似不良"],
        "批次异常": ["批次异常", "批次", "批号", "同批次", "lot", "批次混用"],
        "库位异常": ["库位异常", "库位", "货位", "放错位", "找不到", "库位不一致"],
    }

    def __init__(self, policy_config: dict) -> None:
        self.policy_config = policy_config

    def classify(self, message: str) -> ClassificationResult:
        matched: dict[str, list[str]] = {}
        for issue_type, keywords in self.DEFAULT_RULES.items():
            for keyword in keywords:
                if keyword.lower() in message.lower():
                    matched.setdefault(issue_type, []).append(keyword)

        issue_type = "一般异常咨询"
        if matched:
            issue_type = max(matched.items(), key=lambda item: len(item[1]))[0]
        if "停线" in message and issue_type != "高优先级停线风险":
            issue_type = "高优先级停线风险"

        confirm_keywords = self.policy_config.get(
            "confirm_keywords",
            ["报废", "停线", "责任", "归属", "外部", "供应商", "客户"],
        )
        sensitive_reasons = [keyword for keyword in confirm_keywords if keyword in message]

        high_risk_keywords = self.policy_config.get(
            "high_risk_keywords",
            ["停线", "线边断供", "紧急", "2小时内"],
        )
        matched_risk = [keyword for keyword in high_risk_keywords if keyword in message]

        return ClassificationResult(
            issue_type=issue_type,
            matched_keywords=matched.get(issue_type, []),
            sensitive_reasons=sensitive_reasons,
            high_risk_keywords=matched_risk,
        )
