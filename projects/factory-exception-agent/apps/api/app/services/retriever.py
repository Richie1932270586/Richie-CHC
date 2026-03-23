from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from app.core.config import Settings
from app.services.text_utils import (
    apply_idf,
    build_idf,
    cosine_similarity,
    normalize_text,
    softmax,
    to_counter,
    to_semantic_counter,
    tokenize,
    truncate,
)


def _chunk_text(content: str, chunk_size: int, overlap: int) -> list[str]:
    paragraphs = [paragraph.strip() for paragraph in content.split("\n\n") if paragraph.strip()]
    if not paragraphs:
        return []
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip()
        if len(candidate) <= chunk_size or not current:
            current = candidate
            continue
        chunks.append(current)
        current = current[-overlap:].strip() + "\n\n" + paragraph if overlap else paragraph
    if current:
        chunks.append(current.strip())
    return chunks


def _extract_doc_title(path: Path, raw_content: str) -> str:
    if not raw_content:
        return path.stem
    if "imported_office" in path.parts:
        sheet_match = re.search(r"^## Sheet \| (.+)$", raw_content, flags=re.MULTILINE)
        if sheet_match:
            return sheet_match.group(1).strip()
        office_match = re.search(r"^# OFFICE Import \| (.+)$", raw_content, flags=re.MULTILINE)
        if office_match:
            return office_match.group(1).strip()
    first_line = raw_content.splitlines()[0].replace("#", "").strip()
    first_line = re.sub(r"^OFFICE Import \|\s*", "", first_line)
    return first_line or path.stem


def build_kb_index(settings: Settings) -> dict:
    documents: list[dict] = []
    chunks: list[dict] = []
    document_frequency: Counter[str] = Counter()

    settings.index_file.parent.mkdir(parents=True, exist_ok=True)
    for path in sorted(settings.kb_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".md", ".txt"}:
            continue
        raw_content = path.read_text(encoding="utf-8")
        doc_type = _infer_doc_type(path)
        doc_title = _extract_doc_title(path, raw_content)
        document_record = {
            "document_id": path.stem,
            "title": doc_title,
            "source": path.name,
            "doc_type": doc_type,
            "path": str(path.relative_to(settings.project_root)),
        }
        documents.append(document_record)

        for index, chunk in enumerate(_chunk_text(raw_content, settings.chunk_size, settings.chunk_overlap)):
            normalized_chunk = normalize_text(chunk)
            counter = to_semantic_counter(chunk)
            document_frequency.update(counter.keys())
            chunks.append(
                {
                    "chunk_id": f"{path.stem}-{index}",
                    "document_id": path.stem,
                    "title": doc_title,
                    "source": path.name,
                    "doc_type": doc_type,
                    "path": str(path.relative_to(settings.project_root)),
                    "text": chunk.strip(),
                    "normalized_text": normalized_chunk,
                    "token_counts": dict(counter),
                    "length": len(chunk.strip()),
                }
            )

    idf = build_idf(document_frequency, len(chunks))

    index_payload = {
        "indexed_at": datetime.now().isoformat(timespec="seconds"),
        "embedding_provider": settings.embedding_provider,
        "embedding_model": settings.embedding_model,
        "documents": documents,
        "chunks": chunks,
        "stats": {
            "total_chunks": len(chunks),
            "document_frequency": dict(document_frequency),
            "idf": idf,
        },
    }
    settings.index_file.write_text(
        json.dumps(index_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return index_payload


def _infer_doc_type(path: Path) -> str:
    if "imported_office" in path.parts:
        return "OFFICE"
    return path.stem.split("-", 1)[0].replace("_", " ").upper()


class Retriever:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._index_cache: dict | None = None

    def ensure_index(self) -> dict:
        if self._index_cache is not None:
            return self._index_cache
        if not self.settings.index_file.exists() or self.settings.auto_rebuild_index:
            self._index_cache = build_kb_index(self.settings)
        else:
            self._index_cache = json.loads(self.settings.index_file.read_text(encoding="utf-8"))
        return self._index_cache

    def list_documents(self) -> list[dict]:
        return self.ensure_index().get("documents", [])

    def rebuild_index(self) -> dict:
        self._index_cache = build_kb_index(self.settings)
        return self._index_cache

    def search(
        self,
        query: str,
        issue_type: str,
        rag_enabled: bool,
        rag_profile: str,
        top_k: int,
        rerank_enabled: bool,
    ) -> list[dict]:
        if not rag_enabled:
            return []

        index_data = self.ensure_index()
        idf = index_data.get("stats", {}).get("idf", {})
        query_counter = to_semantic_counter(query)
        weighted_query = apply_idf(query_counter, idf)
        issue_tokens = set(tokenize(issue_type))
        guidance_query = any(keyword in query for keyword in ["指导", "步骤", "怎么做", "如何", "作业", "流程", "返修", "入库", "收货"])
        results: list[dict] = []

        for chunk in index_data.get("chunks", []):
            chunk_counter = Counter(chunk.get("token_counts", {}))
            weighted_chunk = apply_idf(chunk_counter, idf)
            semantic_score = cosine_similarity(weighted_query, weighted_chunk)
            title_counter = to_semantic_counter(chunk.get("title", ""))
            weighted_title = apply_idf(title_counter, idf)
            title_score = cosine_similarity(weighted_query, weighted_title)
            overlap = len(set(query_counter) & set(chunk_counter))
            score = semantic_score
            score += overlap * 0.018
            score += title_score * 0.55
            if query in chunk.get("title", ""):
                score += 0.4
            if issue_tokens & set(chunk_counter):
                score += 0.08
            if rerank_enabled:
                if issue_type != "一般异常咨询" and issue_type in chunk.get("title", ""):
                    score += 0.1
                if rag_profile == "full" and chunk.get("doc_type") in {"SOP", "RULE", "REG"}:
                    score += 0.05
            raw_text = chunk.get("text", "")
            if guidance_query and chunk.get("doc_type") == "OFFICE":
                if "### 主要步骤" in raw_text:
                    score += 0.18
                if re.search(r"(^|\n)\s*1\.\s", raw_text):
                    score += 0.12
                if "### 关键要点" in raw_text:
                    score += 0.08
            if score <= 0:
                continue
            results.append(
                {
                    "title": chunk["title"],
                    "source": chunk["source"],
                    "doc_type": chunk["doc_type"],
                    "path": chunk.get("path"),
                    "snippet": truncate(raw_text, 220),
                    "raw_text": raw_text,
                    "semantic_score": round(semantic_score, 3),
                    "score": round(score, 3),
                }
            )

        results.sort(key=lambda item: item["score"], reverse=True)
        deduped: list[dict] = []
        seen_entries: set[str] = set()
        for result in results:
            key = f"{result['source']}::{result['snippet']}"
            if key in seen_entries:
                continue
            seen_entries.add(key)
            deduped.append(result)
            if len(deduped) >= top_k:
                break
        probabilities = softmax([item["score"] for item in deduped], temperature=0.18)
        for index, item in enumerate(deduped):
            probability = probabilities[index] if index < len(probabilities) else 0.0
            item["probability"] = round(probability, 3)
            if probability >= 0.55:
                item["confidence"] = "high"
            elif probability >= 0.25:
                item["confidence"] = "medium"
            else:
                item["confidence"] = "low"
        return deduped
