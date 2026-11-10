"""Static checks of the workflow and a hand-replayed dry run with toy key, ledger and issue."""

from __future__ import annotations

import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lemanruss.score import keypack  # noqa: E402

WF = ROOT / ".github/workflows/score.yml"
SH = ROOT / "scripts/score.sh"
PASS = "toy-pass-phrase"
REL = "seeker-comb-v2.0"


class WorkflowStatic(unittest.TestCase):
    text = WF.read_text(encoding="utf-8")

    def test_yaml_parses(self) -> None:
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not installed")
        doc = yaml.safe_load(self.text)
        self.assertIn("score", doc["jobs"])
        self.assertEqual(doc[True]["issues"]["types"], ["opened"])  # YAML reads `on` as True

    def test_no_expression_in_run_blocks(self) -> None:
        in_run = False
        indent = 0
        for ln in self.text.splitlines():
            stripped = ln.lstrip()
            if re.match(r"-?\s*run:", stripped):
                if "${{" in ln:
                    self.fail("expression on a run: line")
                in_run = stripped.rstrip().endswith("|")
                indent = len(ln) - len(stripped)
                continue
            if in_run:
                if stripped and len(ln) - len(stripped) <= indent:
                    in_run = False
                elif "${{" in ln:
                    self.fail("expression inside a run: block")
        self.assertNotIn("${{", SH.read_text(encoding="utf-8"))

    def test_forbidden_constructs(self) -> None:
        both = "\n".join(ln for ln in (self.text + SH.read_text(encoding="utf-8")).splitlines()
                         if not ln.lstrip().startswith("#"))
        for bad in ("pull_request_target", "|| true", "set -x", "set -o xtrace", "ref:",
                    "upload-artifact", "workflow_run"):
            self.assertNotIn(bad, both, bad)

    def test_minimal_permissions_and_disabled(self) -> None:
        m = re.search(r"^permissions:\n((?:  .*\n)+)", self.text, re.M)
        assert m
        perms = dict(x.strip().split(": ") for x in m.group(1).splitlines())
        self.assertEqual(perms, {"issues": "write", "contents": "read"})
        self.assertRegex(self.text,
                         r"(?m)^    if: contains\(github\.event\.issue\.labels\.\*\.name, 'score-request'\)$")
        self.assertIn("group: score-ledger", self.text)

    def test_secret_only_via_env_and_gpg_stdin(self) -> None:
        sh = SH.read_text(encoding="utf-8")
        self.assertIn("--passphrase-fd 0", sh)
        self.assertIn("--pinentry-mode loopback", sh)
        self.assertIn("--batch", sh)
        self.assertNotIn("--passphrase ", sh)
        self.assertIsNone(re.search(r"echo[^\n]*SEEKER_KEY_PASS", sh))
        for ln in sh.splitlines():
            if "SEEKER_KEY_PASS" in ln:
                self.assertTrue(ln.lstrip().startswith(("printf '%s\\n' \"$SEEKER_KEY_PASS\"",
                                                        "#", "env -u")), ln)


