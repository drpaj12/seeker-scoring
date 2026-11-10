"""Parse and validate one submission CSV; every failure is a SubmissionError (clear message)."""

from __future__ import annotations

import csv
import io
import math
import re
from dataclasses import dataclass, field

MAX_BYTES = 5 * 1024 * 1024
MAX_LOCATIONS = 10
MAX_COUNT = 3
REQUIRED_HEADERS = ("seeker-release", "subset", "detector", "team")
OPTIONAL_HEADERS = ("contact",)
COLUMNS = ["id", "infected", "score", "count", "locations"]
NET_RE = re.compile(r"^[A-Za-z0-9_.$\[\]:<>/\\-]{1,200}$")


class SubmissionError(ValueError):
    """A hard error: the submission is refused and nothing is scored."""


@dataclass
class Row:
    infected: int
    score: float
    count: int | None
    locations: list[str] = field(default_factory=list)


@dataclass
class Submission:
    headers: dict[str, str]
    rows: dict[str, Row]


def _headers(lines: list[str]) -> tuple[dict[str, str], int]:
    headers: dict[str, str] = {}
    i = 0
    while i < len(lines) and lines[i].startswith("#"):
        key, sep, value = lines[i][1:].partition(":")
        key, value = key.strip(), value.strip()
        if not sep or not key:
            raise SubmissionError(f"line {i + 1}: header must read '# key: value'")
        if key not in REQUIRED_HEADERS + OPTIONAL_HEADERS:
            raise SubmissionError(f"line {i + 1}: unknown header '{key}'")
        if key in headers:
            raise SubmissionError(f"line {i + 1}: header '{key}' given twice")
        if not value and key != "contact":
            raise SubmissionError(f"line {i + 1}: header '{key}' is empty")
        headers[key] = value
        i += 1
    for key in REQUIRED_HEADERS:
        if key not in headers:
            raise SubmissionError(f"missing header '# {key}: ...'")
    return headers, i


def _int01(raw: str, lo: int, hi: int, what: str, line: int) -> int:
    if not re.fullmatch(r"[0-9]", raw.strip()) or not lo <= int(raw) <= hi:
        raise SubmissionError(f"line {line}: {what} must be an integer {lo}..{hi}, got '{raw}'")
    return int(raw)


def parse(text: str, release: str, subset_ids: dict[str, list[str]]) -> Submission:
    """Parse `text`; `subset_ids` maps subset name to its id list. Raises SubmissionError."""
    if len(text.encode("utf-8", "replace")) > MAX_BYTES:
        raise SubmissionError(f"file larger than {MAX_BYTES} bytes")
    lines = text.replace("\r\n", "\n").split("\n")
    headers, i = _headers(lines)
    if not all(ord(ch) < 128 for ln in lines[:i] for ch in ln):
        raise SubmissionError("non-ASCII character in the header lines")
    if headers["seeker-release"] != release:
        raise SubmissionError(
            f"wrong release '{headers['seeker-release']}': this scorer scores '{release}'")
    subset = headers["subset"]
    if subset not in subset_ids:
        raise SubmissionError(f"unknown subset '{subset}'")
    wanted = set(subset_ids[subset])
    body = "\n".join(lines[i:])
    reader = csv.reader(io.StringIO(body))
    first = next(reader, None)
    if first is None or [c.strip() for c in first] != COLUMNS:
        raise SubmissionError(f"line {i + 1}: column header must be '{','.join(COLUMNS)}'")
    rows: dict[str, Row] = {}
    for off, fields in enumerate(reader, start=i + 2):
        if not fields:
            continue
        if len(fields) != len(COLUMNS):
            raise SubmissionError(
                f"line {off}: expected {len(COLUMNS)} fields, got {len(fields)}")
        rid = fields[0].strip()
        if rid not in wanted:
            raise SubmissionError(f"line {off}: id '{rid}' is not in subset '{subset}'")
        if rid in rows:
            raise SubmissionError(f"line {off}: id '{rid}' appears twice")
        infected = _int01(fields[1], 0, 1, "infected", off)
        try:
            score = float(fields[2])
        except ValueError:
            raise SubmissionError(f"line {off}: score '{fields[2]}' is not a number") from None
        if not math.isfinite(score):
            raise SubmissionError(f"line {off}: score must be finite, got '{fields[2]}'")
        count = None
        if fields[3].strip():
            count = _int01(fields[3], 0, MAX_COUNT, "count", off)
            if (count == 0) != (infected == 0):
                raise SubmissionError(
                    f"line {off}: infected={infected} disagrees with count={count}")
        locs = [x.strip() for x in fields[4].split(";") if x.strip()]
        if len(locs) > MAX_LOCATIONS:
            raise SubmissionError(
                f"line {off}: {len(locs)} locations, at most {MAX_LOCATIONS} allowed")
        for net in locs:
            if not NET_RE.match(net):
                raise SubmissionError(f"line {off}: bad net name '{net}'")
        rows[rid] = Row(infected, score, count, list(dict.fromkeys(locs)))
    if not rows:
        raise SubmissionError("no rows")
    missing = sorted(wanted - set(rows))
    if missing:
        raise SubmissionError(
            f"{len(missing)} id(s) of subset '{subset}' missing, first: {', '.join(missing[:5])}")
    return Submission(headers, rows)
