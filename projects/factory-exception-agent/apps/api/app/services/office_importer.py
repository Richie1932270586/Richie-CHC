from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from app.core.config import Settings
from app.services.retriever import Retriever


logger = logging.getLogger(__name__)

DOCX_NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
}
XLSX_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}
PPTX_NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _normalize_block(text: str) -> str:
    normalized = text.replace("\x00", " ")
    normalized = re.sub(r"\r\n?", "\n", normalized)
    normalized = re.sub(r"[ \t]+\n", "\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _hash_text(value: str, length: int = 12) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:length]


def _split_cell_ref(cell_ref: str) -> tuple[str, int] | tuple[None, None]:
    match = re.fullmatch(r"([A-Z]+)(\d+)", cell_ref or "")
    if not match:
        return None, None
    return match.group(1), int(match.group(2))


def _column_index(column: str) -> int:
    value = 0
    for char in column:
        value = value * 26 + (ord(char) - ord("A") + 1)
    return value


def _column_from_index(index: int) -> str:
    letters: list[str] = []
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        letters.append(chr(ord("A") + remainder))
    return "".join(reversed(letters))


class OfficeImportService:
    SUPPORTED_EXTENSIONS = {".docx", ".xlsx", ".pptx"}

    def __init__(self, settings: Settings, retriever: Retriever) -> None:
        self.settings = settings
        self.retriever = retriever

    def list_imports(self) -> dict:
        manifest = self._load_manifest()
        return {
            "supported_extensions": sorted(self.SUPPORTED_EXTENSIONS),
            "imported_kb_dir": str(self.settings.imported_kb_dir.relative_to(self.settings.project_root)),
            "manifest_file": str(self.settings.import_manifest_file.relative_to(self.settings.project_root)),
            "imports": manifest.get("imports", []),
        }

    def import_folder(
        self,
        source_dir: str,
        replace_existing: bool = True,
        recursive: bool = True,
    ) -> dict:
        source_path = Path(source_dir).expanduser()
        if not source_path.exists():
            raise ValueError(f"目录不存在：{source_dir}")
        if not source_path.is_dir():
            raise ValueError(f"不是文件夹：{source_dir}")

        resolved_source = source_path.resolve()
        source_id = _hash_text(str(resolved_source))
        target_dir = self.settings.imported_kb_dir / source_id
        pattern = "**/*" if recursive else "*"
        source_files = sorted(
            path
            for path in resolved_source.glob(pattern)
            if path.is_file()
            and path.suffix.lower() in self.SUPPORTED_EXTENSIONS
            and not path.name.startswith("~$")
        )
        if replace_existing and target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        imported_files: list[dict] = []
        skipped_files: list[dict] = []
        failed_files: list[dict] = []

        for source_file in source_files:
            relative_source = str(source_file.relative_to(resolved_source))
            try:
                extracted_documents = self._extract_documents(source_file)
                if not extracted_documents:
                    skipped_files.append(
                        self._record(
                            source_file=source_file,
                            title=source_file.stem,
                            extension=source_file.suffix.lower(),
                            status="skipped",
                            detail="文件可读取，但未提取到有效文本。",
                        )
                    )
                    continue

                for document in extracted_documents:
                    title = document["title"]
                    doc_hash = _hash_text(f"{relative_source}:{title}")
                    output_name = f"OFFICE-{source_file.suffix.lower().lstrip('.')}-{doc_hash}.md"
                    output_path = target_dir / output_name
                    output_path.write_text(
                        self._render_markdown(
                            title=title,
                            source_root=resolved_source,
                            source_file=source_file,
                            extracted_text=document["content"],
                        ),
                        encoding="utf-8",
                    )
                    imported_files.append(
                        self._record(
                            source_file=source_file,
                            title=title,
                            extension=source_file.suffix.lower(),
                            status="imported",
                            output_file=output_path,
                        )
                    )
            except Exception as exc:
                logger.warning("Failed to import %s: %s", source_file, exc)
                failed_files.append(
                    self._record(
                        source_file=source_file,
                        title=source_file.stem,
                        extension=source_file.suffix.lower(),
                        status="failed",
                        detail=str(exc),
                    )
                )

        index_payload = self.retriever.rebuild_index()
        manifest = self._load_manifest()
        manifest_imports = [
            item for item in manifest.get("imports", []) if item.get("source_id") != source_id
        ]
        manifest_imports.insert(
            0,
            {
                "source_id": source_id,
                "source_dir": str(resolved_source),
                "target_dir": str(target_dir.relative_to(self.settings.project_root)),
                "imported_at": datetime.now().isoformat(timespec="seconds"),
                "replace_existing": replace_existing,
                "recursive": recursive,
                "scanned_files": len(source_files),
                "imported_files": imported_files,
                "skipped_files": skipped_files,
                "failed_files": failed_files,
            },
        )
        self._save_manifest({"updated_at": datetime.now().isoformat(timespec="seconds"), "imports": manifest_imports})

        return {
            "source_dir": str(resolved_source),
            "source_id": source_id,
            "target_dir": str(target_dir.relative_to(self.settings.project_root)),
            "scanned_files": len(source_files),
            "imported_files": imported_files,
            "skipped_files": skipped_files,
            "failed_files": failed_files,
            "index_file": str(self.settings.index_file.relative_to(self.settings.project_root)),
            "total_indexed_documents": len(index_payload.get("documents", [])),
            "total_indexed_chunks": len(index_payload.get("chunks", [])),
            "message": (
                f"导入完成：扫描 {len(source_files)} 个 Office 文件，成功 {len(imported_files)} 个，"
                f"跳过 {len(skipped_files)} 个，失败 {len(failed_files)} 个。"
            ),
        }

    def _render_markdown(
        self,
        title: str,
        source_root: Path,
        source_file: Path,
        extracted_text: str,
    ) -> str:
        imported_at = datetime.now().isoformat(timespec="seconds")
        return "\n".join(
            [
                f"# OFFICE Import | {title}",
                "",
                f"- Source Root: {source_root}",
                f"- Source File: {source_file}",
                f"- File Type: {source_file.suffix.lower()}",
                f"- Imported At: {imported_at}",
                "",
                "## Extracted Content",
                "",
                extracted_text,
                "",
            ]
        )

    def _record(
        self,
        source_file: Path,
        title: str,
        extension: str,
        status: str,
        output_file: Path | None = None,
        detail: str | None = None,
    ) -> dict:
        return {
            "source_file": str(source_file),
            "output_file": (
                str(output_file.relative_to(self.settings.project_root)) if output_file else None
            ),
            "title": title,
            "extension": extension,
            "status": status,
            "detail": detail,
        }

    def _load_manifest(self) -> dict:
        if not self.settings.import_manifest_file.exists():
            return {"updated_at": None, "imports": []}
        return json.loads(self.settings.import_manifest_file.read_text(encoding="utf-8"))

    def _save_manifest(self, payload: dict) -> None:
        self.settings.import_manifest_file.parent.mkdir(parents=True, exist_ok=True)
        self.settings.import_manifest_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _extract_documents(self, source_file: Path) -> list[dict]:
        extension = source_file.suffix.lower()
        if extension == ".docx":
            text = self._extract_docx_text(source_file)
            return [{"title": source_file.stem, "content": text}] if text else []
        if extension == ".xlsx":
            return self._extract_xlsx_documents(source_file)
        if extension == ".pptx":
            text = self._extract_pptx_text(source_file)
            return [{"title": source_file.stem, "content": text}] if text else []
        raise ValueError(f"暂不支持的文件类型：{extension}")

    def _extract_docx_text(self, source_file: Path) -> str:
        with zipfile.ZipFile(source_file) as archive:
            root = ET.fromstring(archive.read("word/document.xml"))
        paragraphs: list[str] = []
        for paragraph in root.findall(".//w:p", DOCX_NS):
            pieces: list[str] = []
            for node in paragraph.iter():
                name = _local_name(node.tag)
                if name == "t" and node.text:
                    pieces.append(node.text)
                elif name == "tab":
                    pieces.append("\t")
                elif name in {"br", "cr"}:
                    pieces.append("\n")
            text = _normalize_block("".join(pieces))
            if text:
                paragraphs.append(text)
        return "\n\n".join(paragraphs)

    def _extract_xlsx_documents(self, source_file: Path) -> list[dict]:
        with zipfile.ZipFile(source_file) as archive:
            shared_strings = self._load_shared_strings(archive)
            sheet_entries = self._load_sheet_entries(archive)
            documents: list[dict] = []
            for sheet_name, target in sheet_entries:
                if target not in archive.namelist():
                    continue
                root = ET.fromstring(archive.read(target))
                rows = self._xlsx_rows(root, shared_strings)
                rendered_sheet = self._render_xlsx_sheet(sheet_name, rows)
                if not rendered_sheet or self._should_skip_sheet(sheet_name, rendered_sheet):
                    continue
                documents.append(
                    {
                        "title": self._sheet_title_from_rendered(rendered_sheet) or sheet_name,
                        "content": rendered_sheet,
                    }
                )
        return documents

    def _xlsx_rows(self, root: ET.Element, shared_strings: list[str]) -> list[dict]:
        rows: list[dict] = []
        for row in root.findall(".//main:sheetData/main:row", XLSX_NS):
            cell_values: dict[str, str] = {}
            for cell in row.findall("main:c", XLSX_NS):
                rendered = self._xlsx_cell_value(cell, shared_strings)
                if not rendered:
                    continue
                column, row_number = _split_cell_ref(cell.attrib.get("r", ""))
                if not column or row_number is None:
                    continue
                cell_values[column] = rendered
            if cell_values:
                rows.append(
                    {
                        "row_number": int(row.attrib.get("r", "0") or 0),
                        "cells": cell_values,
                    }
                )
        return rows

    def _render_xlsx_sheet(self, sheet_name: str, rows: list[dict]) -> str:
        if not rows:
            return ""
        if rendered := self._render_job_element_sheet(sheet_name, rows):
            return rendered
        return self._render_generic_sheet(sheet_name, rows)

    def _render_job_element_sheet(self, sheet_name: str, rows: list[dict]) -> str | None:
        header_row = None
        step_column = None
        how_column = None
        reason_column = None
        for row in rows:
            cells = row["cells"]
            for column, value in cells.items():
                normalized = value.lower()
                if "主要步骤" in value or "major step" in normalized:
                    header_row = row
                    step_column = column
                if "关键要素" in value or "key point" in normalized:
                    how_column = column
                if "理由" in value or "reason" in normalized:
                    reason_column = column
            if header_row and step_column:
                break
        if not header_row or not step_column:
            return None

        step_no_column = _column_from_index(max(_column_index(step_column) - 1, 1))
        title = self._pick_sheet_title(sheet_name, rows)
        document_no = self._cell_value(rows, 7, "D")
        version = self._cell_value(rows, 7, "P")
        job_role = self._cell_value(rows, 8, "D")
        equipment = self._cell_value(rows, 8, "K")

        lines = [f"## Sheet | {title}", ""]
        if document_no or version or job_role or equipment:
            lines.append("### 基本信息")
            if document_no:
                lines.append(f"- 指导书号：{document_no}")
            if version:
                lines.append(f"- 版本号：{version}")
            if job_role:
                lines.append(f"- 岗位：{job_role}")
            if equipment:
                lines.append(f"- 操作设备：{equipment}")
            lines.append("")

        step_lines: list[str] = []
        key_points: list[str] = []
        reasons: list[str] = []
        sequence = 1
        for row in rows:
            if row["row_number"] <= header_row["row_number"]:
                continue
            cells = row["cells"]
            if any("编制人" in value or "修定记录" in value or "修订记录" in value for value in cells.values()):
                break
            step_text = (cells.get(step_column) or "").strip()
            if not step_text:
                continue
            step_no = (cells.get(step_no_column) or str(sequence)).strip()
            how_text = (cells.get(how_column) or "").strip() if how_column else ""
            reason_text = (cells.get(reason_column) or "").strip() if reason_column else ""

            step_lines.append(f"{step_no}. {step_text}")
            if how_text:
                key_points.append(f"{step_no}. {how_text}")
            if reason_text:
                reasons.append(f"{step_no}. {reason_text}")
            sequence += 1

        if not step_lines:
            return None

        lines.append("### 主要步骤")
        for item in step_lines:
            lines.append(item)
            lines.append("")
        lines.append("")
        if key_points:
            lines.append("### 关键要点")
            for item in key_points:
                lines.append(f"- {item}")
                lines.append("")
            lines.append("")
        if reasons:
            lines.append("### 理由说明")
            for item in reasons:
                lines.append(f"- {item}")
                lines.append("")
            lines.append("")
        return "\n".join(lines).strip()

    def _render_generic_sheet(self, sheet_name: str, rows: list[dict]) -> str:
        title = self._pick_sheet_title(sheet_name, rows)
        lines = [f"## Sheet | {title}", ""]
        for row in rows:
            rendered = self._render_generic_row(row["cells"])
            if rendered:
                lines.append(rendered)
                lines.append("")
        return "\n".join(lines).strip()

    def _render_generic_row(self, cells: dict[str, str]) -> str:
        ordered_values = [value for _, value in sorted(cells.items(), key=lambda item: _column_index(item[0])) if value]
        return " | ".join(ordered_values).strip()

    def _pick_sheet_title(self, sheet_name: str, rows: list[dict]) -> str:
        for row in rows:
            if row["row_number"] not in {5, 7}:
                continue
            ordered_values = [value for _, value in sorted(row["cells"].items(), key=lambda item: _column_index(item[0]))]
            for value in ordered_values:
                if any(keyword in value for keyword in ["作业指导书", "岗位指导书", "返修", "收货", "入库", "出库"]):
                    return value
        return sheet_name

    def _cell_value(self, rows: list[dict], row_number: int, column: str) -> str:
        for row in rows:
            if row["row_number"] == row_number:
                return (row["cells"].get(column) or "").strip()
        return ""

    def _sheet_title_from_rendered(self, rendered_sheet: str) -> str:
        first_line = rendered_sheet.splitlines()[0].strip()
        prefix = "## Sheet | "
        if first_line.startswith(prefix):
            return first_line[len(prefix) :].strip()
        return first_line

    def _should_skip_sheet(self, sheet_name: str, rendered_sheet: str) -> bool:
        normalized_name = sheet_name.strip().lower()
        if any(keyword in normalized_name for keyword in ["目录", "封面", "cover", "index"]):
            return True
        first_line = self._sheet_title_from_rendered(rendered_sheet)
        return any(keyword in first_line for keyword in ["目录", "封面"])

    def _load_shared_strings(self, archive: zipfile.ZipFile) -> list[str]:
        if "xl/sharedStrings.xml" not in archive.namelist():
            return []
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        strings: list[str] = []
        for item in root.findall(".//main:si", XLSX_NS):
            texts = [node.text or "" for node in item.findall(".//main:t", XLSX_NS)]
            strings.append("".join(texts).strip())
        return strings

    def _load_sheet_entries(self, archive: zipfile.ZipFile) -> list[tuple[str, str]]:
        if "xl/workbook.xml" not in archive.namelist():
            return []
        workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
        rel_targets: dict[str, str] = {}
        rels_name = "xl/_rels/workbook.xml.rels"
        if rels_name in archive.namelist():
            rels_root = ET.fromstring(archive.read(rels_name))
            for relation in rels_root.findall(".//rel:Relationship", XLSX_NS):
                target = relation.attrib.get("Target", "")
                if target and not target.startswith("xl/"):
                    target = f"xl/{target.lstrip('/')}"
                rel_targets[relation.attrib.get("Id", "")] = target

        entries: list[tuple[str, str]] = []
        for sheet in workbook_root.findall(".//main:sheets/main:sheet", XLSX_NS):
            name = sheet.attrib.get("name", "Sheet")
            rel_id = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", "")
            target = rel_targets.get(rel_id)
            if target:
                entries.append((name, target))
        return entries

    def _xlsx_cell_value(self, cell: ET.Element, shared_strings: list[str]) -> str:
        cell_type = cell.attrib.get("t", "")
        value_node = cell.find("main:v", XLSX_NS)
        formula_node = cell.find("main:f", XLSX_NS)
        inline_texts = [node.text or "" for node in cell.findall(".//main:is/main:t", XLSX_NS)]

        if cell_type == "s" and value_node is not None and value_node.text:
            index = int(value_node.text)
            return shared_strings[index].strip() if index < len(shared_strings) else ""
        if cell_type == "inlineStr" and inline_texts:
            return "".join(inline_texts).strip()
        if value_node is not None and value_node.text:
            return value_node.text.strip()
        if formula_node is not None and formula_node.text:
            return f"FORMULA={formula_node.text.strip()}"
        return ""

    def _extract_pptx_text(self, source_file: Path) -> str:
        with zipfile.ZipFile(source_file) as archive:
            slide_names = sorted(
                name
                for name in archive.namelist()
                if name.startswith("ppt/slides/slide") and name.endswith(".xml")
            )
            sections: list[str] = []
            for index, slide_name in enumerate(slide_names, start=1):
                root = ET.fromstring(archive.read(slide_name))
                texts = [
                    (node.text or "").strip()
                    for node in root.findall(".//a:t", PPTX_NS)
                    if (node.text or "").strip()
                ]
                if texts:
                    sections.append(f"## Slide {index}\n\n" + "\n".join(texts))
        return "\n\n".join(sections)
