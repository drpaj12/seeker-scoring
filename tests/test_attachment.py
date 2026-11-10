"""Attachment route: URL allow-list, file checks, extract path, ledger stamp, family dry run."""

from __future__ import annotations

import hashlib
import json
import os
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import attachment as att  # noqa: E402
import test_tester as tt  # noqa: E402

REPO = "o/r"
GOOD = "https://github.com/user-attachments/files/123456/sub.csv"


class UrlAllowList(unittest.TestCase):
    def link(self, body: str) -> str | None:
        return att.find_link(body, REPO)

    def refused(self, body: str) -> None:
        with self.assertRaises(att.Refuse):
            self.link(body)

    def test_good_forms(self) -> None:
        self.assertEqual(self.link(f"[sub.csv]({GOOD})"), GOOD)
        self.assertEqual(self.link(f"```text\n[sub.csv]({GOOD})\n```"), GOOD)
        self.assertEqual(self.link(f"see {GOOD}."), GOOD)  # trailing dot dropped
        self.assertEqual(self.link(f"[a]({GOOD}) [b]({GOOD})"), GOOD)  # same link twice
        self.assertEqual(self.link("https://github.com/user-attachments/files/9/A_b-1.TXT"),
                         "https://github.com/user-attachments/files/9/A_b-1.TXT")
        legacy = "https://github.com/o/r/files/42/sub.csv"
        self.assertEqual(self.link(legacy), legacy)

    def test_no_link(self) -> None:
        self.assertIsNone(self.link("### Submission CSV\n\nid,infected,score\nhttps://example.org/x"))

    def test_bad_urls(self) -> None:
        for bad in (
            "https://evil.com/user-attachments/files/1/a.csv",           # host
            "https://github.com.evil.com/user-attachments/files/1/a.csv",
            "https://evil.com/github.com/user-attachments/files/1/a.csv",
            "http://github.com/user-attachments/files/1/a.csv",          # not https
            "https://github.com/user-attachments/files/1/a.csv?x=1",     # query
            "https://github.com/user-attachments/files/1/a.csv#f",       # fragment
            "https://github.com/user-attachments/files/1/../a.csv",      # path trick
            "https://github.com/user-attachments/files/1/%2e%2e/a.csv",
            "https://github.com/user-attachments/files/1/a/b.csv",
            "https://github.com/user-attachments/files/x/a.csv",         # id not digits
            "https://github.com/user-attachments/files//a.csv",
            "https://github.com/user-attachments/files/1/a.exe",         # type
            "https://github.com/user-attachments/files/1/a.csv.sh",
            "https://github.com/user-attachments/assets/0a1b2c3d-0000-0000-0000-000000000000",
            "https://github.com:443@evil.com/user-attachments/files/1/a.csv",
            "https://user@github.com/user-attachments/files/1/a.csv",
            "https://github.com/other/repo/files/42/sub.csv",            # legacy, other repo
            "https://github.com/o/r/files/42/sub.sh",
        ):
            with self.subTest(bad):
                self.refused(bad)

    def test_two_links(self) -> None:
        self.refused(f"{GOOD}\nhttps://github.com/user-attachments/files/2/b.csv")
        self.refused(f"{GOOD}\nhttps://evil.com/files/2/b.csv")


