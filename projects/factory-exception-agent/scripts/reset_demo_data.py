from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "apps" / "api"))

from app.core.config import get_settings  # noqa: E402
from app.services.retriever import build_kb_index  # noqa: E402


KB_DOCS = {
    "SOP-shortage-handling.md": """# SOP｜短缺异常处理

适用场景：产线反馈线边物料不足，或仓内余量无法覆盖当前班次需求。

处理原则：
1. 先确认是否为真实短缺，核对系统库存、线边在制和暂存区。
2. 若 2 小时内可能影响上料，按照停线风险预警流程升级班组长。
3. 若存在替代料，必须由工艺或质量确认后才能切换。

标准动作：
- 查询当前批次和库位余量。
- 标记异常批次，避免重复发料。
- 生成补料/调拨工单草稿，并保留处理记录。

风险提醒：
- 不得仅凭口头反馈判定仓内无料。
- 未经确认不得跨批次混用。
""",
    "SOP-misdelivery-handling.md": """# SOP｜错发与标签不一致处理

适用场景：收货、发料或线边领料时，发现标签与实物不一致、错箱或混料。

处理原则：
1. 先冻结可疑箱件，避免继续流转。
2. 对照标签、物料编码、批次号和收发记录复核。
3. 涉及责任判定时，只能输出责任确认草稿，不能自动归责。

标准动作：
- 查询历史同类事件。
- 通知仓储专员和班组长现场复核。
- 生成责任确认草稿与处理记录草稿。
""",
    "SOP-defect-isolation.md": """# SOP｜不良品隔离与复判

适用场景：来料、库存或线边发现疑似不良品、破损件、功能异常件。

处理原则：
1. 先隔离，不直接退库或报废。
2. 同批次出现多件异常时，扩大抽检范围。
3. 报废、批量退货和外部通知均需人工确认。

标准动作：
- 隔离疑似不良品并贴状态标识。
- 通知质检复判。
- 生成升级通知草稿和处理记录草稿。
""",
    "RULE-batch-abnormal.md": """# 规则｜批次异常与批次混用

判定条件：
- 同一容器内出现两个以上批次。
- 实物批次与系统批次不一致。
- 同批次重复出现来料异常或功能不良。

处理规则：
1. 暂停该批次继续流转。
2. 查询历史异常台账，确认是否重复发生。
3. 若同批次连续两次以上异常，建议升级质检和仓储主管。
""",
    "RULE-location-exception.md": """# 规则｜库位异常处理

适用场景：系统库位与实物库位不一致、找不到物料、漏扫导致账实不符。

处理规则：
1. 先核对最近一次移库或发料记录。
2. 禁止在未确认前直接修改系统库位。
3. 若涉及责任归属，先生成责任确认草稿，再由现场主管确认。
""",
    "REG-stopline-escalation.md": """# 规定｜停线风险升级规则

以下情况视为高优先级停线风险：
- 关键物料余量低于安全库存，且 2 小时内无补料路径。
- 线边已出现断供或产线明确反馈即将停线。
- 涉及质量封锁，且无替代批次可切换。

升级要求：
1. 立即生成升级通知草稿。
2. 必须人工确认后，才能触发对班组长、质检或外部的正式通知。
3. 升级记录必须保留时间、原因、责任部门建议。
""",
    "FAQ-return-or-scrap.md": """# FAQ｜隔离、退库、报废怎么区分

常见问答：
- 疑似不良品先做什么？
  先隔离和复判，不直接退库或报废。

- 什么时候能报废？
  只有在质检结论明确且主管确认后，才能走报废流程。

- 能否直接通知供应商？
  对外通知属于敏感动作，只能先生成通知草稿，等待人工确认。
""",
    "WORKINSTR-ticket-recording.md": """# 作业说明｜工单与处理记录填写要求

处理记录至少包含：
- 发现时间
- 异常类型
- 物料编码/名称
- 批次号
- 当前库存或影响范围
- 临时处置
- 是否升级
- 责任部门建议

填写要求：
1. 事实描述与判断结论分开写。
2. 不要在未确认前写死责任归属。
3. 对外通知和报废必须标记“待人工确认”。
""",
    "FAQ-label-mismatch.md": """# FAQ｜标签和实物不一致是否要升级

如果只发现单箱标签与实物不一致，先冻结该箱并复核收货记录。
如果同一批次或同一供应商连续出现两次以上标签不一致，建议升级仓储主管和质检协同。
若问题已经影响线边备料，按停线风险规则处理。
""",
}


