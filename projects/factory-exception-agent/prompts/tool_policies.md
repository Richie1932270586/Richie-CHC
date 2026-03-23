# Tool Policies

```json
{
  "confirm_keywords": ["报废", "停线", "责任", "归属", "供应商", "客户", "对外"],
  "high_risk_keywords": ["停线", "线边断供", "紧急", "2小时内", "高优先级"],
  "always_consider_tools_for": ["短缺", "错发", "不良品", "批次异常", "库位异常", "高优先级停线风险"],
  "sensitive_action_types": ["quality_escalation", "owner_assignment", "external_notification"]
}
```

策略说明：
- 识别到业务异常时，优先考虑检索知识库与查表，不要只给空泛建议。
- 如果用户只是问概念性问题，可先直接回答，再提示是否需要生成草稿。
- 敏感动作只生成草稿，不做真实发送。
- 如果 evidence 为空，仍可用 tables + 规则做保守回答，但要显式提醒“建议复核”。
