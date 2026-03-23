from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "apps" / "api"))

from app.core.config import get_settings  # noqa: E402
from app.models.schemas import ChatRequest, RuntimeOverrides  # noqa: E402
from app.services.agent import FactoryExceptionAgent  # noqa: E402
from app.services.llm_client import LLMClient  # noqa: E402
from app.services.prompt_loader import PromptLoader  # noqa: E402
from app.services.retriever import Retriever  # noqa: E402
from app.services.tables import TableService  # noqa: E402


def main() -> None:
    settings = get_settings()
    cases = json.loads(settings.eval_cases_file.read_text(encoding="utf-8"))
    agent = FactoryExceptionAgent(
        settings=settings,
        retriever=Retriever(settings),
        table_service=TableService(settings),
        prompt_loader=PromptLoader(settings),
        llm_client=LLMClient(settings),
    )

    passed = 0
    for case in cases:
        overrides = RuntimeOverrides.model_validate(case.get("overrides", {}))
        request = ChatRequest(message=case["question"], overrides=overrides)
        response = agent.handle_chat(request)

        issue_type_ok = response["issue_type"] == case["expected_issue_type"]
        confirm_ok = bool(response["confirmations"]) == case["expect_confirmation"]
        tools_used = {item["tool_name"] for item in response["tool_results"]}
        required_tools_ok = set(case["required_tools"]).issubset(tools_used)
        expected_conversation_mode = case.get("expected_conversation_mode")
        conversation_mode_ok = (
            expected_conversation_mode is None
            or response.get("trace", {}).get("conversation_mode") == expected_conversation_mode
        )
        max_retrieved_chunks = case.get("max_retrieved_chunks")
        retrieved_chunks_ok = (
            max_retrieved_chunks is None
            or response.get("trace", {}).get("retrieved_chunks", 0) <= max_retrieved_chunks
        )

        case_passed = (
            issue_type_ok
            and confirm_ok
            and required_tools_ok
            and conversation_mode_ok
            and retrieved_chunks_ok
        )
        passed += int(case_passed)
        print(
            f"[{'PASS' if case_passed else 'FAIL'}] {case['id']} | "
            f"issue={response['issue_type']} confirm={bool(response['confirmations'])} "
            f"mode={response.get('trace', {}).get('conversation_mode')} "
            f"chunks={response.get('trace', {}).get('retrieved_chunks', 0)} "
            f"tools={sorted(tools_used)}"
        )

    print(f"\nEval result: {passed}/{len(cases)} passed")


if __name__ == "__main__":
    main()
