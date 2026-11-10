"""Trojan regions in released net names (answer key only, never in the public release).

Definition (spec section 9). After obfuscation the Trojan cells are remapped and renamed, so the
region of Trojan j in circuit R is found by function, not by name:

    region_j = { net x of R, not a primary input :
                 x is in the transitive fan-in of Trojan j's victim output (through gates and
                 latches), and
                 no net of the clean golden, and no complement of one, has the same signature }

The signature of a net is its value over `RANDOM_LANES` random input lanes plus one lane that
replays the stored witness of Trojan j (the input sequence on which that Trojan fires and shows),
over `max(MIN_CYCLES, witness length)` cycles, golden and R fed identical inputs by port name.
The witness lane makes the payload cell and everything downstream of a firing trigger differ from
the golden, although the trigger is too rare to fire on random lanes. This over-approximates:
logic that ABC restructured also has no golden twin. The scorer therefore prints the chance level
of the hit rate for the same number of submitted nets (see scorer.py).
"""

from __future__ import annotations

import gzip
import json
import random
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RANDOM_LANES = 64
MIN_CYCLES = 16
_P = (1 << 127) - 1
_B = 0x9E3779B97F4A7C15F39CC0605CEDC835 % _P


@dataclass
class Net:
    gates: dict[str, tuple[list[str], list[tuple[str, str]], str]]  # out -> ins, rows, out bit
    latches: dict[str, tuple[str, int]]  # q -> d, init
    inputs: list[str]
    outputs: list[str]
    order: list[str]


def parse_blif(text: str) -> Net:
    inputs: list[str] = []
    outputs: list[str] = []
    gates: dict[str, tuple[list[str], list[tuple[str, str]], str]] = {}
    latches: dict[str, tuple[str, int]] = {}
    cur: str | None = None
    for ln in text.replace("\\\n", " ").splitlines():
        w = ln.split()
        if not w or w[0][0] == "#":
            continue
        if w[0][0] != ".":
            if cur is not None:
                ins, rows, ob = gates[cur]
                pat, bit = (w[0], w[1]) if len(w) > 1 else ("", w[0])
                rows.append((pat, bit))
                gates[cur] = (ins, rows, ob or bit)
            continue
        cur = None
        if w[0] == ".inputs":
            inputs += w[1:]
        elif w[0] == ".outputs":
            outputs += w[1:]
        elif w[0] == ".names":
            cur = w[-1]
            gates[cur] = (w[1:-1], [], "")
        elif w[0] == ".latch":
            init = int(w[-1]) if len(w) > 3 and w[-1] in "0123" else 3
            latches[w[2]] = (w[1], 1 if init == 1 else 0)
    return Net(gates, latches, inputs, outputs, _topo(gates, set(inputs) | set(latches)))


def _topo(gates: dict[str, Any], sources: set[str]) -> list[str]:
    order: list[str] = []
    state: dict[str, int] = {}
    for root in gates:
        stack = [(root, 0)]
        while stack:
            n, i = stack.pop()
            if i == 0:
                if state.get(n) == 2 or n not in gates:
                    continue
                state[n] = 1
            ins = gates[n][0]
            if i < len(ins):
                stack.append((n, i + 1))
                m = ins[i]
                if m in gates and state.get(m) is None:
                    stack.append((m, 0))
            else:
                state[n] = 2
                order.append(n)
    return order


def _eval(rows: list[tuple[str, str]], ins: list[str], vals: dict[str, int], mask: int) -> int:
    acc = 0
    for pat, _ in rows:
        term = mask
        for ch, nm in zip(pat, ins, strict=False):
            if ch == "1":
                term &= vals[nm]
            elif ch == "0":
                term &= ~vals[nm] & mask
        acc |= term
    return acc


