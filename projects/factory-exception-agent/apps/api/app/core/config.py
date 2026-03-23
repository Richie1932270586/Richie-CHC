from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _load_env_file(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _resolve_path(project_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else project_root / path


@dataclass(slots=True)
class Settings:
    project_root: Path
    app_name: str
    api_host: str
    api_port: int
    log_level: str
    mock_mode: bool
    llm_provider: str
    llm_base_url: str
    llm_model: str
    llm_api_key: str
    llm_temperature: float
    llm_timeout_seconds: float
    llm_reasoning_effort: str
    llm_max_tokens: int
    agent_mode: str
    rag_enabled: bool
    rag_profile: str
    rag_top_k: int
    rag_full_top_k: int
    chunk_size: int
    chunk_overlap: int
    rerank_enabled: bool
    embedding_provider: str
    embedding_model: str
    auto_rebuild_index: bool
    allow_cors_all: bool
    kb_dir: Path
    imported_kb_dir: Path
    index_file: Path
    import_manifest_file: Path
    inventory_file: Path
    incidents_file: Path
    owners_file: Path
    ticket_templates_file: Path
    eval_cases_file: Path
    prompts_dir: Path
    web_dist_dir: Path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    project_root = Path(__file__).resolve().parents[4]
    env_values = _load_env_file(project_root / ".env")

    def env(name: str, default: str) -> str:
        return os.getenv(name, env_values.get(name, default))

    return Settings(
        project_root=project_root,
        app_name=env("APP_NAME", "Factory Exception Agent"),
        api_host=env("API_HOST", "127.0.0.1"),
        api_port=int(env("API_PORT", "8000")),
        log_level=env("LOG_LEVEL", "INFO"),
        mock_mode=_parse_bool(env("MOCK_MODE", "true"), True),
        llm_provider=env("LLM_PROVIDER", "mock"),
        llm_base_url=env("LLM_BASE_URL", "https://api.openai.com/v1"),
        llm_model=env("LLM_MODEL", "gpt-4.1-mini"),
        llm_api_key=env("LLM_API_KEY", ""),
        llm_temperature=float(env("LLM_TEMPERATURE", "0.2")),
        llm_timeout_seconds=float(env("LLM_TIMEOUT_SECONDS", "120")),
        llm_reasoning_effort=env("LLM_REASONING_EFFORT", "none"),
        llm_max_tokens=int(env("LLM_MAX_TOKENS", "480")),
        agent_mode=env("AGENT_MODE", "hybrid"),
        rag_enabled=_parse_bool(env("RAG_ENABLED", "true"), True),
        rag_profile=env("RAG_PROFILE", "light"),
        rag_top_k=int(env("RAG_TOP_K", "4")),
        rag_full_top_k=int(env("RAG_FULL_TOP_K", "6")),
        chunk_size=int(env("CHUNK_SIZE", "260")),
        chunk_overlap=int(env("CHUNK_OVERLAP", "50")),
        rerank_enabled=_parse_bool(env("RERANK_ENABLED", "true"), True),
        embedding_provider=env("EMBEDDING_PROVIDER", "local-bow"),
        embedding_model=env("EMBEDDING_MODEL", "token-frequency-v1"),
        auto_rebuild_index=_parse_bool(env("AUTO_REBUILD_INDEX", "true"), True),
        allow_cors_all=_parse_bool(env("ALLOW_CORS_ALL", "true"), True),
        kb_dir=_resolve_path(project_root, env("KB_DIR", "data/knowledge_base")),
        imported_kb_dir=_resolve_path(project_root, env("IMPORTED_KB_DIR", "data/knowledge_base/imported_office")),
        index_file=_resolve_path(project_root, env("INDEX_FILE", "data/indexes/kb_index.json")),
        import_manifest_file=_resolve_path(project_root, env("IMPORT_MANIFEST_FILE", "data/indexes/import_manifest.json")),
        inventory_file=_resolve_path(project_root, env("INVENTORY_FILE", "data/mock_tables/inventory.csv")),
        incidents_file=_resolve_path(project_root, env("INCIDENTS_FILE", "data/mock_tables/incidents.csv")),
        owners_file=_resolve_path(project_root, env("OWNERS_FILE", "data/mock_tables/owners.csv")),
        ticket_templates_file=_resolve_path(project_root, env("TICKET_TEMPLATES_FILE", "data/mock_tables/ticket_templates.json")),
        eval_cases_file=_resolve_path(project_root, env("EVAL_CASES_FILE", "data/eval_cases/eval_cases.json")),
        prompts_dir=project_root / "prompts",
        web_dist_dir=project_root / "apps" / "web" / "dist",
    )
