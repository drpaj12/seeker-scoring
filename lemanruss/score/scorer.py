"""Score one submission: aggregate-only report in tiers (primary, count bonus, location bonus)."""

from __future__ import annotations

import json
import random
import secrets
import time
from math import comb
from pathlib import Path
from typing import Any

from lemanruss.score import ledger
from lemanruss.score.key import Key
from lemanruss.score.metrics import Confusion, auroc, bootstrap_auroc, rates
from lemanruss.score.submission import Submission, parse

MIN_CELL = 10  # a breakdown cell with fewer sampled circuits is suppressed
COUNT_STEP = 5  # cells of the count matrix are rounded to a multiple of this
SAMPLE_FRACTION = 0.7
SET_PART = {"K4": "K4", "K6": "K6", "gates": "G", "silicon": "silicon"}
BASELINES = Path(__file__).resolve().parents[1] / "data" / "baselines.json"


def r2(x: float | None) -> float | None:
    return None if x is None else round(x, 2)


def chance_hit(n_nets: int, region: int, shown: int) -> float:
    """P(at least one of `shown` random distinct nets lies in a region of `region` of `n_nets`)."""
    if n_nets <= 0 or region <= 0 or shown <= 0:
        return 0.0
    if shown > n_nets - region:
        return 1.0
    return 1.0 - comb(n_nets - region, shown) / comb(n_nets, shown)


def unit_of(subset: str, key: Key, subsets: dict[str, list[str]]) -> tuple[str, str | None]:
    """Quota unit of a subset: (cell | benchmark | family, benchmark name or None for family)."""
    ids = subsets[subset]
    bases = {key.base_of[c] for c in ids}
    if len(bases) > 1:
        return ledger.UNIT_FAMILY, None
    base = next(iter(bases))
    sets = {key.set_of[c] for c in ids}
    return (ledger.UNIT_CELL if len(sets) == 1 else ledger.UNIT_BENCHMARK), base


def draw_sample(ids: list[str], key: Key, rng: random.Random) -> list[str]:
    """Hidden sample: 70 percent of every (benchmark, set) cell, drawn inside the submission."""
    cells: dict[tuple[str, str], list[str]] = {}
    for c in ids:
        cells.setdefault((key.base_of[c], key.set_of[c]), []).append(c)
    out: list[str] = []
    for cell in sorted(cells):
        members = cells[cell]
        out += rng.sample(members, min(len(members), max(1, round(SAMPLE_FRACTION * len(members)))))
    return sorted(out)


def _detection(sample: list[str], sub: Submission, key: Key) -> dict[str, Any]:
    pairs = [(key.infected(c), sub.rows[c].infected) for c in sample]
    conf = Confusion.of(pairs)
    sc = [(key.infected(c), sub.rows[c].score) for c in sample]
    by_base: dict[str, list[tuple[int, float]]] = {}
    for c in sample:
        by_base.setdefault(key.base_of[c], []).append((key.infected(c), sub.rows[c].score))
    return {"conf": conf, "rates": rates(conf), "auroc": auroc(sc), "by_base": by_base}


def _cell(sample: list[str], sub: Submission, key: Key, pick: Any) -> dict[str, Any]:
    ids = [c for c in sample if pick(c)]
    if len(ids) < MIN_CELL:
        return {"suppressed": True}
    d = _detection(ids, sub, key)
    c: Confusion = d["conf"]
    return {"n": len(ids), "tp": c.tp, "fp": c.fp, "tn": c.tn, "fn": c.fn,
            "auroc": r2(d["auroc"]), **{k: r2(v) for k, v in d["rates"].items()}}


def _by_true_count(sample: list[str], sub: Submission, key: Key) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for t in (1, 2, 3):
        ids = [c for c in sample if key.n_trojans(c) == t]
        out[str(t)] = ({"suppressed": True} if len(ids) < MIN_CELL else
                       {"n": len(ids),
                        "found": r2(sum(sub.rows[c].infected for c in ids) / len(ids))})
    return out


def _round_step(x: int) -> int:
    return COUNT_STEP * round(x / COUNT_STEP)


