"""Read the answer key (private): labels, sets, Trojans, regions, anonymised base names."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Key:
    labels: dict[str, Any]
    base_of: dict[str, str]
    set_of: dict[str, str]
    goldens: set[str]
    kind: str
    trojans: dict[str, list[Any]]
    cell_prevalence: dict[tuple[str, str], int]
    regions: dict[str, Any] = field(default_factory=dict)

    def infected(self, cid: str) -> int:
        return 0 if self.labels[cid] is None else 1

    def n_trojans(self, cid: str) -> int:
        return len(self.trojans.get(cid, [])) if self.infected(cid) else 0

    def ids(self) -> list[str]:
        """Every scored circuit (goldens excluded), sorted."""
        return sorted(self.base_of)


def load(key_dir: Path) -> Key:
    def rd(name: str) -> Any:
        return json.loads((key_dir / name).read_text(encoding="utf-8"))

    labels = rd("labels.json")
    sets = rd("sets.json")
    trojans = rd("trojans.json") if (key_dir / "trojans.json").exists() else {}
    regions = rd("regions.json") if (key_dir / "regions.json").exists() else {}
    anon = rd("base_names.json") if (key_dir / "base_names.json").exists() else {}
    base_of: dict[str, str] = {}
    set_of: dict[str, str] = {}
    goldens: set[str] = set()
    prev: dict[tuple[str, str], int] = {}
    kind = ""
    for base, s in sets.items():
        goldens.add(s["golden"])
        kind = s.get("kind", kind)
        b = anon.get(base, base)
        for name, v in s["sets"].items():
            prev[(b, name)] = int(v.get("n_infected_drawn", len(v["infected_ids"])))
            for cid in v["infected_ids"] + v["clean_ids"]:
                base_of[cid] = b
                set_of[cid] = name
    return Key(labels, base_of, set_of, goldens, kind, trojans, prev, regions)
