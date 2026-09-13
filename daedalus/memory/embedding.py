"""Dependency-free embeddings and vector index.

`HashingEmbedder` is deterministic and good enough for similarity over short
cognitive descriptions. The `VectorIndex` protocol is the seam for pgvector,
Qdrant, etc.
"""
from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

_TOKEN = re.compile(r"[a-z0-9_]+")


class Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...


class HashingEmbedder:
    def __init__(self, dim: int = 128) -> None:
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        tokens = _TOKEN.findall(text.lower())
        grams = tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
        for g in grams:
            h = int.from_bytes(hashlib.blake2b(g.encode(), digest_size=8).digest(), "little")
            vec[h % self.dim] += 1.0 if (h >> 32) & 1 else -1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class VectorIndex(Protocol):
    def add(self, item_id: str, vector: list[float]) -> None: ...
    def search(self, vector: list[float], k: int) -> list[tuple[str, float]]: ...
    def remove(self, item_id: str) -> None: ...


class InMemoryVectorIndex:
    def __init__(self) -> None:
        self._vectors: dict[str, list[float]] = {}

    def add(self, item_id: str, vector: list[float]) -> None:
        self._vectors[item_id] = vector

    def remove(self, item_id: str) -> None:
        self._vectors.pop(item_id, None)

    def search(self, vector: list[float], k: int = 5) -> list[tuple[str, float]]:
        scored = [(i, sum(a * b for a, b in zip(vector, v))) for i, v in self._vectors.items()]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]

    def __len__(self) -> int:
        return len(self._vectors)