def _count_tier(sample: list[str], sub: Submission, key: Key) -> dict[str, Any]:
    ids = [c for c in sample if key.infected(c) and sub.rows[c].count is not None]
    if len(ids) < MIN_CELL:
        return {"suppressed": True, "answered": len(ids)}
    matrix: dict[str, dict[str, int]] = {}
    for claimed in range(4):
        matrix[str(claimed)] = {str(t): _round_step(sum(
            1 for c in ids if sub.rows[c].count == claimed and key.n_trojans(c) == t))
            for t in (1, 2, 3)}
    exact = sum(1 for c in ids if sub.rows[c].count == key.n_trojans(c)) / len(ids)
    mae = sum(abs((sub.rows[c].count or 0) - key.n_trojans(c)) for c in ids) / len(ids)
    return {"answered": len(ids), "exact": r2(exact), "mae": r2(mae),
            "matrix_claimed_by_true_rounded": matrix, "round_step": COUNT_STEP}


def _loc_tier(sample: list[str], sub: Submission, key: Key) -> dict[str, Any]:
    trials = hits = 0
    chance = 0.0
    answered = 0
    for c in sample:
        reg = key.regions.get(c)
        if not key.infected(c) or reg is None or not sub.rows[c].locations:
            continue
        answered += 1
        shown = set(sub.rows[c].locations)
        for t in reg["trojans"]:
            trials += 1
            hits += 1 if shown & set(t["nets"]) else 0
            chance += chance_hit(reg["n_nets"], len(t["nets"]), len(shown))
    if trials < MIN_CELL:
        return {"suppressed": True, "answered": answered}
    return {"answered": answered, "trials": trials, "hit_rate": r2(hits / trials),
            "chance_rate": r2(chance / trials)}


def _baseline(release: str, subset: str, det: dict[str, Any]) -> list[dict[str, Any]]:
    data = json.loads(BASELINES.read_text(encoding="utf-8")).get(release, {})
    part = next((p for s, p in SET_PART.items() if subset.endswith("-" + s)), "all")
    ci = det["ci"]
    out = []
    for name, vals in data.items():
        if not isinstance(vals, dict):
            continue
        # a per-benchmark entry (key = the unit name) wins over the full-release set figure
        pick = subset if subset in vals else part
        if pick not in vals:
            continue
        b = vals[pick]
        verdict = "n/a"
        if det["auroc"] is not None and ci is not None:
            verdict = ("above" if ci[0] > b else "below" if ci[1] < b else "not distinguishable")
        scope = f"unit {subset}" if pick == subset else f"full release, set {part}"
        out.append({"detector": name, "auroc": b, "scope": scope,
                    "verdict": verdict})
    return out


def score(text: str, key: Key, release: str, subsets: dict[str, list[str]], *,
          ledger_path: Path | None = None, submitter: str | None = None,
          hidden_sample: int | None = None, seed: int | None = None,
          now: float | None = None, limits: ledger.Limits | None = None) -> dict[str, Any]:
    sub = parse(text, release, subsets)
    name = submitter or sub.headers["team"]
    t_now = time.time() if now is None else now
    subset = sub.headers["subset"]
    ids = sorted(subsets[subset])
    unit, benchmark = unit_of(subset, key, subsets)
    if ledger_path is not None:
        ledger.check(ledger_path, name, release, t_now, limits, unit, benchmark)
    if hidden_sample is not None and not 2 <= hidden_sample <= len(ids):
        raise ValueError(f"hidden sample must be between 2 and {len(ids)}")
    drawn = seed if seed is not None else secrets.randbits(62)
    rng = random.Random(drawn)
    sample = (sorted(rng.sample(ids, hidden_sample)) if hidden_sample is not None
              else draw_sample(ids, key, rng))
    n_sample = len(sample)
    det = _detection(sample, sub, key)
    over = "bases" if unit == ledger.UNIT_FAMILY else "circuits"
    groups = (det["by_base"] if over == "bases"
              else {c: [(key.infected(c), sub.rows[c].score)] for c in sample})
    ci = bootstrap_auroc(groups, drawn + 1)
    det["ci"] = ci
    c: Confusion = det["conf"]
    report: dict[str, Any] = {
        "release": release, "subset": subset, "detector": sub.headers["detector"],
        "team": sub.headers["team"], "unit": unit,
        "subset_size": len(ids), "scored_circuits": n_sample,
        "primary": {
            "confusion": {"tp": c.tp, "fp": c.fp, "tn": c.tn, "fn": c.fn},
            **{k: r2(v) for k, v in det["rates"].items()},
            "auroc": r2(det["auroc"]),
            "auroc_ci95": None if ci is None else [r2(ci[0]), r2(ci[1])],
            "auroc_ci95_over": over,
            "by_set": {s: _cell(sample, sub, key, lambda x, s=s: key.set_of[x] == s)
                       for s in sorted(set(key.set_of.values()))},
            "found_by_true_trojan_count": _by_true_count(sample, sub, key)},
        "bonus_count": _count_tier(sample, sub, key),
        "bonus_location": _loc_tier(sample, sub, key),
        "baselines": _baseline(release, subset, det)}
    if ledger_path is not None:
        ledger.record(ledger_path, name, release, subset, len(ids), n_sample, drawn, t_now,
                      unit, benchmark)
    return report