INVENTORY_ROWS = [
    ["item_code", "item_name", "batch_no", "location", "on_hand_qty", "safety_stock", "status"],
    ["LX-100", "零件X", "B202603", "A-01-03", "18", "20", "紧张"],
    ["SY-220", "传感器Y", "B202604", "B-02-01", "85", "40", "正常"],
    ["TZ-310", "托盘Z", "B202602", "C-01-02", "12", "15", "紧张"],
    ["LB-120", "标签盒K", "B202605", "A-03-04", "160", "50", "正常"],
    ["CM-888", "轴承M", "B202601", "D-02-01", "48", "30", "正常"],
    ["WH-500", "外壳P", "B202603", "E-01-01", "5", "18", "紧张"],
]


INCIDENT_ROWS = [
    ["incident_id", "date", "issue_type", "item_code", "batch_no", "severity", "summary", "disposition"],
    ["INC-001", "2026-03-18", "短缺", "LX-100", "B202603", "high", "零件X 批次 B202603 余量不足，产线 A 请求紧急补料", "已补料"],
    ["INC-002", "2026-03-16", "错发", "LB-120", "B202605", "medium", "标签盒K 标签与实物不一致，冻结一箱待复核", "已复核"],
    ["INC-003", "2026-03-14", "不良品", "SY-220", "B202604", "high", "传感器Y 批次 B202604 出现来料不良，质检复判中", "隔离中"],
    ["INC-004", "2026-03-11", "批次异常", "WH-500", "B202603", "high", "外壳P 同批次出现混批记录，暂停流转", "已升级"],
    ["INC-005", "2026-03-09", "库位异常", "CM-888", "B202601", "medium", "轴承M 系统库位与实物不符，待核对移库记录", "处理中"],
    ["INC-006", "2026-03-05", "不良品", "SY-220", "B202604", "medium", "传感器Y 二次发现功能异常，扩大抽检", "已复判"],
    ["INC-007", "2026-03-02", "批次异常", "WH-500", "B202603", "high", "外壳P 批次 B202603 重复异常，建议升级质检", "已升级"],
]


OWNER_ROWS = [
    ["issue_type", "department", "owner_name", "backup_owner", "escalation_contact"],
    ["短缺", "仓储运营", "李晨", "赵敏", "warehouse_lead@factory.demo"],
    ["错发", "仓储运营", "王磊", "周倩", "warehouse_lead@factory.demo"],
    ["不良品", "质量管理", "陈洁", "高远", "quality_mgr@factory.demo"],
    ["批次异常", "质量管理", "陈洁", "高远", "quality_mgr@factory.demo"],
    ["库位异常", "仓储运营", "王磊", "周倩", "warehouse_lead@factory.demo"],
    ["高优先级停线风险", "生产协同", "刘峰", "孙涛", "line_lead@factory.demo"],
]


TICKET_TEMPLATES = {
    "ticket_draft": {
        "subject_prefix": "异常工单草稿",
        "description": "生成内部异常工单草稿，用于后续录入系统。",
        "body_hint": "补充异常发生时间、影响范围和临时处置，再录入企业系统。",
    },
    "handling_record": {
        "subject_prefix": "处理记录草稿",
        "description": "生成内部处理记录，便于复盘与追踪。",
        "body_hint": "按事实、判断、动作三个部分填写，避免先写死责任归属。",
    },
    "quality_escalation": {
        "subject_prefix": "质检升级通知草稿",
        "description": "生成给质检/班组长的升级通知草稿，不直接发送。",
        "body_hint": "说明是否影响上线、是否需要扩大抽检，并标记待人工确认。",
    },
    "owner_assignment": {
        "subject_prefix": "责任确认草稿",
        "description": "生成责任部门确认草稿，避免自动归责。",
        "body_hint": "先写事实，再写待确认的责任部门建议，不直接定责。",
    },
    "external_notification": {
        "subject_prefix": "对外通知草稿",
        "description": "生成供应商/外部协同通知草稿，必须人工确认后使用。",
        "body_hint": "只输出可编辑草稿，外发前由负责人确认内容与口径。",
    },
}


