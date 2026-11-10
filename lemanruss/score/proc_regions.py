"""Trojan regions of a Seeker-Proc release (answer key only).

Definition (spec `docs/specs/2026-11-02-scoring-design.md` section 9a). A processor Trojan is
driven through the core's memory interface (the instruction it fetches), so there is no
open-loop input sequence that makes its trigger fire and the witness lane of `regions.py`
cannot be built. The region is therefore taken on random input lanes only:

    free   = { net x of R, not a primary input : no net of the clean twin, and no complement of
               one, has the same signature on 64 random lanes over 16 cycles }
    victim = { primary output o of R : the transitive fan-in of o contains a free net }
    region = free, restricted to the fan-in of the victim outputs (all of `free` when a free
             net reaches no output, which does not happen on a core with observation ports)

R and its clean twin are fed identical inputs by port name. A rare trigger (a 16- or 32-bit
magic word) reads a constant on random lanes and its partial-match logic has no counterpart in
the twin, so it is in the region. Two limits, stated: (1) a circuit holds 1 to 3 Trojans and
they are not told apart, so the circuit's region is one cell set and `trojans` repeats it once
per Trojan (a claim in the region hits one Trojan, matching stays one to one); (2) the twin was
mapped by its own ABC script, so restructured logic of the infected circuit also lacks a
counterpart and the region over-approximates; the chance control of `levels.py` prints the
level-3 score of random claims of the same sizes next to every detector.
"""

from __future__ import annotations

import gzip
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from lemanruss.score import regions as rg


def region_nets(golden: rg.Net, rel: rg.Net, seed: str) -> dict[str, Any]:
    cand = [n for n in list(rel.gates) + list(rel.latches) if n not in set(rel.inputs)]
    g_nets = list(golden.gates) + list(golden.latches) + golden.inputs
    gs = rg.simulate(golden, [], seed, rg.MIN_CYCLES, g_nets)[0]
    rs = rg.simulate(rel, [], seed, rg.MIN_CYCLES, cand)[0]
    known = {a for a, _ in gs.values()} | {b for _, b in gs.values()}
    free = {n for n in cand if rs[n][0] not in known}
    victims = [o for o in rel.outputs if rg.fanin(rel, o) & free]
    cone: set[str] = set()
    for o in victims:
        cone |= rg.fanin(rel, o)
    nets = sorted(free & cone) if victims else sorted(free)
    return {"victims": victims, "nets": nets, "cone": len(cone), "free": len(free),
            "n_nets": len(cand)}


def _task(args: tuple[str, str, str, str, int]) -> tuple[str, dict[str, Any]]:
    cid, rel_path, twin_path, seed, n_trojans = args
    with gzip.open(rel_path, "rt", encoding="utf-8") as fh:
        rel = rg.parse_blif(fh.read())
    with gzip.open(twin_path, "rt", encoding="utf-8") as fh:
        gold = rg.parse_blif(fh.read())
    r = region_nets(gold, rel, f"{seed}/{cid}")
    one = {"victim": ",".join(r["victims"][:8]), "victim_found": bool(r["victims"]),
           "nets": r["nets"], "cone": r["cone"]}
    return cid, {"n_nets": r["n_nets"], "trojans": [one] * n_trojans}


def build(release_dir: Path, workers: int = 2, seed: str = "proc-regions-1") -> dict[str, Any]:
    key = release_dir / "answer_key"
    prov = json.loads((key / "provenance.json").read_text(encoding="utf-8"))
    manifest = json.loads((release_dir / "manifest.json").read_text(encoding="utf-8"))
    tasks = []
    for row in manifest["circuits"]:
        cid = str(row["id"])
        if prov[cid]["role"] != "infected":
            continue
        n_tr = int(prov[cid]["insert"]["n_trojans"])
        tasks.append((cid, str(release_dir / row["file"]),
                      str(key / "twins" / f"{cid}.blif.gz"), seed, n_tr))
    res: dict[str, Any] = {}
    if workers <= 1:
        for t in tasks:
            cid, r = _task(t)
            res[cid] = r
    else:
        with ProcessPoolExecutor(workers) as ex:
            for cid, r in ex.map(_task, tasks, chunksize=2):
                res[cid] = r
    return dict(sorted(res.items()))


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("release", type=Path)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    a.out.write_text(json.dumps(build(a.release, a.workers)), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
