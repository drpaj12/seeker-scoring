"""Public evaluation release: base names anonymised (b001...), the mapping kept in the key.

The public release holds `circuits/`, a manifest without base names (`base` is the anonymised
name, goldens are listed by id) and a minimal datasheet with no per-base or per-set label data.
Port names are the circuit interface and stay; a reader may still recognise a well-known
benchmark from them (spec section 10).
"""

from __future__ import annotations

import hashlib
import json
import random
import shutil
from pathlib import Path
from typing import Any


def mapping(bases: list[str], seed: int) -> dict[str, str]:
    order = sorted(bases)
    random.Random(f"anon/{seed}").shuffle(order)
    return {b: f"b{i:03d}" for i, b in enumerate(order, 1)}


def anonymise(release: Path, key_dir: Path, out: Path, seed: int = 0) -> str:
    man: dict[str, Any] = json.loads((release / "manifest.json").read_text(encoding="utf-8"))
    names = sorted({c["base"] for c in man["circuits"]})
    amap = mapping(names, seed)
    (key_dir / "base_names.json").write_text(json.dumps(amap, indent=1) + "\n", encoding="utf-8")
    (out / "circuits").mkdir(parents=True, exist_ok=True)
    for c in man["circuits"]:
        shutil.copyfile(release / c["file"], out / c["file"])
    pub: dict[str, Any] = {
        "release": man["release"], "family": man["family"], "version": man["version"],
        "tools": man["tools"], "answer_key": "not published; scored through the service only",
        "circuits": [{**c, "base": amap[c["base"]]} for c in man["circuits"]],
        "goldens": {amap[b]: g for b, g in man["goldens"].items()},
        "counts": {"circuits": len(man["circuits"]), "bases": len(names)}}
    (out / "manifest.json").write_text(json.dumps(pub, indent=1) + "\n", encoding="utf-8")
    (out / "DATASHEET.md").write_text(
        f"# {man['release']} (public evaluation release)\n\n"
        f"Family {man['family']}, {len(man['circuits'])} circuits over {len(names)} anonymised "
        "bases (b001...). Each base has one clean golden (listed in the manifest). No label, "
        "set, prevalence or Trojan data is published; submit detector output for scoring "
        "(docs/user/SUBMISSION.md).\n", encoding="utf-8")
    sums = []
    for p in sorted(out.rglob("*")):
        if p.is_file() and p.name != "SHA256SUMS":
            sums.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out)}")
    (out / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    return f"{len(names)} bases anonymised, {len(man['circuits'])} circuits"