def _f(x: Any) -> str:
    return "n/a" if x is None else (f"{x:.2f}" if isinstance(x, float) else str(x))


def render(rep: dict[str, Any]) -> str:
    p = rep["primary"]
    c = p["confusion"]
    note = ("" if p["auroc_ci95_over"] == "bases" else
            " Interval over circuits, optimistic: circuits of one benchmark share a golden.")
    L = [f"# Seeker scoring report: {rep['detector']} ({rep['team']})", "",
         f"Release `{rep['release']}`, subset `{rep['subset']}`: scored on a hidden random "
         f"sample of "
         f"{rep['scored_circuits']} of {rep['subset_size']} circuits. Aggregates only.", "",
         "## Primary: detection (infected = at least one Trojan)", "",
         "| | predicted infected | predicted clean |", "|---|---|---|",
         f"| infected | TP {c['tp']} | FN {c['fn']} |",
         f"| clean | FP {c['fp']} | TN {c['tn']} |", "",
         f"TPR {_f(p['tpr'])}, FPR {_f(p['fpr'])}, precision {_f(p['precision'])}, "
         f"F1 {_f(p['f1'])}, accuracy {_f(p['accuracy'])}.", "",
         f"AUROC {_f(p['auroc'])}, 95% interval over {p['auroc_ci95_over']} "
         f"{_f(p['auroc_ci95'])}.{note}", "",
         "Infected circuits found, by true number of Trojans (multi-Trojan circuits must be "
         "found):",
         ""]
    for t, v in p["found_by_true_trojan_count"].items():
        L.append(f"- {t} Trojan(s): " + ("suppressed (too few circuits)" if v.get("suppressed")
                 else f"{_f(v['found'])} of {v['n']}"))
    L += ["", "By mapping set:", ""]
    for s, v in p["by_set"].items():
        L.append(f"- {s}: " + ("suppressed (too few circuits)" if v.get("suppressed") else
                 f"n {v['n']}, TP {v['tp']} FP {v['fp']} TN {v['tn']} FN {v['fn']}, "
                 f"TPR {_f(v['tpr'])}, FPR {_f(v['fpr'])}, AUROC {_f(v['auroc'])}"))
    L += ["", "## Baselines (AUROC of detectors on the full release)", ""]
    for b in rep["baselines"]:
        L.append(f"- {b['detector']}: {_f(b['auroc'])} ({b['scope']}); yours is {b['verdict']}")
    L += ["", "A 100-circuit sample gives a wide interval: `not distinguishable` is not a loss.",
          "",
          "## Bonus: number of Trojans", ""]
    k = rep["bonus_count"]
    if k.get("suppressed"):
        L.append(f"Suppressed: {k['answered']} infected circuits with a count (need {MIN_CELL}).")
    else:
        L.append(f"Exact count right on {_f(k['exact'])} of {k['answered']} infected circuits; "
                 f"mean absolute error {_f(k['mae'])}. Claimed (rows) against true "
                 f"(columns 1, 2, 3), "
                 f"cells rounded to multiples of {k['round_step']}:")
        L.append("")
        L += ["| claimed | 1 | 2 | 3 |", "|---|---|---|---|"]
        for cl, row in k["matrix_claimed_by_true_rounded"].items():
            L.append(f"| {cl} | {row['1']} | {row['2']} | {row['3']} |")
    L += ["", "## Bigger bonus: where is the Trojan", ""]
    g = rep["bonus_location"]
    if g.get("suppressed"):
        L.append(f"Suppressed: fewer than {MIN_CELL} located Trojans ({g['answered']} circuits).")
    else:
        L.append(f"{g['trials']} Trojans in {g['answered']} circuits with locations: hit rate "
                 f"{_f(g['hit_rate'])} (chance level for the same number of nets "
                 f"{_f(g['chance_rate'])}).")
    return "\n".join(L) + "\n"
