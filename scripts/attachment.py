#!/usr/bin/env python3
"""Attachment helpers for score.sh. Data only; nothing from the issue is executed.

  attachment.py link REPO       issue body on stdin; prints the one attachment URL or NONE.
                                Exit 2 with a reason on stdout: bad URL or more than one link.
  attachment.py check FILE      exit 2 with a reason unless FILE is UTF-8 text without NUL, <= 8 MB.
  attachment.py stamp LEDGER INPUT SHA256
                                add input and sha256 to the last ledger line.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

MAX_BYTES = 8 * 1024 * 1024
_NAME = r"[A-Za-z0-9._-]{1,100}"
_EXT = re.compile(r"\.(?:csv|txt)\Z", re.I)
# GitHub issue attachment forms. The user-attachments form is the one GitHub issues today
# (docs.github.com "Attaching files" documents csv/txt uploads but gives no URL example; the
# form is taken from reports of github.com/user-attachments/files/<id>/<name>). The older
# form is accepted only for the scoring repository itself.
USER_RE = re.compile(r"https://github\.com/user-attachments/files/[0-9]+/(" + _NAME + r")")
_CAND = re.compile(r"https?://[^\s<>\"'`)\]]+", re.I)


class Refuse(Exception):
    pass


def candidates(body: str) -> list[str]:
    seen: list[str] = []
    for m in _CAND.finditer(body.replace("\r\n", "\n")):
        u = m.group(0).rstrip(".,;:!")
        if ("/files/" in u or "user-attachments" in u) and u not in seen:
            seen.append(u)
    return seen


def valid_url(url: str, repo: str) -> bool:
    m = USER_RE.fullmatch(url)
    if not m:
        legacy = re.compile(r"https://github\.com/" + re.escape(repo) + r"/files/[0-9]+/(" + _NAME + r")",
                            re.I)
        m = legacy.fullmatch(url)
    return bool(m) and bool(_EXT.search(m.group(1))) and m.group(1) not in (".", "..")


def find_link(body: str, repo: str) -> str | None:
    c = candidates(body)
    if not c:
        return None
    if len(c) > 1:
        raise Refuse("more than one attachment link; attach exactly one .csv or .txt file")
    if not valid_url(c[0], repo):
        raise Refuse("the attachment link is not a GitHub issue attachment of type .csv or .txt")
    return c[0]


def check_file(path: Path) -> None:
    data = path.read_bytes()
    if len(data) > MAX_BYTES:
        raise Refuse("attachment larger than 8 MB")
    if b"\x00" in data:
        raise Refuse("attachment is not text (NUL byte)")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        raise Refuse("attachment is not UTF-8 text") from None


def normalise(path: Path) -> None:
    text = path.read_bytes().decode("utf-8").removeprefix("﻿").replace("\r\n", "\n")
    path.write_text(text.strip() + "\n", encoding="utf-8")


def stamp(ledger: Path, kind: str, sha: str) -> None:
    lines = ledger.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[-1])
    entry["input"] = kind
    entry["sha256"] = sha
    lines[-1] = json.dumps(entry)
    ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    try:
        if argv[0] == "link":
            print(find_link(sys.stdin.read(), argv[1]) or "NONE")
        elif argv[0] == "check":
            check_file(Path(argv[1]))
        elif argv[0] == "normalise":
            normalise(Path(argv[1]))
        elif argv[0] == "stamp":
            stamp(Path(argv[1]), argv[2], argv[3])
        else:
            return 64
    except Refuse as exc:
        print(str(exc))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
