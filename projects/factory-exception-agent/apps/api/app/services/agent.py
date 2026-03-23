from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.services.classifier import ClassificationResult, IssueClassifier
from app.services.drafts import DraftBuilder
from app.services.llm_client import LLMClient
from app.services.prompt_loader import PromptLoader
from app.services.retriever import Retriever
from app.services.tables import TableService
from app.services.text_utils import cosine_similarity, softmax, to_semantic_counter


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RuntimeConfig:
    rag_enabled: bool
    rag_profile: str
    agent_mode: str
    top_k: int


@dataclass(slots=True)
class HistoryContext:
    last_user_message: str = ""
    last_assistant_message: str = ""
    last_assistant_meta: dict[str, Any] | None = None
    active_doc_title: str = ""
    active_doc_path: str = ""
    conversation_mode: str = ""
    step_cursor: int = 0
    total_steps: int = 0


class FactoryExceptionAgent:
    ISSUE_SCENARIO_KEYWORDS = {
        "短缺",
        "缺料",
        "停线",
        "报废",
        "升级",
        "责任",
        "库存",
        "余量",
        "供应商",
        "客户",
        "找不到",
        "不一致",
        "放错位",
        "库位异常",
        "异常台账",
        "错发",
        "不良品",
        "批次异常",
    }
    SOP_GUIDANCE_KEYWORDS = {
        "SOP",
        "指导",
        "步骤",
        "怎么做",
        "如何",
        "作业",
        "流程",
        "入库",
        "收货",
        "返修",
        "上架",
        "下架",
        "配送",
    }
    SOP_FOLLOW_UP_KEYWORDS = {
        "为什么",
        "原因",
        "目的",
        "注意",
        "要点",
        "重点",
        "PDA",
        "标签",
        "库位",
        "扫码",
        "下一步",
        "确认什么",
        "然后",
        "继续",
        "什么意思",
        "怎么理解",
        "需要看什么",
        "看什么",
        "还需要看",
    }
    BUSINESS_CONTEXT_KEYWORDS = ISSUE_SCENARIO_KEYWORDS | SOP_GUIDANCE_KEYWORDS | {
        "厂内物流",
        "仓储",
        "质检",
        "物流",
        "物料",
        "线边",
        "补料",
        "工单",
        "库存",
        "台账",
        "供应商",
        "批号",
        "来料",
        "隔离",
    }
    ISSUE_DEFAULT_STEPS: dict[str, list[str]] = {
        "短缺": ["先确认当前批次和线边剩余量。", "核对替代料或紧急补料路径。", "保留处理记录并跟踪恢复时间。"],
        "错发": ["先冻结可疑箱件，避免继续上料。", "核对标签、实物和收货记录。", "通知仓储和班组长复核责任归属。"],
        "不良品": ["先隔离疑似不良品。", "保留样本并通知质检复判。", "在确认前不要直接退库或报废。"],
        "批次异常": ["暂停该批次继续流转。", "核对批次、标签和来料记录。", "同步质检确认是否扩大影响范围。"],
        "库位异常": ["先确认系统库位和实物库位。", "现场复核是否存在错放或漏扫。", "补充库位调整记录。"],
        "高优先级停线风险": ["先确认停线风险时间窗。", "立即锁定应急补料/替代料方案。", "同步班组长和质检，保留升级草稿等待人工确认。"],
    }

    def __init__(
        self,
        settings: Settings,
        retriever: Retriever,
        table_service: TableService,
        prompt_loader: PromptLoader,
        llm_client: LLMClient,
    ) -> None:
        self.settings = settings
        self.retriever = retriever
        self.table_service = table_service
        self.prompt_loader = prompt_loader
        self.llm_client = llm_client

    def _build_history_context(self, history: list[dict[str, Any]]) -> HistoryContext:
        context = HistoryContext()
        for item in reversed(history):
            role = item.get("role")
            content = item.get("content", "").strip()
            if role == "assistant" and not context.last_assistant_message:
                meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
                trace = meta.get("trace", {}) if isinstance(meta.get("trace"), dict) else {}
                context.last_assistant_message = content
                context.last_assistant_meta = meta
                context.active_doc_title = (
                    trace.get("primary_doc_title")
                    or meta.get("primary_doc_title")
                    or ""
                )
                context.active_doc_path = (
                    trace.get("primary_doc_path")
                    or meta.get("primary_doc_path")
                    or ""
                )
                context.conversation_mode = (
                    trace.get("conversation_mode")
                    or meta.get("conversation_mode")
                    or ""
                )
                context.step_cursor = int(
                    trace.get("step_cursor")
                    or meta.get("step_cursor")
                    or 0
                )
                context.total_steps = int(
                    trace.get("total_steps")
                    or meta.get("total_steps")
                    or 0
                )
            if role == "user" and content and not context.last_user_message:
                context.last_user_message = content
            if context.last_user_message and context.last_assistant_message:
                break
        return context

    def _looks_like_follow_up(self, message: str) -> bool:
        follow_up_keywords = [
            "然后",
            "接下来",
            "下一步",
            "后面",
            "继续",
            "再然后",
            "之后",
            "为什么",
            "原因",
            "目的",
            "注意什么",
            "注意",
            "要点",
            "重点",
            "还要",
            "怎么扫",
            "如果",
            "那",
            "PDA",
            "标签",
            "库位",
            "扫码",
            "确认什么",
        ]
        stripped = message.strip()
        return any(keyword in stripped for keyword in follow_up_keywords)

    def _resolve_query_text(self, request, history_context: HistoryContext) -> str:
        message = request.message.strip()
        if not request.history:
            return message
        if not self._looks_like_follow_up(message):
            return message
        anchors = [
            history_context.active_doc_title,
            history_context.last_user_message,
        ]
        anchors = [item for item in anchors if item and item != message]
        if not anchors:
            return message
        return " ".join(dict.fromkeys([*anchors, message]))

    def _casual_intent(self, message: str) -> str | None:
        stripped = message.strip()
        lowered = stripped.lower()
        if lowered in {"hi", "hello", "hey"} or stripped in {"你好", "您好", "在吗", "嗨", "早上好", "下午好", "晚上好"}:
            return "greeting"
        if any(keyword in stripped for keyword in ["什么模型", "使用什么模型", "现在在使用什么模型", "qwen", "千问", "ollama", "模型吗", "是不是qwen", "是不是千问"]):
            return "model_info"
        if any(keyword in stripped for keyword in ["你是谁", "你能做什么", "你可以做什么", "可以做什么", "能帮我做什么", "怎么用", "帮助", "help", "介绍一下"]):
            return "capability"
        if any(keyword in stripped for keyword in ["谢谢", "感谢", "收到", "明白了", "好的", "ok", "OK"]):
            return "acknowledge"
        if len(stripped) <= 12 and not re.search(r"[\dA-Za-z_-]{3,}", stripped) and stripped.endswith(("吗", "么", "?", "？")):
            return "smalltalk"
        return None

    def _looks_like_sop_question(self, message: str) -> bool:
        return any(keyword in message for keyword in self.SOP_GUIDANCE_KEYWORDS | self.SOP_FOLLOW_UP_KEYWORDS)

    def _looks_like_business_query(self, message: str, history_context: HistoryContext | None = None) -> bool:
        stripped = message.strip()
        if not stripped:
            return False
        if history_context and (history_context.active_doc_path or history_context.active_doc_title):
            if self._looks_like_follow_up(stripped):
                return True
        lowered = stripped.lower()
        return any(keyword.lower() in lowered for keyword in self.BUSINESS_CONTEXT_KEYWORDS)

    def _citation_label(self, item: dict[str, Any]) -> str:
        label = (item.get("title") or item.get("source") or "未命名文档").strip()
        label = re.sub(r"^OFFICE Import \|\s*", "", label)
        return label

    def _format_evidence_for_prompt(self, evidence: list[dict]) -> list[dict[str, str]]:
        formatted: list[dict[str, str]] = []
        seen_titles: set[str] = set()
        for item in evidence[:3]:
            title = self._citation_label(item)
            if title in seen_titles:
                continue
            seen_titles.add(title)
            formatted.append(
                {
                    "title": title,
                    "doc_type": item.get("doc_type", ""),
                    "snippet": item.get("snippet", ""),
                }
            )
        return formatted

    def _normalize_final_message(self, message: str) -> str:
        if not message:
            return ""
        cleaned_lines: list[str] = []
        section_labels = {"结论", "处理步骤", "回答要点", "下一步", "注意事项", "风险提醒", "引用来源", "引用"}
        for raw_line in message.replace("\r\n", "\n").split("\n"):
            line = raw_line.rstrip()
            line = re.sub(r"^\s{0,3}#{1,6}\s*", "", line)
            line = re.sub(r"^\s*\*\s+", "- ", line)
            line = line.replace("**", "").replace("__", "").replace("`", "")
            if line in section_labels:
                line = f"{line}："
            cleaned_lines.append(line)
        cleaned = "\n".join(cleaned_lines)
        cleaned = cleaned.replace("处理步骤或回答要点：", "回答要点：")
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    def _build_casual_response(self, message: str, history_context: HistoryContext) -> dict:
        intent = self._casual_intent(message) or "smalltalk"
        if intent == "greeting":
            response_message = (
                "你好，我是厂内物流 SOP 与异常处理助手。"
                "你可以直接问我某个作业指导书怎么做，或者问异常怎么处理。"
                "例如：`指导进行冲压车间自制件返修作业`、`零件X短缺应该怎么处理？`"
            )
        elif intent == "model_info":
            if self.llm_client.enabled:
                response_message = (
                    f"当前后端已配置真实模型调用，正在使用 `{self.settings.llm_provider}` / `{self.settings.llm_model}`。"
                    f" 当前超时配置是 {int(self.settings.llm_timeout_seconds)} 秒。"
                )
            else:
                response_message = (
                    "当前还没有成功接入真实模型，系统正在使用本地语义匹配 + RAG 模式。"
                    f" 现在的配置项是 `{self.settings.llm_provider}` / `{self.settings.llm_model}`，"
                    "但当前请求没有走到真实模型返回。"
                )
        elif intent == "capability":
            response_message = (
                "我当前主要能做 4 件事：\n"
                "1. 按 SOP 回答作业步骤、注意事项和原因说明。\n"
                "2. 处理短缺、错发、不良品、批次异常、库位异常等问题。\n"
                "3. 查询本地 mock 表，包括库存、历史异常、责任人映射和工单模板。\n"
                "4. 生成工单、通知、处理记录草稿，并在高风险动作时要求人工确认。"
            )
        elif intent == "acknowledge":
            if history_context.active_doc_title:
                response_message = (
                    f"收到。当前会话还在围绕《{history_context.active_doc_title}》。"
                    "你可以继续问“下一步呢”“注意什么”“为什么要这样做”。"
                )
            else:
                response_message = "收到。你可以继续给我一个 SOP 名称、异常场景，或者直接提问某一步怎么做。"
        else:
            response_message = (
                "我更擅长回答厂内物流 SOP、异常处理、库存/台账查询和动作草稿。"
                "如果你要测试上下文，可以先问一条 SOP，再继续追问“下一步呢”或“注意什么”。"
            )
        return {
            "message": response_message,
            "conclusion": "普通对话已响应。",
            "issue_type": "普通对话",
            "risk_level": "low",
            "handling_steps": [],
            "risk_alerts": ["当前是普通对话模式，未触发异常处理或敏感动作。"],
            "evidence": [],
            "actions": [],
            "confirmations": [],
            "tool_results": [],
            "mode": {
                "mock_mode": self.settings.mock_mode,
                "llm_connected": self.llm_client.enabled,
                "llm_provider": self.settings.llm_provider,
                "llm_model": self.settings.llm_model,
                "rag_enabled": self.settings.rag_enabled,
                "rag_profile": self.settings.rag_profile,
                "agent_mode": self.settings.agent_mode,
                "embedding_provider": self.settings.embedding_provider,
                "embedding_model": self.settings.embedding_model,
            },
            "trace": {
                "query_text": message.strip(),
                "matched_keywords": [],
                "sensitive_reasons": [],
                "high_risk_keywords": [],
                "retrieved_chunks": 0,
                "sop_guidance_mode": False,
                "conversation_mode": "casual_chat",
                "primary_doc_title": history_context.active_doc_title,
                "primary_doc_path": history_context.active_doc_path,
                "step_cursor": history_context.step_cursor,
                "total_steps": history_context.total_steps,
            },
        }

    def _build_llm_casual_response(
        self,
        message: str,
        history_context: HistoryContext,
        system_prompt: str,
    ) -> dict | None:
        llm_message = self.llm_client.render(
            system_prompt=system_prompt,
            user_prompt=(
                "当前是普通聊天/引导模式，不需要触发异常处理模板。\n"
                f"用户消息：{message}\n"
                f"上一轮用户消息：{history_context.last_user_message}\n"
                f"上一轮助手消息：{history_context.last_assistant_message}\n"
                "请自然回答，语气简洁，不要编造企业系统事实。"
            ),
        )
        if not llm_message:
            return None
        return {
            "message": llm_message,
            "conclusion": "普通对话已由真实模型响应。",
            "issue_type": "普通对话",
            "risk_level": "low",
            "handling_steps": [],
            "risk_alerts": ["当前是普通对话模式，未触发异常处理或敏感动作。"],
            "evidence": [],
            "actions": [],
            "confirmations": [],
            "tool_results": [],
            "mode": {
                "mock_mode": self.settings.mock_mode,
                "llm_connected": self.llm_client.enabled,
                "llm_provider": self.settings.llm_provider,
                "llm_model": self.settings.llm_model,
                "rag_enabled": self.settings.rag_enabled,
                "rag_profile": self.settings.rag_profile,
                "agent_mode": self.settings.agent_mode,
                "embedding_provider": self.settings.embedding_provider,
                "embedding_model": self.settings.embedding_model,
            },
            "trace": {
                "query_text": message.strip(),
                "matched_keywords": [],
                "sensitive_reasons": [],
                "high_risk_keywords": [],
                "retrieved_chunks": 0,
                "sop_guidance_mode": False,
                "conversation_mode": "llm_chat",
                "primary_doc_title": history_context.active_doc_title,
                "primary_doc_path": history_context.active_doc_path,
                "step_cursor": history_context.step_cursor,
                "total_steps": history_context.total_steps,
            },
        }

    def _resolve_runtime(self, overrides) -> RuntimeConfig:
        rag_profile = overrides.rag_profile if overrides and overrides.rag_profile else self.settings.rag_profile
        top_k_default = self.settings.rag_full_top_k if rag_profile == "full" else self.settings.rag_top_k
        return RuntimeConfig(
            rag_enabled=overrides.rag_enabled if overrides and overrides.rag_enabled is not None else self.settings.rag_enabled,
            rag_profile=rag_profile,
            agent_mode=overrides.agent_mode if overrides and overrides.agent_mode else self.settings.agent_mode,
            top_k=overrides.top_k if overrides and overrides.top_k else top_k_default,
        )

    def _assess_risk(
        self,
        classification: ClassificationResult,
        inventory_rows: list[dict],
        incident_rows: list[dict],
        message: str,
    ) -> tuple[str, list[str]]:
        alerts: list[str] = []
        risk_level = "low"
        if classification.issue_type in {"短缺", "错发", "不良品", "批次异常", "库位异常"}:
            risk_level = "medium"
        if classification.issue_type == "高优先级停线风险" or classification.high_risk_keywords:
            risk_level = "high"
            alerts.append("命中停线/紧急关键词，需要优先处理。")
        if inventory_rows:
            row = inventory_rows[0]
            on_hand = int(row.get("on_hand_qty", "0") or 0)
            safety_stock = int(row.get("safety_stock", "0") or 0)
            if on_hand <= safety_stock:
                risk_level = "high" if classification.issue_type in {"短缺", "高优先级停线风险"} else risk_level
                alerts.append(f"库存余量 {on_hand}，已接近或低于安全库存 {safety_stock}。")
        if incident_rows and len(incident_rows) >= 2:
            alerts.append("历史台账中存在同类异常，建议补充复盘。")
            if risk_level == "medium":
                risk_level = "high" if classification.issue_type in {"批次异常", "不良品"} else risk_level
        if "报废" in message:
            alerts.append("涉及报废动作，必须人工确认。")
            risk_level = "high"
        if not alerts:
            alerts.append("当前建议基于 mock 规则和本地知识库，请由现场人员复核后执行。")
        return risk_level, alerts

    def _build_steps(self, issue_type: str, evidence: list[dict], response_style: dict) -> list[str]:
        steps = list(self.ISSUE_DEFAULT_STEPS.get(issue_type, ["先确认问题范围。", "补充现场事实。", "保留处理记录。"]))
        max_steps = int(response_style.get("max_steps", 4) or 4)
        for item in evidence[:1]:
            steps.append(f"参考《{self._citation_label(item)}》中的 SOP 段落执行复核。")
        return steps[:max_steps]

    def _build_conclusion(
        self,
        issue_type: str,
        risk_level: str,
        inventory_rows: list[dict],
        owner_rows: list[dict],
    ) -> str:
        inventory_hint = ""
        if inventory_rows:
            inventory_row = inventory_rows[0]
            inventory_hint = (
                f" 相关物料 {inventory_row.get('item_name')} 当前余量 {inventory_row.get('on_hand_qty')}，"
                f"安全库存 {inventory_row.get('safety_stock')}。"
            )
        owner_hint = ""
        if owner_rows:
            owner_row = owner_rows[0]
            owner_hint = f" 建议先由 {owner_row.get('department')} / {owner_row.get('owner_name')} 接手。"
        return f"判定为 {issue_type}，当前风险等级 {risk_level}。{inventory_hint}{owner_hint}".strip()

    def _build_message(
        self,
        conclusion: str,
        steps: list[str],
        alerts: list[str],
        evidence: list[dict],
        steps_label: str = "处理步骤",
    ) -> str:
        citation_labels = list(dict.fromkeys(self._citation_label(item) for item in evidence[:3]))
        citations = "；".join(f"《{label}》" for label in citation_labels) or "无"
        step_block = "\n".join(f"{index + 1}. {step}" for index, step in enumerate(steps))
        alert_block = "\n".join(f"- {alert}" for alert in alerts)
        return (
            f"结论：{conclusion}\n\n"
            f"{steps_label}：\n{step_block}\n\n"
            f"风险提醒：\n{alert_block}\n\n"
            f"引用来源：{citations}"
        )

    def _is_sop_guidance_query(
        self,
        message: str,
        classification: ClassificationResult,
        evidence: list[dict],
        history_context: HistoryContext,
        has_history: bool = False,
    ) -> bool:
        has_office_evidence = any(item.get("doc_type") == "OFFICE" or "作业指导书" in item.get("title", "") for item in evidence)
        has_active_sop = bool(history_context.active_doc_path or history_context.active_doc_title)
        if not has_office_evidence and not has_active_sop:
            return False
        guidance_like_query = self._looks_like_sop_question(message)
        follow_up_like_query = guidance_like_query or (has_active_sop and self._looks_like_follow_up(message))
        if classification.issue_type == "一般异常咨询":
            if has_history and has_active_sop and follow_up_like_query:
                return True
            return has_office_evidence and guidance_like_query
        scenario_like_query = any(keyword in message for keyword in self.ISSUE_SCENARIO_KEYWORDS)
        if has_history and has_active_sop and follow_up_like_query:
            return True
        return has_office_evidence and guidance_like_query and not scenario_like_query

    def _read_document(self, relative_path: str | None) -> str:
        if not relative_path:
            return ""
        document_path = self.settings.project_root / Path(relative_path)
        if not document_path.exists() or not document_path.is_file():
            return ""
        return document_path.read_text(encoding="utf-8")

    def _extract_markdown_section(self, content: str, heading: str) -> str:
        match = re.search(
            rf"^### {re.escape(heading)}\s*$\n(.*?)(?=^### |\Z)",
            content,
            flags=re.MULTILINE | re.DOTALL,
        )
        return match.group(1).strip() if match else ""

    def _clean_sop_item(self, line: str) -> str:
        cleaned = line.strip().lstrip("-").strip()
        cleaned = re.sub(r"^\d+(?:\.\d+)?\.\s*", "", cleaned)
        return cleaned.strip()

    def _extract_section_items(self, content: str, heading: str) -> list[str]:
        section = self._extract_markdown_section(content, heading)
        if not section:
            return []
        items: list[str] = []
        for raw_line in section.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("### "):
                break
            if re.match(r"^(\d+(?:\.\d+)?)\.\s+", line) or line.startswith("- "):
                cleaned = self._clean_sop_item(line)
                if cleaned:
                    items.append(cleaned)
        deduped: list[str] = []
        seen_items: set[str] = set()
        for item in items:
            if item in seen_items:
                continue
            seen_items.add(item)
            deduped.append(item)
        return deduped

    def _extract_semantic_candidates(self, content: str) -> list[dict]:
        candidates: list[dict] = []
        current_section = "正文"
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("### "):
                current_section = line.replace("###", "", 1).strip()
                continue
            if line.startswith(("# ", "## ", "- Source ", "- File Type", "- Imported At")):
                continue
            if line.startswith("- "):
                cleaned = self._clean_sop_item(line)
            elif re.match(r"^(\d+(?:\.\d+)?)\.\s+", line):
                cleaned = self._clean_sop_item(line)
            else:
                cleaned = line
            if len(cleaned) < 4:
                continue
            candidates.append(
                {
                    "section": current_section,
                    "text": cleaned,
                }
            )
        deduped: list[dict] = []
        seen: set[str] = set()
        for candidate in candidates:
            key = f"{candidate['section']}::{candidate['text']}"
            if key in seen:
                continue
            seen.add(key)
            deduped.append(candidate)
        return deduped

    def _rank_semantic_candidates(self, query: str, candidates: list[dict], limit: int = 5) -> list[dict]:
        if not candidates:
            return []
        query_counter = to_semantic_counter(query)
        scored: list[dict] = []
        for candidate in candidates:
            candidate_counter = to_semantic_counter(candidate["text"])
            section_counter = to_semantic_counter(candidate["section"])
            semantic_score = cosine_similarity(query_counter, candidate_counter)
            section_score = cosine_similarity(query_counter, section_counter)
            overlap = len(set(query_counter) & set(candidate_counter))
            score = semantic_score + section_score * 0.18 + overlap * 0.03
            if score <= 0:
                continue
            scored.append(
                {
                    **candidate,
                    "score": round(score, 3),
                }
            )
        scored.sort(key=lambda item: item["score"], reverse=True)
        top_items = scored[:limit]
        probabilities = softmax([item["score"] for item in top_items], temperature=0.2)
        for index, item in enumerate(top_items):
            probability = probabilities[index] if index < len(probabilities) else 0.0
            item["probability"] = round(probability, 3)
        return top_items

    def _confidence_label(self, probability: float) -> str:
        if probability >= 0.55:
            return "高"
        if probability >= 0.3:
            return "中"
        return "低"

    def _semantic_intent(self, message: str) -> str:
        if any(keyword in message for keyword in ["为什么", "原因", "目的", "为何"]):
            return "why"
        if any(keyword in message for keyword in ["注意", "要点", "重点", "风险", "确认什么"]):
            return "attention"
        if any(keyword in message for keyword in ["下一步", "然后", "接下来", "继续", "后面", "还有吗"]):
            return "next"
        if any(keyword in message for keyword in ["步骤", "流程", "怎么做", "如何做", "怎么操作", "操作", "作业"]):
            return "steps"
        if any(keyword in message for keyword in ["看什么", "需要看什么", "什么意思", "怎么理解", "哪些", "哪几个", "是什么"]):
            return "explain"
        return "general"

    def _is_explicit_incident_query(self, message: str) -> bool:
        incident_keywords = [
            "怎么处理",
            "如何处理",
            "怎么办",
            "异常",
            "短缺",
            "缺料",
            "错发",
            "不良品",
            "批次异常",
            "报废",
            "停线",
            "升级",
            "责任",
            "对外通知",
            "工单",
            "台账",
            "库存",
            "余量",
        ]
        return any(keyword in message for keyword in incident_keywords)

    def _dedupe_preserve_order(self, items: list[str], limit: int) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for item in items:
            cleaned = item.strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            deduped.append(cleaned)
            if len(deduped) >= limit:
                break
        return deduped

    def _to_answer_style_points(
        self,
        intent: str,
        ranked: list[dict],
        parsed_doc: dict,
    ) -> list[str]:
        steps = parsed_doc.get("steps", [])
        key_points = parsed_doc.get("key_points", [])
        reasons = parsed_doc.get("reasons", [])
        ranked_texts = [item["text"] for item in ranked]

        if intent == "why":
            candidates = self._dedupe_preserve_order(ranked_texts + reasons + key_points, 3)
            return [f"这一步主要是为了：{item}" for item in candidates]

        if intent == "attention":
            candidates = self._dedupe_preserve_order(ranked_texts + key_points + reasons, 4)
            return [f"现场重点看：{item}" for item in candidates]

        if intent == "steps":
            candidates = self._dedupe_preserve_order(ranked_texts + steps, 4)
            return [f"建议按这个顺序执行：{item}" if index == 0 else item for index, item in enumerate(candidates)]

        if intent == "next":
            candidates = self._dedupe_preserve_order(steps + ranked_texts + key_points, 4)
            return [f"后续可以继续这样做：{item}" if index == 0 else item for index, item in enumerate(candidates)]

        if intent == "explain":
            candidates = self._dedupe_preserve_order(ranked_texts + key_points + steps + reasons, 4)
            if not candidates:
                return []
            answer_points = [f"简单说，你现在最需要关注的是：{candidates[0]}"]
            for item in candidates[1:4]:
                answer_points.append(f"同时再看：{item}")
            return answer_points

        candidates = self._dedupe_preserve_order(ranked_texts + steps + key_points + reasons, 4)
        if not candidates:
            return []
        answer_points = [f"先做核心动作：{candidates[0]}"]
        for item in candidates[1:4]:
            answer_points.append(f"补充要点：{item}")
        return answer_points

    def _primary_sop_document(
        self,
        evidence: list[dict],
        anchor_text: str = "",
        preferred_path: str = "",
        preferred_title: str = "",
    ) -> dict | None:
        candidates = [item for item in evidence if item.get("path")] or list(evidence)
        if preferred_path:
            for item in candidates:
                if item.get("path") == preferred_path:
                    return item
            preferred_file = self.settings.project_root / Path(preferred_path)
            if preferred_file.exists():
                return {
                    "title": preferred_title,
                    "path": preferred_path,
                    "source": Path(preferred_path).name,
                    "doc_type": "OFFICE",
                }
        if not candidates:
            return None
        if not anchor_text.strip():
            return candidates[0]
        anchor_counter = to_semantic_counter(anchor_text)
        scored: list[tuple[float, dict]] = []
        for item in candidates:
            title = item.get("title", "")
            title_score = cosine_similarity(anchor_counter, to_semantic_counter(title))
            if anchor_text in title or title in anchor_text:
                title_score += 0.25
            scored.append((title_score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return scored[0][1]

    def _parse_sop_document(
        self,
        evidence: list[dict],
        anchor_text: str = "",
        preferred_path: str = "",
        preferred_title: str = "",
    ) -> dict:
        primary = self._primary_sop_document(
            evidence,
            anchor_text=anchor_text,
            preferred_path=preferred_path,
            preferred_title=preferred_title,
        )
        if not primary:
            return {"title": "", "steps": [], "key_points": [], "reasons": [], "path": None}
        content = self._read_document(primary.get("path"))
        title_match = re.search(r"^## Sheet \| (.+)$", content, flags=re.MULTILINE)
        title = title_match.group(1).strip() if title_match else primary.get("title", "")
        return {
            "title": title,
            "path": primary.get("path"),
            "steps": self._extract_section_items(content, "主要步骤"),
            "key_points": self._extract_section_items(content, "关键要点"),
            "reasons": self._extract_section_items(content, "理由说明"),
        }

    def _rank_sop_items(self, query: str, items: list[str], limit: int) -> list[str]:
        if not items:
            return []
        query_counter = to_semantic_counter(query)
        scored: list[tuple[float, str]] = []
        for item in items:
            item_counter = to_semantic_counter(item)
            overlap = len(set(query_counter) & set(item_counter))
            score = cosine_similarity(query_counter, item_counter) + overlap * 0.06
            scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        ranked = [item for score, item in scored if score > 0]
        deduped: list[str] = []
        for item in ranked:
            if item not in deduped:
                deduped.append(item)
            if len(deduped) >= limit:
                break
        return deduped or items[:limit]

    def _focus_sop_items(
        self,
        user_message: str,
        query_text: str,
        parsed_doc: dict,
        step_cursor: int = 0,
    ) -> tuple[list[str], list[str], int, str]:
        reasons = parsed_doc.get("reasons", [])
        key_points = parsed_doc.get("key_points", [])
        steps = parsed_doc.get("steps", [])
        focus_query = user_message.strip() or query_text
        detail_keywords = ["PDA", "标签", "库位", "扫码", "推荐库位码", "合格标签"]
        next_step_keywords = ["下一步", "然后", "接下来", "继续", "再然后", "后面", "还有吗"]

        if any(keyword in user_message for keyword in ["为什么", "原因", "目的", "为何"]):
            return (
                self._rank_sop_items(focus_query, reasons or key_points or steps, 4),
                ["如现场条件变化，先复核再执行。"],
                step_cursor,
                "why",
            )
        if any(keyword in user_message for keyword in ["注意", "要点", "重点", "风险", "确认什么"]):
            return (
                self._rank_sop_items(focus_query, key_points or reasons or steps, 5),
                ["若标签、PDA 或库位状态异常，先暂停并复核。"],
                step_cursor,
                "attention",
            )
        if any(keyword in user_message for keyword in next_step_keywords):
            if not steps:
                return (
                    ["当前这份 SOP 没有提取出可继续展开的主要步骤。"],
                    ["建议打开原始文档复核。"],
                    step_cursor,
                    "next_steps",
                )
            start = step_cursor if step_cursor > 0 else 0
            end = min(start + 3, len(steps))
            if start >= len(steps):
                return (
                    ["当前这份 SOP 的主要步骤已经讲完了。你可以继续问“注意什么”或“为什么要这样做”。"],
                    [f"该 SOP 共 {len(steps)} 步，当前已讲完。"],
                    len(steps),
                    "next_steps",
                )
            return (
                steps[start:end],
                [f"继续到第 {start + 1}-{end} 步，共 {len(steps)} 步。"],
                end,
                "next_steps",
            )

        matched_details = self._rank_sop_items(focus_query, steps + key_points + reasons, 4)
        if any(keyword in user_message for keyword in detail_keywords):
            return (
                matched_details or steps[:4],
                ["如员工继续追问，可继续问“注意什么 / 为什么要这样做 / 下一步是什么”。"],
                step_cursor,
                "detail",
            )

        initial_steps = steps[:4]
        alerts = key_points[:2]
        if len(steps) > len(initial_steps):
            alerts.append("如需继续，可直接追问“下一步呢”。")
        elif not alerts:
            alerts = ["如员工继续追问，可继续问“注意什么 / 为什么要这样做 / 下一步是什么”。"]
        return initial_steps, alerts, len(initial_steps), "steps"

    def _build_sop_guidance_response(
        self,
        user_message: str,
        query_text: str,
        evidence: list[dict],
        anchor_text: str = "",
        preferred_path: str = "",
        preferred_title: str = "",
        step_cursor: int = 0,
    ) -> tuple[str, str, list[str], list[str], dict]:
        parsed_doc = self._parse_sop_document(
            evidence,
            anchor_text=anchor_text,
            preferred_path=preferred_path,
            preferred_title=preferred_title,
        )
        source_title = parsed_doc.get("title") or (evidence[0]["title"] if evidence else preferred_title)
        lines, alerts, next_cursor, response_kind = self._focus_sop_items(
            user_message,
            query_text,
            parsed_doc,
            step_cursor=step_cursor,
        )
        if lines and response_kind in {"why", "attention", "detail"}:
            intent_map = {
                "why": "why",
                "attention": "attention",
                "detail": "explain",
            }
            lines = self._to_answer_style_points(
                intent_map[response_kind],
                [{"text": line} for line in lines],
                parsed_doc,
            )

        if any(keyword in user_message for keyword in ["为什么", "原因", "目的", "为何"]):
            conclusion = f"根据 {source_title}，当前问题更适合看该作业的原因和控制点。"
        elif any(keyword in user_message for keyword in ["注意", "要点", "重点", "风险", "确认什么"]):
            conclusion = f"根据 {source_title}，以下是该作业的关键注意事项。"
        elif response_kind == "next_steps":
            conclusion = f"根据 {source_title}，下面继续说明后续步骤。"
        elif any(keyword in user_message for keyword in ["PDA", "标签", "库位", "扫码", "推荐库位码", "合格标签"]):
            conclusion = f"根据 {source_title}，以下是和你追问内容最相关的 SOP 条目。"
        else:
            conclusion = f"根据 {source_title}，该作业可按以下主要步骤执行。"

        if not lines:
            lines = ["已命中相关 SOP，但当前文档没有提取出可直接展示的条目，建议打开原始文档继续查看。"]
            alerts = ["如果该 SOP 是图片版或扫描版，下一步需要补 OCR。"]
        return conclusion, "low", lines, alerts, {
            "primary_doc_title": source_title,
            "primary_doc_path": parsed_doc.get("path") or preferred_path,
            "step_cursor": next_cursor,
            "total_steps": len(parsed_doc.get("steps", [])),
            "response_kind": response_kind,
        }

    def _is_semantic_qa_mode(
        self,
        message: str,
        classification: ClassificationResult,
        evidence: list[dict],
        sop_guidance_mode: bool,
        history_context: HistoryContext,
    ) -> bool:
        if sop_guidance_mode or not evidence:
            return False
        if not any(item.get("doc_type") == "OFFICE" for item in evidence):
            return False
        semantic_intent = self._semantic_intent(message)
        has_active_sop = bool(history_context.active_doc_path or history_context.active_doc_title)
        if classification.issue_type == "一般异常咨询":
            return has_active_sop and (semantic_intent != "general" or self._looks_like_follow_up(message))
        if has_active_sop and semantic_intent in {"why", "attention", "steps", "explain", "next"}:
            return not self._is_explicit_incident_query(message)
        return False

    def _build_local_semantic_answer(
        self,
        user_message: str,
        query_text: str,
        evidence: list[dict],
        history_context: HistoryContext,
    ) -> tuple[str, str, list[str], list[str], dict]:
        use_history_anchor = bool(history_context.active_doc_path or history_context.active_doc_title) and self._looks_like_follow_up(user_message)
        parsed_doc = self._parse_sop_document(
            evidence,
            anchor_text=history_context.active_doc_title or query_text,
            preferred_path=history_context.active_doc_path if use_history_anchor else "",
            preferred_title=history_context.active_doc_title if use_history_anchor else "",
        )
        source_title = parsed_doc.get("title") or (evidence[0]["title"] if evidence else "命中文档")
        content = self._read_document(parsed_doc.get("path"))
        candidates = self._extract_semantic_candidates(content)
        ranked = self._rank_semantic_candidates(query_text, candidates, limit=5)
        semantic_intent = self._semantic_intent(user_message)
        if not ranked:
            return (
                f"已命中《{source_title}》，但当前本地语义解析没有抽出可直接回答的条目。",
                "low",
                ["建议改成更具体的问法，例如“这一步为什么要扫码”或“返修入库主要看哪些点”。"],
                ["当前是本地语义匹配模式，建议再补充关键词以提高命中率。"],
                {
                    "primary_doc_title": source_title,
                    "primary_doc_path": parsed_doc.get("path"),
                    "semantic_probability": 0.0,
                    "response_kind": "semantic_qa",
                },
            )

        top_probability = ranked[0].get("probability", 0.0)
        confidence_label = self._confidence_label(top_probability)
        focus_sections = {item["section"] for item in ranked[:3]}
        answer_points = self._to_answer_style_points(semantic_intent, ranked, parsed_doc)
        if semantic_intent == "why":
            conclusion = f"我理解你在追问《{source_title}》这一步为什么这样做，当前语义匹配置信度{confidence_label}。"
        elif semantic_intent == "attention":
            conclusion = f"我理解你在问《{source_title}》里执行时要重点盯哪些点，当前语义匹配置信度{confidence_label}。"
        elif semantic_intent == "steps":
            conclusion = f"我理解你在问《{source_title}》怎么做，这里先按本地语义匹配给你一个执行顺序，当前置信度{confidence_label}。"
        elif semantic_intent == "next":
            conclusion = f"我理解你在继续追问《{source_title}》的后续动作，下面先给你当前最相关的后续步骤，当前语义匹配置信度{confidence_label}。"
        elif semantic_intent == "explain":
            conclusion = f"我理解你在问《{source_title}》里这件事到底该看什么，下面先给你结论，再给依据，当前置信度{confidence_label}。"
        else:
            conclusion = f"根据语义匹配，《{source_title}》与当前问题最相关，我先给你最可能的回答方向，当前置信度{confidence_label}。"

        alerts = [
            f"本地语义匹配概率约 {round(top_probability * 100)}%，命中分区：{' / '.join(sorted(focus_sections)) or '正文'}。",
        ]
        if top_probability < 0.3:
            alerts.append("当前匹配度偏低，建议补充更具体的物料、环节或动作关键词。")
        else:
            alerts.append("如果你想继续追问，可以直接问“这一步为什么”“下一步是什么”“如果不一致怎么办”。")

        return conclusion, "low", answer_points, alerts, {
            "primary_doc_title": source_title,
            "primary_doc_path": parsed_doc.get("path"),
            "semantic_probability": top_probability,
            "response_kind": "semantic_qa",
        }

    def handle_chat(self, request) -> dict:
        runtime = self._resolve_runtime(request.overrides)
        tool_policies = self.prompt_loader.tool_policies()
        response_style = self.prompt_loader.response_style()
        system_prompt = self.prompt_loader.system_prompt()
        classifier = IssueClassifier(tool_policies)
        draft_builder = DraftBuilder(tool_policies)
        history_context = self._build_history_context(request.history)

        casual_intent = self._casual_intent(request.message)
        if (
            casual_intent
            and not self._looks_like_follow_up(request.message)
            and not self._looks_like_business_query(request.message, history_context)
        ):
            return self._build_casual_response(request.message, history_context)

        query_text = self._resolve_query_text(request, history_context)
        classification = classifier.classify(query_text)
        if classification.issue_type == "一般异常咨询" and not self._looks_like_business_query(request.message, history_context):
            if self.llm_client.enabled:
                llm_chat = self._build_llm_casual_response(request.message, history_context, system_prompt)
                if llm_chat:
                    return llm_chat
            return self._build_casual_response(request.message, history_context)
        inventory_rows = self.table_service.query_inventory(query_text)
        incident_rows = self.table_service.query_incidents(classification.issue_type, query_text)
        owner_rows = self.table_service.query_owner(classification.issue_type)

        evidence: list[dict] = []
        if runtime.agent_mode != "only-tool":
            evidence = self.retriever.search(
                query=query_text,
                issue_type=classification.issue_type,
                rag_enabled=runtime.rag_enabled,
                rag_profile=runtime.rag_profile,
                top_k=runtime.top_k,
                rerank_enabled=self.settings.rerank_enabled,
            )

        sop_guidance_mode = self._is_sop_guidance_query(
            request.message,
            classification,
            evidence,
            history_context,
            has_history=bool(request.history),
        )
        semantic_qa_mode = self._is_semantic_qa_mode(
            request.message,
            classification,
            evidence,
            sop_guidance_mode,
            history_context,
        )
        sop_trace: dict[str, Any] = {
            "primary_doc_title": history_context.active_doc_title,
            "primary_doc_path": history_context.active_doc_path,
            "step_cursor": history_context.step_cursor,
            "total_steps": history_context.total_steps,
            "conversation_mode": "exception_handling",
        }

        if sop_guidance_mode:
            risk_level = "low"
            use_history_anchor = bool(history_context.active_doc_path or history_context.active_doc_title) and self._looks_like_follow_up(request.message)
            anchor_text = history_context.active_doc_title or history_context.last_user_message or request.message
            conclusion, risk_level, steps, alerts, sop_trace = self._build_sop_guidance_response(
                request.message,
                query_text,
                evidence,
                anchor_text=anchor_text,
                preferred_path=history_context.active_doc_path if use_history_anchor else "",
                preferred_title=history_context.active_doc_title if use_history_anchor else "",
                step_cursor=history_context.step_cursor if use_history_anchor else 0,
            )
            sop_trace["conversation_mode"] = "sop_guidance"
        elif semantic_qa_mode:
            conclusion, risk_level, steps, alerts, sop_trace = self._build_local_semantic_answer(
                request.message,
                query_text,
                evidence,
                history_context,
            )
            sop_trace["conversation_mode"] = "semantic_qa"
        else:
            risk_level, alerts = self._assess_risk(classification, inventory_rows, incident_rows, query_text)
            conclusion = self._build_conclusion(classification.issue_type, risk_level, inventory_rows, owner_rows)
            steps = self._build_steps(classification.issue_type, evidence, response_style)

        templates = {
            action_type: self.table_service.get_ticket_template(action_type)
            for action_type in [
                "ticket_draft",
                "handling_record",
                "quality_escalation",
                "owner_assignment",
                "external_notification",
            ]
        }
        actions = []
        if not sop_guidance_mode and not semantic_qa_mode:
            actions = draft_builder.build_actions(
                issue_type=classification.issue_type,
                risk_level=risk_level,
                message=query_text,
                inventory_rows=inventory_rows,
                incident_rows=incident_rows,
                owner_rows=owner_rows,
                templates=templates,
            )
        confirmations = [
            action["confirmation_reason"]
            for action in actions
            if action["requires_confirmation"] and action.get("confirmation_reason")
        ]
        confirmations = list(dict.fromkeys(confirmations))

        tool_results: list[dict] = []
        if not sop_guidance_mode and not semantic_qa_mode:
            tool_results = [
                {
                    "tool_name": "inventory_lookup",
                    "summary": "查询库存/余量表",
                    "rows": inventory_rows,
                },
                {
                    "tool_name": "incident_lookup",
                    "summary": "查询历史异常台账",
                    "rows": incident_rows,
                },
                {
                    "tool_name": "owner_lookup",
                    "summary": "查询责任部门映射",
                    "rows": owner_rows,
                },
            ]
            tool_results = [result for result in tool_results if result["rows"]]

        response_kind = sop_trace.get("response_kind", "")
        steps_label = "回答要点" if sop_guidance_mode or semantic_qa_mode or response_kind in {"semantic_qa", "detail", "attention", "why"} else "处理步骤"
        mock_message = self._build_message(conclusion, steps, alerts, evidence, steps_label=steps_label)
        evidence_summary = self._format_evidence_for_prompt(evidence)
        llm_message = self.llm_client.render(
            system_prompt=system_prompt,
            user_prompt=(
                "请根据以下结构化信息输出最终回复，保持业务化、简洁、可执行。\n"
                "输出必须是纯文本，不要使用 Markdown 标题、星号加粗、反引号或代码块。\n"
                f"固定使用以下字段名：结论、{steps_label}、风险提醒、引用来源。\n"
                f"第二段标题只能写“{steps_label}：”，不要写“处理步骤或回答要点”。\n"
                "引用来源只写文档标题，不要写 .md 文件名、hash 文件名或路径。\n"
                f"用户问题：{request.message}\n"
                f"最近对话上下文：用户上轮={history_context.last_user_message}；助手上轮={history_context.last_assistant_message}\n"
                f"检索上下文：{query_text}\n"
                f"当前响应模式：{sop_trace.get('conversation_mode', 'exception_handling')}\n"
                f"结论：{conclusion}\n"
                f"回答要点：{steps}\n"
                f"风险提醒：{alerts}\n"
                f"引用：{evidence_summary}\n"
                "如果当前是 SOP 问答或语义问答，请先总结再展开，不要机械照抄原文。"
            ),
        )
        message = self._normalize_final_message(llm_message or mock_message)
        logger.info(
            "Handled chat issue_type=%s risk=%s rag=%s mode=%s",
            classification.issue_type,
            risk_level,
            runtime.rag_enabled,
            runtime.agent_mode,
        )

        return {
            "message": message,
            "conclusion": conclusion,
            "issue_type": classification.issue_type,
            "risk_level": risk_level,
            "handling_steps": steps,
            "risk_alerts": alerts,
            "evidence": evidence,
            "actions": actions,
            "confirmations": confirmations,
            "tool_results": tool_results,
            "mode": {
                "mock_mode": self.settings.mock_mode,
                "llm_connected": self.llm_client.enabled,
                "llm_provider": self.settings.llm_provider,
                "llm_model": self.settings.llm_model,
                "rag_enabled": runtime.rag_enabled,
                "rag_profile": runtime.rag_profile,
                "agent_mode": runtime.agent_mode,
                "embedding_provider": self.settings.embedding_provider,
                "embedding_model": self.settings.embedding_model,
            },
            "trace": {
                "query_text": query_text,
                "matched_keywords": classification.matched_keywords,
                "sensitive_reasons": classification.sensitive_reasons,
                "high_risk_keywords": classification.high_risk_keywords,
                "retrieved_chunks": len(evidence),
                "sop_guidance_mode": sop_guidance_mode,
                "conversation_mode": sop_trace.get("conversation_mode", "exception_handling"),
                "primary_doc_title": sop_trace.get("primary_doc_title", ""),
                "primary_doc_path": sop_trace.get("primary_doc_path", ""),
                "step_cursor": sop_trace.get("step_cursor", 0),
                "total_steps": sop_trace.get("total_steps", 0),
                "response_kind": sop_trace.get("response_kind", ""),
                "semantic_probability": sop_trace.get("semantic_probability", 0.0),
            },
        }

    def confirm_action(self, action_id: str, action_type: str, action_title: str) -> dict:
        return {
            "action_id": action_id,
            "status": "confirmed",
            "message": f"已确认：{action_title}（{action_type}）仍为草稿状态，等待人工复制/提交到真实系统。",
        }
