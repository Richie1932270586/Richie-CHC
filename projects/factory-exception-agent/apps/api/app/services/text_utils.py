from __future__ import annotations

import math
import re
from collections import Counter


WORD_RE = re.compile(r"[A-Za-z0-9_-]+|[\u4e00-\u9fff]+")


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for match in WORD_RE.findall(normalize_text(text)):
        if re.fullmatch(r"[\u4e00-\u9fff]+", match):
            tokens.extend(list(match))
            if len(match) > 1:
                tokens.extend(match[idx : idx + 2] for idx in range(len(match) - 1))
            tokens.append(match)
        else:
            tokens.append(match)
    return [token for token in tokens if token]


def to_counter(text: str) -> Counter[str]:
    return Counter(tokenize(text))


def semantic_tokenize(text: str) -> list[str]:
    normalized = normalize_text(text)
    base_tokens = tokenize(text)
    compact = normalized.replace(" ", "")
    ngrams: list[str] = []
    for size in (2, 3):
        if len(compact) < size:
            continue
        ngrams.extend(compact[index : index + size] for index in range(len(compact) - size + 1))
    return [token for token in [*base_tokens, *ngrams] if token]


def to_semantic_counter(text: str) -> Counter[str]:
    return Counter(semantic_tokenize(text))


def cosine_similarity(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    numerator = sum(left[token] * right.get(token, 0) for token in left)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def build_idf(document_frequency: Counter[str], total_documents: int) -> dict[str, float]:
    if total_documents <= 0:
        return {}
    return {
        token: math.log((1 + total_documents) / (1 + frequency)) + 1.0
        for token, frequency in document_frequency.items()
    }


def apply_idf(counter: Counter[str], idf: dict[str, float]) -> Counter[str]:
    weighted = Counter()
    for token, value in counter.items():
        weighted[token] = value * idf.get(token, 1.0)
    return weighted


def softmax(values: list[float], temperature: float = 1.0) -> list[float]:
    if not values:
        return []
    if temperature <= 0:
        temperature = 1.0
    scaled = [value / temperature for value in values]
    max_value = max(scaled)
    exponents = [math.exp(value - max_value) for value in scaled]
    total = sum(exponents)
    if total == 0:
        return [0.0 for _ in values]
    return [value / total for value in exponents]


def truncate(text: str, max_length: int = 180) -> str:
    if len(text) <= max_length:
        return text
    return text[: max_length - 3].rstrip() + "..."
