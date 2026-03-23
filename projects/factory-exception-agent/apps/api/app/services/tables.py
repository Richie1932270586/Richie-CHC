from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from app.core.config import Settings


class TableService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _read_csv(self, path: Path) -> list[dict[str, str]]:
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            return list(csv.DictReader(file))

    def _read_json(self, path: Path) -> dict:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def extract_entities(self, message: str) -> dict[str, str | None]:
        batch_match = re.search(r"\b([A-Z]\d{6,})\b", message)
        item_code_match = re.search(r"\b([A-Z]{1,3}-?\d{2,4})\b", message)

        inventory_rows = self._read_csv(self.settings.inventory_file)
        matched_item_name = None
        for row in inventory_rows:
            item_name = row.get("item_name", "")
            if item_name and item_name in message:
                matched_item_name = item_name
                break

        return {
            "batch_no": batch_match.group(1) if batch_match else None,
            "item_code": item_code_match.group(1) if item_code_match else None,
            "item_name": matched_item_name,
        }

    def query_inventory(self, message: str) -> list[dict[str, str]]:
        entities = self.extract_entities(message)
        rows = self._read_csv(self.settings.inventory_file)
        results: list[dict[str, str]] = []
        for row in rows:
            if entities["item_code"] and row.get("item_code") == entities["item_code"]:
                results.append(row)
                continue
            if entities["item_name"] and row.get("item_name") == entities["item_name"]:
                results.append(row)
                continue
            if entities["batch_no"] and row.get("batch_no") == entities["batch_no"]:
                results.append(row)
        return results[:3]

    def query_incidents(self, issue_type: str, message: str) -> list[dict[str, str]]:
        entities = self.extract_entities(message)
        rows = self._read_csv(self.settings.incidents_file)
        results: list[dict[str, str]] = []
        for row in rows:
            if issue_type != "一般异常咨询" and row.get("issue_type") == issue_type:
                results.append(row)
                continue
            if entities["item_code"] and row.get("item_code") == entities["item_code"]:
                results.append(row)
                continue
            if entities["batch_no"] and row.get("batch_no") == entities["batch_no"]:
                results.append(row)
        return results[:3]

    def query_owner(self, issue_type: str) -> list[dict[str, str]]:
        rows = self._read_csv(self.settings.owners_file)
        return [row for row in rows if row.get("issue_type") == issue_type][:2]

    def get_ticket_template(self, action_type: str) -> dict:
        templates = self._read_json(self.settings.ticket_templates_file)
        return templates.get(action_type, {})
