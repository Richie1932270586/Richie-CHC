from __future__ import annotations

from uuid import uuid4


class DraftBuilder:
    def __init__(self, policy_config: dict) -> None:
        self.policy_config = policy_config

    def _is_sensitive(self, action_type: str, issue_type: str, message: str) -> tuple[bool, str | None]:
        confirm_keywords = self.policy_config.get(
            "confirm_keywords",
            ["报废", "停线", "责任", "归属", "供应商", "客户", "对外"],
        )
        reasons = [keyword for keyword in confirm_keywords if keyword in message]
        if action_type == "quality_escalation" and issue_type == "高优先级停线风险":
            reasons.append("停线风险升级")
        if action_type == "owner_assignment" and issue_type in {"错发", "库位异常"}:
            reasons.append("责任归属判断")
        if action_type == "external_notification":
            reasons.append("对外通知")
        if "报废" in message:
            reasons.append("涉及报废")
        unique_reasons = list(dict.fromkeys(reasons))
        if unique_reasons:
            return True, "、".join(unique_reasons)
        return False, None

    def build_actions(
        self,
        issue_type: str,
        risk_level: str,
        message: str,
        inventory_rows: list[dict],
        incident_rows: list[dict],
        owner_rows: list[dict],
        templates: dict[str, dict],
    ) -> list[dict]:
        actions: list[dict] = []
        owner_info = owner_rows[0] if owner_rows else {}
        inventory_info = inventory_rows[0] if inventory_rows else {}
        incident_info = incident_rows[0] if incident_rows else {}

        action_plan = [
            ("ticket_draft", "生成工单草稿"),
            ("handling_record", "生成处理记录草稿"),
        ]
        if issue_type in {"不良品", "批次异常", "高优先级停线风险"}:
            action_plan.append(("quality_escalation", "生成升级通知草稿"))
        owner_keywords = ["责任", "归属", "谁负责", "责任人", "责任部门"]
        if issue_type in {"错发", "库位异常"} and any(keyword in message for keyword in owner_keywords):
            action_plan.append(("owner_assignment", "生成责任确认草稿"))
        if any(keyword in message for keyword in ["供应商", "客户", "对外"]):
            action_plan.append(("external_notification", "生成对外通知草稿"))

        for action_type, title in action_plan:
            template = templates.get(action_type, {})
            sensitive, reason = self._is_sensitive(action_type, issue_type, message)
            draft_text = "\n".join(
                [
                    f"主题：{template.get('subject_prefix', title)}",
                    f"异常类型：{issue_type}",
                    f"风险等级：{risk_level}",
                    f"当前描述：{message}",
                    f"库存参考：{inventory_info.get('item_name', '无匹配')} / 余量 {inventory_info.get('on_hand_qty', '-')}",
                    f"历史异常参考：{incident_info.get('summary', '暂无历史匹配')}",
                    f"责任部门建议：{owner_info.get('department', '待确认')} / {owner_info.get('owner_name', '待确认')}",
                    f"建议正文：{template.get('body_hint', '请根据当前异常补充业务细节后再提交。')}",
                ]
            )
            actions.append(
                {
                    "action_id": uuid4().hex[:8],
                    "action_type": action_type,
                    "title": title,
                    "description": template.get("description", "生成可编辑草稿，不直接发送。"),
                    "draft": draft_text,
                    "sensitive": sensitive,
                    "requires_confirmation": sensitive,
                    "confirmation_reason": reason,
                    "status": "draft",
                }
            )
        return actions