class FileChecks(unittest.TestCase):
    def check(self, data: bytes) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "f"
            p.write_bytes(data)
            att.check_file(p)

    def test_ok(self) -> None:
        self.check("# a\nid,infected,score\n".encode())
        self.check(b"x" * att.MAX_BYTES)

    def test_size_cap(self) -> None:
        with self.assertRaises(att.Refuse):
            self.check(b"x" * (att.MAX_BYTES + 1))

    def test_nul(self) -> None:
        with self.assertRaises(att.Refuse):
            self.check(b"id,infected\x00,score\n")

    def test_not_utf8(self) -> None:
        with self.assertRaises(att.Refuse):
            self.check(b"\xff\xfe\x00a")
        with self.assertRaises(att.Refuse):
            self.check(b"\xc3\x28")

    def test_normalise(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "f"
            p.write_bytes("﻿# a\r\nb\r\n\r\n".encode())
            att.normalise(p)
            self.assertEqual(p.read_text(), "# a\nb\n")


FAKE_CURL = """#!/usr/bin/env bash
echo "$*" >> "$CURL_LOG"
env | grep -E '^(SEEKER_KEY_PASS|LEDGER_TOKEN|GH_TOKEN)=' >> "$CURL_ENV_LOG" || true
out=""
while [ $# -gt 0 ]; do
  if [ "$1" = "--output" ]; then out="$2"; fi
  shift
done
[ -n "${CURL_FAIL:-}" ] && exit 22
cp "$CURL_FILE" "$out"
"""


class AttachmentDryRun(tt.DryRun):
    """Whole script with a toy key; the download is a fake curl that copies a local file."""

    def setUp(self) -> None:
        super().setUp()
        (self.bin / "curl").write_text(FAKE_CURL, encoding="utf-8")
        (self.bin / "curl").chmod(0o755)

    def csv_text(self) -> str:
        b = self.body()
        return b.split("```text\n", 1)[1].rsplit("\n```", 1)[0] + "\n"

    def run_att(self, data: bytes, body: str | None = None, fail: bool = False,
                ) -> subprocess.CompletedProcess[str]:
        f = self.r / "dl.bin"
        f.write_bytes(data)
        gh_body = self.r / "gh_body.md"
        gh_body.unlink(missing_ok=True)
        env = {"PATH": f"{self.bin}:{os.environ['PATH']}", "HOME": str(self.r),
               "GNUPGHOME": self.gnupg(), "RUNNER_TEMP": str(self.rt),
               "ISSUE_BODY": body if body is not None else f"### Submission CSV\n\n```text\n[sub.csv]({GOOD})\n```\n",
               "SUBMITTER": "alice", "ISSUE_NUMBER": "7", "GITHUB_REPOSITORY": REPO,
               "LEDGER_TOKEN": "tok-secret", "LEDGER_REPO": "o/l", "GH_TOKEN": "gh-secret",
               "LEDGER_CLONE_URL": str(self.remote), "SEEKER_KEY_PASS": tt.PASS,
               "GH_LOG": str(self.r / "gh.log"), "GH_BODY": str(gh_body),
               "CURL_LOG": str(self.r / "curl.log"), "CURL_ENV_LOG": str(self.r / "curl.env"),
               "CURL_FILE": str(f)}
        if fail:
            env["CURL_FAIL"] = "1"
        return subprocess.run(["bash", str(tt.SH)], env=env, capture_output=True, text=True)

    def reply(self) -> str:
        return (self.r / "gh_body.md").read_text()

    def test_attachment_scored_and_ledgered(self) -> None:
        text = self.csv_text()
        p = self.run_att(text.encode())
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("Seeker scoring report", self.reply())
        line = json.loads(self.ledger_lines()[0])
        self.assertEqual(line["input"], "attachment")
        self.assertEqual(line["sha256"], hashlib.sha256(text.encode()).hexdigest())
        args = (self.r / "curl.log").read_text()
        for flag in ("--proto =https", "--proto-redir =https", "--max-redirs", "--max-filesize 8388608",
                     "--max-time 60", GOOD):
            self.assertIn(flag, args)
        self.assertNotIn("-H", args.split())  # no header, so no auth header
        self.assertFalse((self.r / "curl.env").read_text().strip())  # no secret in curl env

    def test_body_route_unchanged_and_stamped(self) -> None:
        b = self.body()
        p = self.run_once(b)
        self.assertEqual(p.returncode, 0, p.stderr)
        line = json.loads(self.ledger_lines()[0])
        self.assertEqual(line["input"], "body")
        self.assertEqual(len(line["sha256"]), 64)
        self.assertFalse((self.r / "curl.log").exists())

    def test_attachment_equals_body_report(self) -> None:
        text = self.csv_text()
        p = self.run_att(text.encode())
        self.assertEqual(p.returncode, 0, p.stderr)
        sha_att = json.loads(self.ledger_lines()[0])["sha256"]
        self.assertEqual(sha_att, hashlib.sha256(text.encode()).hexdigest())

    def test_crlf_attachment(self) -> None:
        p = self.run_att(self.csv_text().replace("\n", "\r\n").encode())
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(len(self.ledger_lines()), 1)

    def assert_refused_no_ledger(self, p: subprocess.CompletedProcess[str], text: str) -> None:
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("REFUSED", self.reply())
        self.assertIn(text, self.reply())
        log = (self.r / "gh.log").read_text()
        self.assertIn("issue close 7", log)
        self.assertEqual(len(self.ledger_lines()), 0)
        for s in (p.stdout, p.stderr, self.reply()):
            self.assertNotIn(tt.PASS, s)

    def test_refusals(self) -> None:
        ok = self.csv_text().encode()
        two = f"```text\n{GOOD}\nhttps://github.com/user-attachments/files/2/b.csv\n```\n"
        cases = {
            "two links": (ok, two, False, "more than one"),
            "bad host": (ok, "```text\nhttps://evil.com/user-attachments/files/1/a.csv\n```\n", False,
                         "not a GitHub issue attachment"),
            "http": (ok, "http://github.com/user-attachments/files/1/a.csv", False,
                     "not a GitHub issue attachment"),
            "nul": (ok + b"\x00", None, False, "NUL"),
            "binary": (b"\xff\xfe\x00\x01", None, False, "not text"),
            "too large": (b"x" * (att.MAX_BYTES + 1), None, False, "8 MB"),
            "download fails": (ok, None, True, "could not be downloaded"),
        }
        for name, (data, body, fail, msg) in cases.items():
            with self.subTest(name):
                p = self.run_att(data, body, fail)
                self.assert_refused_no_ledger(p, msg)

    def test_no_csv_no_link_refused(self) -> None:
        p = self.run_att(b"", "### Submission CSV\n\nhello\n")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("unknown", self.reply())
        self.assertEqual(len(self.ledger_lines()), 0)


class FamilyDryRun(unittest.TestCase):
    """A Comb family submission of all public circuits through the attachment path, toy key."""

    def test_family_size(self) -> None:
        if not tt.shutil.which("gpg"):
            self.skipTest("gpg missing")
        n_bases = 20  # 20 x 300 = 6000 rows; big enough for a family bundle
        with tempfile.TemporaryDirectory() as td:
            r = Path(td)
            rng = random.Random(5)
            kd, pub = r / "answer_key", r / "public"
            kd.mkdir()
            labels: dict[str, object] = {}
            trojans: dict[str, object] = {}
            k = 0
            for b in range(n_bases):
                (pub / f"B{b:02d}").mkdir(parents=True)
                lines = []
                for s in ("K4", "K6", "gates"):
                    ids = []
                    for i in range(100):
                        cid = f"sc{k:05d}"
                        k += 1
                        ids.append(cid)
                        labels[cid] = ["t"] if i < 35 else None
                        if i < 35:
                            trojans[cid] = [{}]
                    lines.append(f"{s}: " + " ".join(ids))
                (pub / f"B{b:02d}" / "sets.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
            (kd / "labels.json").write_text(json.dumps(labels), encoding="utf-8")
            (kd / "trojans.json").write_text(json.dumps(trojans), encoding="utf-8")
            arc = r / "plain.tar.gz"
            tt.keypack.pack(kd, pub, tt.REL, "comb", arc)
            ids = sorted(labels)
            rows = "\n".join(f"{c},{int(rng.random() > 0.5)},{rng.random():.3f},," for c in ids)
            text = ("# seeker-release: seeker-comb-v2.0\n# subset: Comb\n# detector: random\n"
                    f"# team: t\nid,infected,score,count,locations\n{rows}\n")
            self.assertGreater(len(text), 65536)  # does not fit an issue body
            # reuse DryRun plumbing: build its remote/bin with this key
            t = AttachmentDryRun("test_attachment_scored_and_ledgered")
            t.td = tempfile.TemporaryDirectory()
            try:
                t.r = Path(t.td.name)
                shutil_copy(arc, t.r / "plain.tar.gz")
                _setup_remote(t)
                p = t.run_att(text.encode())
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertIn("Seeker scoring report", t.reply())
                line = json.loads(t.ledger_lines()[0])
                self.assertEqual((line["unit"], line["input"], line["n"]), ("family", "attachment", len(ids)))
            finally:
                t.td.cleanup()


def shutil_copy(a: Path, b: Path) -> None:
    b.write_bytes(a.read_bytes())


def _setup_remote(t: AttachmentDryRun) -> None:
    r = t.r
    t.remote = r / "remote.git"
    seed = r / "seed"
    for cmd in (["git", "init", "-q", "--bare", str(t.remote)],
                ["git", "clone", "-q", str(t.remote), str(seed)]):
        subprocess.run(cmd, check=True, capture_output=True)
    (seed / "keys").mkdir()
    subprocess.run(
        ["gpg", "--batch", "--quiet", "--pinentry-mode", "loopback", "--passphrase-fd", "0",
         "--symmetric", "--cipher-algo", "AES256", "--output",
         str(seed / "keys" / f"{tt.REL}-key.tar.gz.gpg"), str(r / "plain.tar.gz")],
        input=tt.PASS + "\n", text=True, check=True, capture_output=True,
        env={**os.environ, "GNUPGHOME": t.gnupg()})
    (seed / "ledger.jsonl").write_text("", encoding="utf-8")
    for cmd in (["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@x", "commit", "-qm", "i"],
                ["push", "-q", "origin", "HEAD"]):
        subprocess.run(["git", "-C", str(seed), *cmd], check=True, capture_output=True)
    t.bin = r / "bin"
    t.bin.mkdir()
    for name, body in (("gh", tt.FAKE_GH), ("curl", FAKE_CURL)):
        (t.bin / name).write_text(body, encoding="utf-8")
        (t.bin / name).chmod(0o755)
    t.rt = r / "runner"
    t.rt.mkdir()


if __name__ == "__main__":
    unittest.main()