def simulate(net: Net, witnesses: list[tuple[list[str], list[str]]], seed: str,
             cycles: int, nets: list[str]) -> list[dict[str, tuple[int, int]]]:
    """Per Trojan lane set: net -> (signature, complement signature). `witnesses` holds
    (input names, rows) per Trojan; lane RANDOM_LANES + j replays Trojan j."""
    t = len(witnesses)
    width = RANDOM_LANES + t
    mask = (1 << width) - 1
    rngs = {n: random.Random(f"{seed}/{n}") for n in sorted(net.inputs)}
    wit_idx = [{n: k for k, n in enumerate(names)} for names, _ in witnesses]
    masks = [((1 << RANDOM_LANES) - 1) | (1 << (RANDOM_LANES + j)) for j in range(t)]
    sig = [{n: [0, 0] for n in nets} for _ in range(max(t, 1))]
    state = {q: (mask if init else 0) for q, (_, init) in net.latches.items()}
    for c in range(cycles):
        vals: dict[str, int] = dict(state)
        for n in sorted(net.inputs):
            v = rngs[n].getrandbits(width)
            for j, (_, rows) in enumerate(witnesses):
                k = wit_idx[j].get(n)
                if k is not None and c < len(rows):
                    bit = 1 << (RANDOM_LANES + j)
                    v = (v | bit) if rows[c][k] == "1" else (v & ~bit)
            vals[n] = v
        for g in net.order:
            g_ins, g_rows, ob = net.gates[g]
            v = _eval(g_rows, g_ins, vals, mask)
            vals[g] = (~v & mask) if ob == "0" else v
        for j in range(max(t, 1)):
            mj = masks[j] if t else (1 << RANDOM_LANES) - 1
            for n in nets:
                w = vals.get(n, 0) & mj
                s = sig[j][n]
                s[0] = (s[0] * _B + w) % _P
                s[1] = (s[1] * _B + (~w & mj)) % _P
        state = {q: vals.get(d, 0) for q, (d, _) in net.latches.items()}
    return [{n: (a, b) for n, (a, b) in s.items()} for s in sig]


def fanin(net: Net, root: str) -> set[str]:
    seen: set[str] = set()
    todo = [root]
    while todo:
        n = todo.pop()
        if n in seen:
            continue
        seen.add(n)
        if n in net.gates:
            todo += net.gates[n][0]
        elif n in net.latches:
            todo.append(net.latches[n][0])
    return seen


def region_of(golden: Net, rel: Net, witnesses: list[tuple[list[str], list[str]]],
              victims: list[str], seed: str) -> list[dict[str, Any]]:
    cycles = max([MIN_CYCLES] + [len(r) for _, r in witnesses])
    cand = [n for n in list(rel.gates) + list(rel.latches) if n not in set(rel.inputs)]
    g_nets = list(golden.gates) + list(golden.latches) + golden.inputs
    gs = simulate(golden, witnesses, seed, cycles, g_nets)
    rs = simulate(rel, witnesses, seed, cycles, cand)
    out: list[dict[str, Any]] = []
    for j, v in enumerate(victims):
        known = {a for a, _ in gs[j].values()} | {b for _, b in gs[j].values()}
        found = v in rel.outputs
        cone = fanin(rel, v) if found else set(cand)
        nets = sorted(n for n in cand if n in cone and rs[j][n][0] not in known)
        out.append({"victim": v, "victim_found": found, "nets": nets, "cone": len(cone)})
    return out


def _task(args: tuple[str, str, str, str, str, list[str]]) -> tuple[str, dict[str, Any]]:
    cid, rel_path, gold_path, wit_path, seed, victims = args
    with gzip.open(wit_path, "rt", encoding="utf-8") as fh:
        wit = json.load(fh)
    names = wit["inputs"]
    rows = [wit["steps"].get(cid, {}).get(str(j), []) for j in range(len(victims))]
    wl = [(names, r) for r in rows]
    with gzip.open(rel_path, "rt", encoding="utf-8") as fh:
        rel = parse_blif(fh.read())
    with gzip.open(gold_path, "rt", encoding="utf-8") as fh:
        gold = parse_blif(fh.read())
    n_nets = len(rel.gates) + len(rel.latches)
    return cid, {"n_nets": n_nets, "trojans": region_of(gold, rel, wl, victims, f"{seed}/{cid}")}


def build(release_dir: Path, key_dir: Path, workers: int = 2, seed: str = "regions-1",
          only: list[str] | None = None) -> dict[str, Any]:
    sets = json.loads((key_dir / "sets.json").read_text(encoding="utf-8"))
    trojans = json.loads((key_dir / "trojans.json").read_text(encoding="utf-8"))
    tasks = []
    for base, s in sets.items():
        gold = release_dir / "circuits" / f"{s['golden']}.blif.gz"
        wit = key_dir / "witnesses" / f"{base}.json.gz"
        for v in s["sets"].values():
            for cid in v["infected_ids"]:
                if only is not None and cid not in only:
                    continue
                victims = [str(t["victim"]) for t in trojans[cid]]
                tasks.append((cid, str(release_dir / "circuits" / f"{cid}.blif.gz"), str(gold),
                              str(wit), seed, victims))
    res: dict[str, Any] = {}
    if workers <= 1:
        for task in tasks:
            cid, r = _task(task)
            res[cid] = r
    else:
        with ProcessPoolExecutor(workers) as ex:
            for cid, r in ex.map(_task, tasks, chunksize=4):
                res[cid] = r
    return dict(sorted(res.items()))
