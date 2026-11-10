"""Three-level score of a detector's claims (paper section "Scoring finer than yes or no").

Per circuit, T = the Trojans it holds (one region of cells each, from `regions.py`) and C = the
claims the detector makes (each claim names zero or more cells). The score of one circuit is
|matched| / |C u T| (1 when both are empty); the score at a level is the mean over circuits.

- Level 1, presence: C and T reduced to "at least one". matched = 1 if both are non-empty.
- Level 2, count: matched = min(|C|, |T|), union = max(|C|, |T|).
- Level 3, location: a claim HITS a Trojan when a cell it names lies in that Trojan's region
  (the logic that feeds the victim output with no equal counterpart in the golden). Matching is
  one to one (a claim hits at most one Trojan, a Trojan is hit by at most one claim); matched =
  the largest such matching, union = |C| + |T| - matched.

Cell counts at every level: TP = matched, FP = |C| - matched, FN = |T| - matched, TN = a clean
circuit with no claim. At level 1 these are circuit counts. s3 <= s2 <= s1 per circuit.

Chance control: the same claims with no information, i.e. the claim lists permuted among the
circuits of one base and every named cell redrawn at random from the circuit's cells (the number
of cells per claim kept). Its expected score is computed per circuit; the label compares the
detector's mean with that expectation (bootstrap over bases), per the CAD reporting convention:
ABOVE CHANCE when the interval of the paired difference lies above 0, BELOW CHANCE when below,
INCONCLUSIVE when it touches 0.
"""

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

LEVELS = (1, 2, 3)


@dataclass(frozen=True)
class Circ:
    """One scored circuit. `regions` holds one cell set per true Trojan (empty = clean).
    `claims` holds the cells each claim names. `n_cells` is the number of cells of the circuit
    (used only by the chance control)."""

    cid: str
    base: str
    regions: tuple[frozenset[str], ...]
    claims: tuple[frozenset[str], ...]
    n_cells: int = 0


def max_matching(claims: Sequence[frozenset[str]], regions: Sequence[frozenset[str]]) -> int:
    """Size of the largest one-to-one matching of claims to Trojans, an edge being a claim
    naming a cell of the Trojan's region (augmenting paths; sizes are tiny)."""
    adj = [[j for j, r in enumerate(regions) if c & r] for c in claims]
    owner: dict[int, int] = {}

    def try_claim(i: int, seen: set[int]) -> bool:
        for j in adj[i]:
            if j in seen:
                continue
            seen.add(j)
            if j not in owner or try_claim(owner[j], seen):
                owner[j] = i
                return True
        return False

    return sum(1 for i in range(len(claims)) if try_claim(i, set()))


def matched(c: Circ, level: int) -> int:
    n_c, n_t = len(c.claims), len(c.regions)
    if level == 1:
        return 1 if n_c and n_t else 0
    if level == 2:
        return min(n_c, n_t)
    return max_matching(c.claims, c.regions)


def union(c: Circ, level: int) -> int:
    n_c, n_t = len(c.claims), len(c.regions)
    if level == 1:
        return 1 if n_c or n_t else 0
    if level == 2:
        return max(n_c, n_t)
    return n_c + n_t - matched(c, 3)


def circuit_score(c: Circ, level: int) -> float:
    u = union(c, level)
    return 1.0 if u == 0 else matched(c, level) / u


@dataclass(frozen=True)
class Cells:
    tp: int
    fp: int
    fn: int
    tn: int


def cells(circs: Sequence[Circ], level: int) -> Cells:
    tp = fp = fn = tn = 0
    for c in circs:
        n_c, n_t = len(c.claims), len(c.regions)
        if level == 1:
            n_c, n_t = min(n_c, 1), min(n_t, 1)
        m = matched(c, level)
        tp += m
        fp += n_c - m
        fn += n_t - m
        tn += 1 if (n_t == 0 and n_c == 0) else 0
    return Cells(tp, fp, fn, tn)


def mean_score(circs: Sequence[Circ], level: int) -> float | None:
    return sum(circuit_score(c, level) for c in circs) / len(circs) if circs else None


# ---- chance control -----------------------------------------------------------------------

