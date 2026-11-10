"""Information bound for the adaptive-attacker analysis (spec section 6)."""

from __future__ import annotations

from math import comb, log2


def channel(n: int, sample: int, group: int) -> list[list[float]]:
    """P(Y = y | K = k): Y infected circuits seen in a sample of `sample` of `n`, K in the group."""
    return [[comb(k, y) * comb(n - k, sample - y) / comb(n, sample)
             if 0 <= y <= k and 0 <= sample - y <= n - k else 0.0
             for y in range(sample + 1)] for k in range(group + 1)]


def capacity(p: list[list[float]], iters: int = 300) -> float:
    """Channel capacity in bits (Blahut-Arimoto)."""
    m, ny = len(p), len(p[0])
    r = [1.0 / m] * m
    for _ in range(iters):
        q = [sum(r[i] * p[i][y] for i in range(m)) for y in range(ny)]
        w = [r[i] * 2 ** sum(p[i][y] * log2(p[i][y] / q[y]) for y in range(ny) if p[i][y] > 0)
             for i in range(m)]
        s = sum(w)
        r = [x / s for x in w]
    q = [sum(r[i] * p[i][y] for i in range(m)) for y in range(ny)]
    return sum(r[i] * p[i][y] * log2(p[i][y] / q[y])
               for i in range(m) for y in range(ny) if p[i][y] > 0)


def count_capacity(n: int, sample: int) -> float:
    return capacity(channel(n, sample, n))


def bits_per_query(n: int, sample: int, n_counts: int = 5, matrix_cells: int = 12,
                   round_step: int = 5) -> float:
    """Upper bound on key information per report: `n_counts` sampled counts, the count matrix
    cells rounded to `round_step`, and AUROC at two decimals (log2 101 bits)."""
    c = count_capacity(n, sample)
    cell = max(0.0, c - log2(round_step))
    return n_counts * c + matrix_cells * cell + log2(101)


def min_queries(k: int, bits: float, h: float = 0.9) -> int:
    """Smallest number of queries that could carry k labels of entropy h each."""
    q = k * h / bits
    return int(q) + (0 if q == int(q) else 1)