EVAL_CASES = [
    {
        "id": "eval-01",
        "question": "产线 A 反馈零件X 短缺，当前批次 B202603，应该怎么处理？",
        "expected_issue_type": "短缺",
        "expect_confirmation": False,
        "required_tools": ["inventory_lookup"],
        "overrides": {},
    },
    {
        "id": "eval-02",
        "question": "收货时发现一箱标签和实物不一致，是否需要升级？",
        "expected_issue_type": "错发",
        "expect_confirmation": False,
        "required_tools": ["incident_lookup"],
        "overrides": {},
    },
    {
        "id": "eval-03",
        "question": "有一批传感器Y 疑似不良品，先做隔离还是直接退库？",
        "expected_issue_type": "不良品",
        "expect_confirmation": False,
        "required_tools": ["incident_lookup"],
        "overrides": {},
    },
    {
        "id": "eval-04",
        "question": "外壳P 批次 B202603 重复异常，是否需要升级质检？",
        "expected_issue_type": "批次异常",
        "expect_confirmation": False,
        "required_tools": ["incident_lookup", "owner_lookup"],
        "overrides": {},
    },
    {
        "id": "eval-05",
        "question": "系统显示轴承M 在 D-02-01，但现场找不到，算库位异常吗？",
        "expected_issue_type": "库位异常",
        "expect_confirmation": False,
        "required_tools": ["owner_lookup"],
        "overrides": {},
    },
    {
        "id": "eval-06",
        "question": "零件X 余量不够，2 小时内可能停线，要不要马上升级？",
        "expected_issue_type": "高优先级停线风险",
        "expect_confirmation": True,
        "required_tools": ["inventory_lookup", "owner_lookup"],
        "overrides": {},
    },
    {
        "id": "eval-07",
        "question": "这批疑似不良品如果要报废，需要直接走报废流程吗？",
        "expected_issue_type": "不良品",
        "expect_confirmation": True,
        "required_tools": [],
        "overrides": {},
    },
    {
        "id": "eval-08",
        "question": "需要通知供应商这次标签错贴问题吗？",
        "expected_issue_type": "错发",
        "expect_confirmation": True,
        "required_tools": [],
        "overrides": {},
    },
    {
        "id": "eval-09",
        "question": "如果只保留 tools，不开 RAG，零件X 短缺怎么处理？",
        "expected_issue_type": "短缺",
        "expect_confirmation": False,
        "required_tools": ["inventory_lookup"],
        "overrides": {"agent_mode": "only-tool", "rag_enabled": False},
    },
    {
        "id": "eval-10",
        "question": "标签和实物不一致，但没有具体物料号，先做什么？",
        "expected_issue_type": "错发",
        "expect_confirmation": False,
        "required_tools": [],
        "overrides": {},
    },
    {
        "id": "eval-11",
        "question": "高优先级停线风险场景里，可以自动通知班组长吗？",
        "expected_issue_type": "高优先级停线风险",
        "expect_confirmation": True,
        "required_tools": [],
        "overrides": {},
    },
    {
        "id": "eval-12",
        "question": "外壳P 批次 B202603 在 full-RAG 下应该参考哪些规则？",
        "expected_issue_type": "批次异常",
        "expect_confirmation": False,
        "required_tools": ["incident_lookup"],
        "overrides": {"rag_profile": "full"},
    },
]


def write_csv(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerows(rows)


def main() -> None:
    settings = get_settings()
    settings.kb_dir.mkdir(parents=True, exist_ok=True)
    settings.inventory_file.parent.mkdir(parents=True, exist_ok=True)
    settings.eval_cases_file.parent.mkdir(parents=True, exist_ok=True)

    for filename, content in KB_DOCS.items():
        (settings.kb_dir / filename).write_text(content.strip() + "\n", encoding="utf-8")

    write_csv(settings.inventory_file, INVENTORY_ROWS)
    write_csv(settings.incidents_file, INCIDENT_ROWS)
    write_csv(settings.owners_file, OWNER_ROWS)
    settings.ticket_templates_file.write_text(
        json.dumps(TICKET_TEMPLATES, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    settings.eval_cases_file.write_text(
        json.dumps(EVAL_CASES, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    index_payload = build_kb_index(settings)
    print(f"Demo data reset complete. KB docs: {len(KB_DOCS)}")
    print(f"Index rebuilt: {settings.index_file}")
    print(f"Indexed chunks: {len(index_payload.get('chunks', []))}")


if __name__ == "__main__":
    main()
