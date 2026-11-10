"""Named subsets of 100 circuits per release: seeded, stratified by source (base), ids only."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from lemanruss.score.key import Key, load

SUBSET_SIZE = 100


def allocate(pool: dict[str, list[str]], n: int, rng: random.Random) -> list[str]:
    """Equal allocation over bases, round-robin in a seeded base order, capped by availability."""
    bases = sorted(b for b in pool if pool[b])
    rng.shuffle(bases)
    queues = {b: rng.sample(pool[b], len(pool[b])) for b in bases}
    out: list[str] = []
    while len(out) < n and any(queues.values()):
        for b in bases:
            if queues[b] and len(out) < n:
                out.append(queues[b].pop())
    return sorted(out)


def _group(ids: list[str], key: Key) -> dict[str, list[str]]:
    pool: dict[str, list[str]] = {}
    for cid in ids:
        pool.setdefault(key.base_of[cid], []).append(cid)
    return pool


def build_subsets(key: Key, release: str, seed: int) -> dict[str, Any]:
    fam = "Comb" if key.kind == "comb" else "Seq"
    ids = key.ids()
    out: dict[str, list[str]] = {"all": ids}

    def draw(name: str, cand: list[str]) -> None:
        out[name] = allocate(_group(cand, key), SUBSET_SIZE, random.Random(f"{seed}/{name}"))

    for s in sorted(set(key.set_of.values())):
        draw(f"{fam}-{s}", [c for c in ids if key.set_of[c] == s])
    bands = {"low": (0, 30), "mid": (31, 50), "high": (51, 100)}
    for nm, (lo, hi) in bands.items():
        draw(f"{fam}-prev-{nm}", [
            c for c in ids
            if lo <= key.cell_prevalence[(key.base_of[c], key.set_of[c])] <= hi])
    clean = [c for c in ids if not key.infected(c)]
    for t in (1, 2, 3):
        inf = [c for c in ids if key.n_trojans(c) == t]
        rng = random.Random(f"{seed}/{fam}-trojans-{t}")
        out[f"{fam}-trojans-{t}"] = sorted(
            allocate(_group(inf, key), SUBSET_SIZE // 2, rng)
            + allocate(_group(clean, key), SUBSET_SIZE // 2, rng))
    draw(f"{fam}-mix100", ids)
    return {"release": release, "seed": seed,
            "subsets": {k: {"n": len(v), "ids": v} for k, v in out.items()}}


def make(key_dir: Path, release: str, seed: int, out: Path) -> dict[str, Any]:
    res = build_subsets(load(key_dir), release, seed)
    out.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    return res


def load_subsets(path: Path) -> tuple[str, dict[str, list[str]]]:
    d = json.loads(path.read_text(encoding="utf-8"))
    return d["release"], {k: v["ids"] for k, v in d["subsets"].items()}