def make_key(root: Path) -> tuple[Path, Path]:
    rng = random.Random(2)
    kd, pub = root / "answer_key", root / "public"
    kd.mkdir()
    labels: dict[str, object] = {}
    trojans: dict[str, object] = {}
    k = 0
    (pub / "C432").mkdir(parents=True)
    lines = []
    for s in ("K4", "K6", "gates"):
        ids = []
        for i in range(100):
            cid = f"sc{k:04d}"
            k += 1
            ids.append(cid)
            if i < 35:
                labels[cid] = ["t"]
                trojans[cid] = [{}]
            else:
                labels[cid] = None
        lines.append(f"{s}: " + " ".join(rng.sample(ids, 100)))
    (pub / "C432" / "sets.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (kd / "labels.json").write_text(json.dumps(labels), encoding="utf-8")
    (kd / "trojans.json").write_text(json.dumps(trojans), encoding="utf-8")
    return kd, pub


FAKE_GH = """#!/usr/bin/env bash
echo "$*" >> "$GH_LOG"
while [ $# -gt 0 ]; do
  if [ "$1" = "--body-file" ]; then cp "$2" "$GH_BODY"; fi
  shift
done
"""


class DryRun(unittest.TestCase):
    def setUp(self) -> None:
        if not shutil.which("gpg"):
            self.skipTest("gpg missing")
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        r = Path(self.td.name)
        self.r = r
        kd, pub = make_key(r)
        arc = r / "plain.tar.gz"
        keypack.pack(kd, pub, REL, "comb", arc)
        # toy ledger remote (bare) with the encrypted key and an empty ledger
        self.remote = r / "remote.git"
        seed = r / "seed"
        for cmd in (["git", "init", "-q", "--bare", str(self.remote)],
                    ["git", "clone", "-q", str(self.remote), str(seed)]):
            subprocess.run(cmd, check=True, capture_output=True)
        (seed / "keys").mkdir()
        subprocess.run(
            ["gpg", "--batch", "--quiet", "--pinentry-mode", "loopback", "--passphrase-fd", "0",
             "--symmetric", "--cipher-algo", "AES256", "--output",
             str(seed / "keys" / f"{REL}-key.tar.gz.gpg"), str(arc)],
            input=PASS + "\n", text=True, check=True, capture_output=True,
            env={**os.environ, "GNUPGHOME": self.gnupg()})
        (seed / "ledger.jsonl").write_text("", encoding="utf-8")
        for cmd in (["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@x", "commit", "-qm", "i"],
                    ["push", "-q", "origin", "HEAD"]):
            subprocess.run(["git", "-C", str(seed), *cmd], check=True, capture_output=True)
        self.bin = r / "bin"
        self.bin.mkdir()
        (self.bin / "gh").write_text(FAKE_GH, encoding="utf-8")
        (self.bin / "gh").chmod(0o755)
        self.rt = r / "runner"
        self.rt.mkdir()
        self.ids = sorted(json.loads((kd / "labels.json").read_text()))[:100]

    def gnupg(self) -> str:
        d = self.r / "gnupg"
        d.mkdir(mode=0o700, exist_ok=True)
        return str(d)

    def body(self, unit: str = "C432-K4", release: str = REL) -> str:
        sub = json.loads(
            subprocess.run(
                [sys.executable, "-c",
                 "import json,sys;from pathlib import Path;"
                 "from lemanruss.score.subsets import load_subsets;"
                 "print(json.dumps(load_subsets(Path(sys.argv[1]))[1][sys.argv[2]]))",
                 str(self.unpacked() / "subsets.json"), unit],
                capture_output=True, text=True, check=True, cwd=ROOT,
                env={**os.environ, "PYTHONPATH": str(ROOT)}).stdout)
        rows = "\n".join(f"{c},{i % 2},{(i * 7 % 10) / 10},," for i, c in enumerate(sub))
        return ("### Submission CSV\n\n```text\n"
                f"# seeker-release: {release}\n# subset: {unit}\n# detector: d\n# team: t\n"
                f"id,infected,score,count,locations\n{rows}\n```\n")

    def unpacked(self) -> Path:
        d = self.r / "unp"
        if not d.exists():
            keypack.unpack(self.r / "plain.tar.gz", d)
        return d / f"{REL}-key"

    def run_once(self, body: str, remote: Path | None = None) -> subprocess.CompletedProcess[str]:
        gh_body = self.r / "gh_body.md"
        gh_body.unlink(missing_ok=True)
        env = {"PATH": f"{self.bin}:{os.environ['PATH']}", "HOME": str(self.r),
               "GNUPGHOME": self.gnupg(), "RUNNER_TEMP": str(self.rt),
               "ISSUE_BODY": body, "SUBMITTER": "alice", "ISSUE_NUMBER": "7",
               "GITHUB_REPOSITORY": "o/r", "LEDGER_TOKEN": "x", "LEDGER_REPO": "o/l",
               "LEDGER_CLONE_URL": str(remote or self.remote), "SEEKER_KEY_PASS": PASS,
               "GH_LOG": str(self.r / "gh.log"), "GH_BODY": str(gh_body)}
        return subprocess.run(["bash", str(SH)], env=env, capture_output=True, text=True)

    def ledger_lines(self) -> list[str]:
        out = subprocess.run(["git", "-C", str(self.remote), "show", "HEAD:ledger.jsonl"],
                             capture_output=True, text=True, check=True).stdout
        return out.splitlines()

    def test_report_ledger_and_quota(self) -> None:
        p = self.run_once(self.body())
        self.assertEqual(p.returncode, 0, p.stderr)
        report = (self.r / "gh_body.md").read_text()
        self.assertIn("Seeker scoring report", report)
        lines = self.ledger_lines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["unit"], "cell")
        log = (self.r / "gh.log").read_text()
        for verb in ("issue comment 7", "issue close 7", "issue lock 7"):
            self.assertIn(verb, log)
        for s in (p.stdout, p.stderr, report, lines[0]):
            self.assertNotIn(PASS, s)
        self.assertFalse((self.rt / "seeker" / "key").exists())  # cleaned up
        # second call inside 24 h: refused with the retry message, ledger unchanged
        p2 = self.run_once(self.body("C432-K6"))
        self.assertEqual(p2.returncode, 0, p2.stderr)
        self.assertIn("retry in", (self.r / "gh_body.md").read_text())
        self.assertEqual(len(self.ledger_lines()), 1)
        self.assertNotIn("jamieson dit peter", (self.r / "gh_body.md").read_text())

    def test_quota_used_up_points_to_email(self) -> None:
        work = self.r / "fill"
        subprocess.run(["git", "clone", "-q", str(self.remote), str(work)], check=True,
                       capture_output=True)
        old = [json.dumps({"t": 0.0, "submitter": "alice", "release": REL, "unit": "cell",
                           "benchmark": f"B{i}"}) for i in range(10)]
        (work / "ledger.jsonl").write_text("\n".join(old) + "\n", encoding="utf-8")
        for cmd in (["add", "ledger.jsonl"],
                    ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "fill"],
                    ["push", "-q", "origin", "HEAD"]):
            subprocess.run(["git", "-C", str(work), *cmd], check=True, capture_output=True)
        p = self.run_once(self.body())
        self.assertEqual(p.returncode, 0, p.stderr)
        text = (self.r / "gh_body.md").read_text()
        self.assertIn("REFUSED: limit reached", text)
        self.assertIn("jamieson dit peter at gmail dit com", text)
        self.assertEqual(len(self.ledger_lines()), 10)

    def test_unknown_release_refused_without_key(self) -> None:
        p = self.run_once(self.body(release="seeker-evil-v9"))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("unknown", (self.r / "gh_body.md").read_text())
        self.assertEqual(len(self.ledger_lines()), 0)

    def test_ledger_push_failure_fails_the_run(self) -> None:
        hook = self.remote / "hooks" / "pre-receive"
        hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        hook.chmod(0o755)
        p = self.run_once(self.body())
        self.assertNotEqual(p.returncode, 0)
        self.assertFalse((self.r / "gh_body.md").exists())  # no report released
        self.assertIn("ledger push failed", p.stderr)

    def test_wrong_passphrase_fails(self) -> None:
        p = subprocess.run(["bash", str(SH)], capture_output=True, text=True, env={
            "PATH": f"{self.bin}:{os.environ['PATH']}", "HOME": str(self.r),
            "GNUPGHOME": self.gnupg(), "RUNNER_TEMP": str(self.rt),
            "ISSUE_BODY": self.body(), "SUBMITTER": "a", "ISSUE_NUMBER": "1",
            "GITHUB_REPOSITORY": "o/r", "LEDGER_TOKEN": "x", "LEDGER_REPO": "o/l",
            "LEDGER_CLONE_URL": str(self.remote), "SEEKER_KEY_PASS": "wrong",
            "GH_LOG": str(self.r / "gh.log"), "GH_BODY": str(self.r / "b.md")})
        self.assertNotEqual(p.returncode, 0)
        self.assertNotIn("wrong", p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
