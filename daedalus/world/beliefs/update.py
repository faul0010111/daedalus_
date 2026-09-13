"""Evidence accumulation in log-odds space."""
from __future__ import annotations

import math

EPS_LOW, EPS_HIGH = 0.005, 0.995


def logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def update(confidence: float, positive: bool, reliability: float) -> float:
    reliability = min(max(reliability, 0.51), 0.999)
    delta = logit(reliability)
    lo = logit(confidence) + (delta if positive else -delta)
    return min(max(sigmoid(lo), EPS_LOW), EPS_HIGH)


def binary_entropy(p: float) -> float:
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return -(p * math.log2(p) + (1 - p) * math.log2(1 - p))
