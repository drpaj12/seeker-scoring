"""Pack and unpack the trimmed answer key of one public release (public ids only).

Archive layout `<release>-key/{labels,sets,trojans,subsets}.json`; `subsets.json` holds the
units `<benchmark>-<set>`, `<benchmark>` and the family bundle. Nothing else is packed: no
scripts, rareness, provenance, witnesses or seeds. The archive is private; the encryption
(`gpg`) is done outside this module.
"""

from __future__ import annotations

import gzip
import io
import json
import tarfile
from pathlib import Path
from typing import Any

FILES = ("labels.json", "sets.json", "trojans.json", "subsets.json")


class KeyPackError(ValueError):
    """The key and the public tree disagree, or an archive is malformed."""


def _trojan_counts(key_dir: Path, labels: dict[str, Any]) -> dict[str, int]:
    tj = key_dir / "trojans.json"
    if tj.exists():
        return {c: len(v) for c, v in json.loads(tj.read_text(encoding="utf-8")).items()}
    prov = json.loads((key_dir / "provenance.json").read_text(encoding="utf-8"))
    return {c: int(p["insert"].get("n_trojans", 0)) if p["role"] == "infected" else 0
            for c, p in prov.items()}


def _cells(bench_dir: Path) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for line in (bench_dir / "sets.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        name, _, ids = line.partition(":")
        out[name.strip()] = ids.split()
    return out


def build(key_dir: Path, public_family_dir: Path, release: str, family: str,
          ) -> dict[str, Any]:
    """The four JSON objects. `public_family_dir` holds `<benchmark>/sets.txt` (ids only)."""
    labels = json.loads((key_dir / "labels.json").read_text(encoding="utf-8"))
    ntroj = _trojan_counts(key_dir, labels)
    sets: dict[str, Any] = {}
    subsets: dict[str, list[str]] = {}
    k_labels: dict[str, Any] = {}
    k_troj: dict[str, Any] = {}
    for bdir in sorted(p for p in public_family_dir.iterdir() if (p / "sets.txt").exists()):
        b = bdir.name
        sets[b] = {"golden": "golden", "kind": family, "sets": {}}
        units: dict[str, list[str]] = {}
        for name, ids in _cells(bdir).items():
            if len(ids) != 100:
                raise KeyPackError(f"{b}-{name}: {len(ids)} circuits, expected 100")
            for i in ids:
                if i not in labels:
                    raise KeyPackError(f"{b}-{name}: id {i} is not in the key")
            inf = sorted(i for i in ids if labels[i] is not None)
            clean = sorted(i for i in ids if labels[i] is None)
            sets[b]["sets"][name] = {"infected_ids": inf, "clean_ids": clean,
                                     "n_infected_drawn": len(inf)}
            units[f"{b}-{name}"] = sorted(ids)
            for i in ids:
                k_labels[i] = labels[i]
                n = ntroj.get(i, 0) if labels[i] is not None else 0
                if (n >= 1) != (labels[i] is not None):
                    raise KeyPackError(f"{b}-{name}: Trojan count disagrees with label of {i}")
                if n:
                    k_troj[i] = [{} for _ in range(n)]
        units[b] = sorted(i for u in units.values() for i in u)
        subsets.update(units)
    if not k_labels:
        raise KeyPackError("no benchmark with a sets.txt under " + str(public_family_dir))
    subsets[family.capitalize()] = sorted(k_labels)
    sub = {"release": release, "seed": 0,
           "subsets": {k: {"n": len(v), "ids": v} for k, v in subsets.items()}}
    return {"labels.json": k_labels, "sets.json": sets, "trojans.json": k_troj,
            "subsets.json": sub}


def pack(key_dir: Path, public_family_dir: Path, release: str, family: str, out: Path,
         ) -> dict[str, int]:
    """Write the deterministic `.tar.gz` (sorted, zero mtime); return the size of each file."""
    files = build(key_dir, public_family_dir, release, family)
    raw = io.BytesIO()
    sizes: dict[str, int] = {}
    with tarfile.open(fileobj=raw, mode="w") as tf:
        for name, obj in files.items():
            data = (json.dumps(obj, indent=None, sort_keys=True) + "\n").encode()
            sizes[name] = len(data)
            ti = tarfile.TarInfo(f"{release}-key/{name}")
            ti.size, ti.mtime, ti.mode = len(data), 0, 0o600
            tf.addfile(ti, io.BytesIO(data))
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("wb") as fh, gzip.GzipFile(fileobj=fh, mode="wb", compresslevel=9,
                                             mtime=0, filename="") as gz:
        gz.write(raw.getvalue())
    out.chmod(0o600)
    sizes["archive"] = out.stat().st_size
    return sizes


def unpack(archive: Path, dest: Path) -> Path:
    """Extract the four known files only (no links, no paths outside); return the key dir."""
    dest.mkdir(parents=True, exist_ok=True)
    top: str | None = None
    with tarfile.open(archive, "r:gz") as tf:
        for m in tf.getmembers():
            parts = Path(m.name).parts
            if (not m.isreg() or len(parts) != 2 or parts[1] not in FILES
                    or m.name.startswith("/") or ".." in parts):
                raise KeyPackError(f"unexpected archive member '{m.name}'")
            top = top or parts[0]
            if parts[0] != top:
                raise KeyPackError("archive holds more than one top directory")
        if top is None:
            raise KeyPackError("empty archive")
        for m in tf.getmembers():
            f = tf.extractfile(m)
            assert f is not None
            target = dest / m.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(f.read())
            target.chmod(0o600)
    return dest / top
