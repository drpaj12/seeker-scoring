"""Detection metrics: confusion matrix, rates, AUROC and a bootstrap interval over bases."""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Confusion:
    tp: int
    fp: int
    tn: int
    fn: int

    @staticmethod
    def of(pairs: list[tuple[int, int]]) -> Confusion:
        """`pairs` are (true, predicted) with 1 = infected."""
        return Confusion(
            sum(1 for t, p in pairs if t and p), sum(1 for t, p in pairs if not t and p),
            sum(1 for t, p in pairs if not t and not p), sum(1 for t, p in pairs if t and not p))


def ratio(a: float, b: float) -> float | None:
    return a / b if b else None


def rates(c: Confusion) -> dict[str, float | None]:
    prec = ratio(c.tp, c.tp + c.fp)
    tpr = ratio(c.tp, c.tp + c.fn)
    f1 = ratio(2 * c.tp, 2 * c.tp + c.fp + c.fn)
    return {"tpr": tpr, "fpr": ratio(c.fp, c.fp + c.tn), "precision": prec, "f1": f1,
            "accuracy": ratio(c.tp + c.tn, c.tp + c.fp + c.tn + c.fn)}


def auroc(pairs: list[tuple[int, float]]) -> float | None:
    """Mann-Whitney AUROC; ties count one half. `pairs` are (true, score)."""
    order = sorted(pairs, key=lambda x: x[1])
    n_pos = sum(1 for t, _ in order if t)
    n_neg = len(order) - n_pos
    if not n_pos or not n_neg:
        return None
    rank_sum = 0.0
    i = 0
    while i < len(order):
        j = i
        while j < len(order) and order[j][1] == order[i][1]:
            j += 1
        avg = (i + 1 + j) / 2
        rank_sum += avg * sum(1 for t, _ in order[i:j] if t)
        i = j
    return (rank_sum - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def bootstrap_auroc(
    by_base: dict[str, list[tuple[int, float]]], seed: int, reps: int = 1000
) -> tuple[float, float] | None:
    """95 % percentile interval, resampling bases (not circuits) with replacement."""
    bases = sorted(by_base)
    if len(bases) < 2:
        return None
    rng = random.Random(seed)
    vals: list[float] = []
    for _ in range(reps):
        pairs = [p for b in (rng.choice(bases) for _ in bases) for p in by_base[b]]
        a = auroc(pairs)
        if a is not None:
            vals.append(a)
    if len(vals) < reps // 2:
        return None
    vals.sort()
    return vals[int(0.025 * (len(vals) - 1))], vals[int(round(0.975 * (len(vals) - 1)))]