def _random_claim_score(c: Circ, sizes: Sequence[int], rng: random.Random) -> tuple[float, ...]:
    """(s1, s2, s3) of circuit `c` when it carries claims of the given sizes at random cells."""
    n_c, n_t = len(sizes), len(c.regions)
    s1 = 1.0 if bool(n_c) == bool(n_t) else 0.0
    s2 = 1.0 if max(n_c, n_t) == 0 else min(n_c, n_t) / max(n_c, n_t)
    if n_t == 0 or n_c == 0:
        return s1, s2, 1.0 if n_c == n_t else 0.0
    index: dict[str, int] = {}
    for r in c.regions:
        for x in r:
            index.setdefault(x, len(index))
    n = max(c.n_cells, len(index))
    rand = [frozenset(str(i) for i in rng.sample(range(n), min(m, n))) for m in sizes]
    reg = [frozenset(str(index[x]) for x in r) for r in c.regions]
    m3 = max_matching(rand, reg)
    return s1, s2, m3 / (n_c + n_t - m3)


def chance_expectation(circs: Sequence[Circ], reps: int = 30, seed: int = 0
                       ) -> dict[str, tuple[float, float, float]]:
    """Per circuit, expected (s1, s2, s3) of the chance control (see module doc)."""
    rng = random.Random(seed)
    by_base: dict[str, list[Circ]] = defaultdict(list)
    for c in circs:
        by_base[c.base].append(c)
    acc = {c.cid: [0.0, 0.0, 0.0] for c in circs}
    for _ in range(reps):
        for group in by_base.values():
            sizes = [tuple(len(x) for x in c.claims) for c in group]
            rng.shuffle(sizes)
            for c, sz in zip(group, sizes, strict=True):
                for k, v in enumerate(_random_claim_score(c, sz, rng)):
                    acc[c.cid][k] += v
    return {k: (a / reps, b / reps, d / reps) for k, (a, b, d) in acc.items()}


# ---- aggregation --------------------------------------------------------------------------

def label(lo: float, hi: float) -> str:
    return "ABOVE CHANCE" if lo > 0 else "BELOW CHANCE" if hi < 0 else "INCONCLUSIVE"


def _ci(units: list[tuple[float, int]], reps: int, seed: int) -> tuple[float, float]:
    """Percentile interval of sum/count over bases resampled with replacement."""
    rng = random.Random(seed)
    vals = []
    for _ in range(reps):
        pick = [units[rng.randrange(len(units))] for _ in units]
        n = sum(k for _, k in pick)
        vals.append(sum(s for s, _ in pick) / n if n else 0.0)
    vals.sort()
    return vals[int(0.025 * (len(vals) - 1))], vals[int(round(0.975 * (len(vals) - 1)))]


def summarise(circs: Sequence[Circ], chance: dict[str, tuple[float, float, float]],
              reps: int = 1000, seed: int = 7) -> dict[int, dict[str, Any]]:
    """Per level: mean score with 95% interval over bases, chance mean, W/L/T over bases
    (detector base mean against the chance expectation of the base), label, cell counts."""
    out: dict[int, dict[str, Any]] = {}
    bases = sorted({c.base for c in circs})
    for lv in LEVELS:
        s = {c.cid: circuit_score(c, lv) for c in circs}
        e = {c.cid: chance[c.cid][lv - 1] for c in circs}
        units_s: list[tuple[float, int]] = []
        units_d: list[tuple[float, int]] = []
        w = lo = t = 0
        for b in bases:
            ids = [c.cid for c in circs if c.base == b]
            units_s.append((sum(s[i] for i in ids), len(ids)))
            units_d.append((sum(s[i] - e[i] for i in ids), len(ids)))
            diff = sum(s[i] - e[i] for i in ids) / len(ids)
            if abs(diff) < 1e-9:
                t += 1
            elif diff > 0:
                w += 1
            else:
                lo += 1
        n = len(circs)
        ci = _ci(units_s, reps, seed + lv)
        di = _ci(units_d, reps, seed + 10 + lv)
        cl = cells(circs, lv)
        out[lv] = {"mean": sum(s.values()) / n, "ci": ci,
                   "chance": sum(e.values()) / n, "diff_ci": di, "wlt": (w, lo, t),
                   "label": label(*di), "n": n,
                   "tp": cl.tp, "fp": cl.fp, "fn": cl.fn, "tn": cl.tn}
    return out
