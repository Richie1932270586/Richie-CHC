from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RuntimeOverrides(BaseModel):
    rag_enabled: bool | None = None
    rag_profile: str | None = None
    agent_mode: str | None = None
    top_k: int | None = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[dict[str, Any]] = Field(default_factory=list)
    overrides: RuntimeOverrides | None = None


class EvidenceItem(BaseModel):
    title: str
    source: str
    snippet: str
    score: float
    doc_type: str
    probability: float | None = None
    confidence: str | None = None


class ToolResult(BaseModel):
    tool_name: str
    summary: str
    rows: list[dict[str, Any]] = Field(default_factory=list)


class SuggestedAction(BaseModel):
    action_id: str
    action_type: str
    title: str
    description: str
    draft: str
    sensitive: bool = False
    requires_confirmation: bool = False
    confirmation_reason: str | None = None
    status: str = "draft"


class ChatResponse(BaseModel):
    message: str
    conclusion: str
    issue_type: str
    risk_level: str
    handling_steps: list[str]
    risk_alerts: list[str]
    evidence: list[EvidenceItem]
    actions: list[SuggestedAction]
    confirmations: list[str]
    tool_results: list[ToolResult]
    mode: dict[str, Any]
    trace: dict[str, Any]


class ConfirmActionRequest(BaseModel):
    action_id: str
    action_type: str
    action_title: str
    draft: str


class ConfirmActionResponse(BaseModel):
    action_id: str
    status: str
    message: str


class ImportFolderRequest(BaseModel):
    source_dir: str = Field(min_length=1, max_length=4000)
    replace_existing: bool = True
    recursive: bool = True


class ImportFileRecord(BaseModel):
    source_file: str
    output_file: str | None = None
    title: str
    extension: str
    status: str
    detail: str | None = None


class ImportFolderResponse(BaseModel):
    source_dir: str
    source_id: str
    target_dir: str
    scanned_files: int
    imported_files: list[ImportFileRecord] = Field(default_factory=list)
    skipped_files: list[ImportFileRecord] = Field(default_factory=list)
    failed_files: list[ImportFileRecord] = Field(default_factory=list)
    index_file: str
    total_indexed_documents: int
    total_indexed_chunks: int
    message: str
