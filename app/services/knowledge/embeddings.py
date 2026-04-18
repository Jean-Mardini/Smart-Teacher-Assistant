"""Embedding generation utilities for RAG.

This project uses a lightweight local tokenizer + cosine similarity fallback so
chat can work without an external embedding API.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, Iterable, List


TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def tokenize(text: str) -> List[str]:
    return [token.lower() for token in TOKEN_RE.findall(text or "")]


def embed_text(text: str) -> Dict[str, float]:
    counts = Counter(tokenize(text))
    if not counts:
        return {}

    norm = math.sqrt(sum(value * value for value in counts.values()))
    return {token: value / norm for token, value in counts.items()}


def embed_texts(texts: Iterable[str]) -> List[Dict[str, float]]:
    return [embed_text(text) for text in texts]


def cosine_similarity(left: Dict[str, float], right: Dict[str, float]) -> float:
    if not left or not right:
        return 0.0

    if len(left) > len(right):
        left, right = right, left

    return sum(value * right.get(token, 0.0) for token, value in left.items())
