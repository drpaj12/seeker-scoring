"""Rate-limit ledger: a JSON-lines file the scorer reads and appends. Private, beside the key.

Quotas per submitter and release (spec 3.4): 1 per 24 hours (any unit), 10 in total, 3 per
benchmark (cell and benchmark units together) and 3 family bundles.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

WINDOW_S = 24 * 3600
MAX_TOTAL = 10
MAX_PER_BENCHMARK = 3
MAX_FAMILY = 3

UNIT_CELL = "cell"
UNIT_BENCHMARK = "benchmark"
UNIT_FAMILY = "family"


class RateLimitError(RuntimeError):
    """The submitter used up a quota; the message says when to retry, where that helps."""


@dataclass(frozen=True)
class Limits:
    window_s: int = WINDOW_S
    max_total: int = MAX_TOTAL
    max_per_benchmark: int = MAX_PER_BENCHMARK
    max_family: int = MAX_FAMILY


def _entries(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def check(path: Path, submitter: str, release: str, now: float,
          lim: Limits | None = None, unit: str = UNIT_CELL,
          benchmark: str | None = None) -> None:
    """Raise RateLimitError when one more submission of this unit would break a quota."""
    lim = lim or Limits()
    mine = [e for e in _entries(path) if e["submitter"] == submitter and e["release"] == release]
    if mine:
        last = max(float(str(e["t"])) for e in mine)
        if now - last < lim.window_s:
            wait = int(lim.window_s - (now - last))
            raise RateLimitError(
                f"one submission per {lim.window_s // 3600} h: retry in {wait // 60} minutes")
    if len(mine) >= lim.max_total:
        raise RateLimitError(
            f"limit reached: {lim.max_total} scored submissions per submitter for {release}")
    if unit == UNIT_FAMILY:
        if sum(1 for e in mine if e.get("unit") == UNIT_FAMILY) >= lim.max_family:
            raise RateLimitError(
                f"limit reached: {lim.max_family} family bundles per submitter for {release}")
    elif benchmark is not None:
        used = sum(1 for e in mine if e.get("benchmark") == benchmark)
        if used >= lim.max_per_benchmark:
            raise RateLimitError(
                f"limit reached: {lim.max_per_benchmark} scored submissions per benchmark "
                f"for {release}")


def record(path: Path, submitter: str, release: str, subset: str, n: int, n_sample: int,
           seed: int, now: float | None = None, unit: str = UNIT_CELL,
           benchmark: str | None = None) -> None:
    """Append one line. A failed write raises (OSError): the run must not report success."""
    entry = {"t": time.time() if now is None else now, "submitter": submitter,
             "release": release, "subset": subset, "unit": unit, "benchmark": benchmark,
             "n": n, "sample": n_sample, "seed": seed}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
        fh.flush()
