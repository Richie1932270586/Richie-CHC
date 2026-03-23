from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    ConfirmActionRequest,
    ConfirmActionResponse,
    ImportFolderRequest,
    ImportFolderResponse,
)
from app.services.agent import FactoryExceptionAgent
from app.services.llm_client import LLMClient
from app.services.office_importer import OfficeImportService
from app.services.prompt_loader import PromptLoader
from app.services.retriever import Retriever
from app.services.tables import TableService


settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

retriever = Retriever(settings)
table_service = TableService(settings)
prompt_loader = PromptLoader(settings)
llm_client = LLMClient(settings)
office_importer = OfficeImportService(settings, retriever)
agent = FactoryExceptionAgent(settings, retriever, table_service, prompt_loader, llm_client)

app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.allow_cors_all else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event() -> None:
    retriever.ensure_index()


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "app_name": settings.app_name,
        "mock_mode": settings.mock_mode,
        "llm_provider": settings.llm_provider,
        "llm_connected": llm_client.enabled,
    }


@app.get("/api/config")
def api_config() -> dict:
    runtime_mode = "llm" if llm_client.enabled else "local_semantic"
    runtime_description = (
        f"当前已接入真实模型 {settings.llm_model}，会用模型做聊天和基于检索结果的综合回答。当前项目默认推荐本地配置为 Ollama + qwen3.5:9b。"
        if llm_client.enabled
        else "当前未接入真实大模型，系统正在使用本地语义匹配 + RAG 检索；SOP 问答可用，但日常闲聊能力有限。推荐先执行 `ollama pull qwen3.5:9b` 并保持 Ollama 服务启动；如果你本机已经有自定义 `qwen3.5:14b`，只需要改 `.env` 里的 `LLM_MODEL`。"
    )
    return {
        "app_name": settings.app_name,
        "mock_mode": settings.mock_mode,
        "llm_connected": llm_client.enabled,
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "llm_timeout_seconds": settings.llm_timeout_seconds,
        "llm_reasoning_effort": settings.llm_reasoning_effort,
        "llm_max_tokens": settings.llm_max_tokens,
        "runtime_mode": runtime_mode,
        "runtime_description": runtime_description,
        "agent_mode": settings.agent_mode,
        "rag_enabled": settings.rag_enabled,
        "rag_profile": settings.rag_profile,
        "rag_top_k": settings.rag_top_k,
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
        "embedding_provider": settings.embedding_provider,
        "embedding_model": settings.embedding_model,
        "imported_kb_dir": str(settings.imported_kb_dir.relative_to(settings.project_root)),
    }


@app.get("/api/rag/documents")
def list_rag_documents() -> dict:
    return {
        "documents": retriever.list_documents(),
        "index_file": str(settings.index_file.relative_to(settings.project_root)),
    }


@app.get("/api/rag/imports")
def list_rag_imports() -> dict:
    return office_importer.list_imports()


@app.post("/api/rag/import-folder", response_model=ImportFolderResponse)
def import_rag_folder(request: ImportFolderRequest) -> ImportFolderResponse:
    try:
        result = office_importer.import_folder(
            source_dir=request.source_dir,
            replace_existing=request.replace_existing,
            recursive=request.recursive,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"导入失败：{exc}") from exc
    return ImportFolderResponse.model_validate(result)


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    return ChatResponse.model_validate(agent.handle_chat(request))


@app.post("/api/actions/confirm", response_model=ConfirmActionResponse)
def confirm_action(request: ConfirmActionRequest) -> ConfirmActionResponse:
    return ConfirmActionResponse.model_validate(
        agent.confirm_action(request.action_id, request.action_type, request.action_title)
    )


if settings.web_dist_dir.exists():
    app.mount("/ui", StaticFiles(directory=settings.web_dist_dir, html=True), name="ui")


@app.get("/", response_model=None)
def read_index() -> Response:
    index_file = settings.web_dist_dir / "index.html"
    if index_file.exists():
        return RedirectResponse("/ui")
    return Response(
        content='{"message":"UI dist not found. Please run the backend API directly or start apps/web."}',
        media_type="application/json",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )
