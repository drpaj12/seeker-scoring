"""Pull the submission CSV out of an issue body (data only; nothing is executed)."""

from __future__ import annotations

import re


def extract_csv(body: str) -> str:
    """The text of the first fenced block, else the text after the first '###' heading."""
    body = body.replace("\r\n", "\n")
    m = re.search(r"```[A-Za-z]*\n(.*?)\n```", body, re.S)
    if m:
        return m.group(1).strip() + "\n"
    parts = re.split(r"^###[^\n]*\n", body, maxsplit=1, flags=re.M)
    return (parts[1] if len(parts) > 1 else body).strip() + "\n"
