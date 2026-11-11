"""Static checks of the workflow and a hand-replayed dry run with toy key, ledger and issue."""

from __future__ import annotations

import json
import os
import random
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lemanruss.score import keypack  # noqa: E402

WF = ROOT / ".github/workflows/score.yml"
SH = ROOT / "scripts/score-local.sh"
REL = "seeker-comb-v2.0"


class WorkflowStatic(unittest.TestCase):
    text = WF.read_text(encoding="utf-8")

    def test_yaml_parses(self) -> None:
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not installed")
        doc = yaml.safe_load(self.text)
        self.assertIn("stage", doc["jobs"])
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
                    "upload-artifact", "workflow_run", "actions/checkout"):
            self.assertNotIn(bad, both, bad)

    def test_minimal_permissions_and_label_gate(self) -> None:
        m = re.search(r"^permissions:\n((?:  .*\n)+)", self.text, re.M)
        assert m
        perms = dict(x.strip().split(": ") for x in m.group(1).splitlines())
        self.assertEqual(perms, {"issues": "write", "contents": "read"})
        self.assertRegex(self.text,
                         r"(?m)^    if: contains\(github\.event\.issue\.labels\.\*\.name, 'score-request'\)$")

    def test_workflow_only_stages(self) -> None:
        # no scoring, no key, no ledger, no issue body, no close in Actions
        code = "\n".join(ln for ln in self.text.splitlines() if not ln.lstrip().startswith("#"))
        for bad in ("secrets.", "SEEKER_KEY_PASS", "LEDGER", "issue.body", "gpg", "lemanruss",
                    "score.sh", "issue close", "issue lock"):
            self.assertNotIn(bad, code, bad)
        self.assertIn("--add-label staged", code)
        self.assertIn("label create staged", code)
        self.assertIn("staged for the maintainer", code)

    def test_issue_form_says_hand_scored(self) -> None:
        form = (ROOT / ".github/ISSUE_TEMPLATE/score-request.yml").read_text(encoding="utf-8")
        self.assertIn("by hand", form)
        self.assertIn("jamieson dit peter at gmail dit com", form)


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
if [ "$1 $2" = "issue view" ]; then
  case "$*" in
    *author*) if [[ "$*" == *login* ]]; then echo alice; else cat "$GH_ISSUE_BODY"; fi ;;
    *) cat "$GH_ISSUE_BODY" ;;
  esac
  exit 0
fi
while [ $# -gt 0 ]; do
  if [ "$1" = "--body-file" ]; then cp "$2" "$GH_BODY"; fi
  shift
done
"""


class LocalBase(unittest.TestCase):
    """Plumbing only (toy key, ledger remote, fake gh); no tests here."""


    extra_env: dict[str, str] = {}

    def build_key(self, r: Path) -> tuple[Path, Path]:
        return make_key(r)

    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        r = Path(self.td.name)
        self.r = r
        kd, pub = self.build_key(r)
        self.keys = r / "keys"
        self.keys.mkdir()
        keypack.pack(kd, pub, REL, "comb", self.keys / f"{REL}-key.tar.gz")
        self.remote = r / "remote.git"
        seed = r / "seed"
        for cmd in (["git", "init", "-q", "--bare", str(self.remote)],
                    ["git", "clone", "-q", str(self.remote), str(seed)]):
            subprocess.run(cmd, check=True, capture_output=True)
        (seed / "ledger.jsonl").write_text("", encoding="utf-8")
        for cmd in (["add", "-A"],
                    ["-c", "user.name=t", "-c", "user.email=t@x", "commit", "-qm", "i"],
                    ["push", "-q", "origin", "HEAD"]):
            subprocess.run(["git", "-C", str(seed), *cmd], check=True, capture_output=True)
        self.ledger = r / "ledger"
        subprocess.run(["git", "clone", "-q", str(self.remote), str(self.ledger)], check=True,
                       capture_output=True)
        for k, v in (("user.name", "t"), ("user.email", "t@x")):
            subprocess.run(["git", "-C", str(self.ledger), "config", k, v], check=True)
        self.bin = r / "bin"
        self.bin.mkdir()
        (self.bin / "gh").write_text(FAKE_GH, encoding="utf-8")
        (self.bin / "gh").chmod(0o755)
        self.unp = r / "unp"
        keypack.unpack(self.keys / f"{REL}-key.tar.gz", self.unp)

    def csv(self, unit: str = "C432-K4", release: str = REL) -> str:
        sub = json.loads(
            subprocess.run(
                [sys.executable, "-c",
                 "import json,sys;from pathlib import Path;"
                 "from lemanruss.score.subsets import load_subsets;"
                 "print(json.dumps(load_subsets(Path(sys.argv[1]))[1][sys.argv[2]]))",
                 str(self.unp / f"{REL}-key" / "subsets.json"), unit],
                capture_output=True, text=True, check=True, cwd=ROOT,
                env={**os.environ, "PYTHONPATH": str(ROOT)}).stdout)
        rows = "\n".join(f"{c},{i % 2},{(i * 7 % 10) / 10},," for i, c in enumerate(sub))
        return (f"# seeker-release: {release}\n# subset: {unit}\n# detector: d\n# team: t\n"
                f"id,infected,score,count,locations\n{rows}\n")

    def body(self, **kw: str) -> str:
        return f"### Submission CSV\n\n```text\n{self.csv(**kw)}```\n"

    def run_local(self, *args: str, body: str | None = None) -> subprocess.CompletedProcess[str]:
        gh_body = self.r / "gh_body.md"
        gh_body.unlink(missing_ok=True)
        issue_body = self.r / "issue_body.md"
        issue_body.write_text(body if body is not None else self.body(), encoding="utf-8")
        env = {"PATH": f"{self.bin}:{os.environ['PATH']}", "HOME": str(self.r),
               "KEYS_DIR": str(self.keys), "LEDGER_DIR": str(self.ledger),
               "SEEKER_REPO": "o/r", "EMAIL_OUT_DIR": str(self.r / "email"),
               "GH_LOG": str(self.r / "gh.log"), "GH_BODY": str(gh_body),
               "GH_ISSUE_BODY": str(issue_body), **self.extra_env}
        return subprocess.run(["bash", str(SH), *args], env=env, capture_output=True, text=True)

    def remote_ledger(self) -> list[str]:
        out = subprocess.run(["git", "-C", str(self.remote), "show", "HEAD:ledger.jsonl"],
                             capture_output=True, text=True, check=True).stdout
        return out.splitlines()


class LocalScoring(LocalBase):
    def test_issue_report_ledger_and_quota(self) -> None:
        p = self.run_local("7")
        self.assertEqual(p.returncode, 0, p.stderr)
        report = (self.r / "gh_body.md").read_text()
        self.assertIn("Seeker scoring report", report)
        lines = self.remote_ledger()
        self.assertEqual(len(lines), 1)
        entry = json.loads(lines[0])
        self.assertEqual(entry["unit"], "cell")
        self.assertEqual(entry["input"], "issue")
        self.assertEqual(entry["submitter"], "alice")
        self.assertEqual(len(entry["sha256"]), 64)
        log = (self.r / "gh.log").read_text()
        for verb in ("issue comment 7", "issue edit 7 --remove-label staged", "issue close 7",
                     "issue lock 7"):
            self.assertIn(verb, log)
        # second call inside 24 h: refused with the retry message, ledger unchanged
        (self.r / "gh.log").unlink()
        p2 = self.run_local("8", body=self.body(unit="C432-K6"))
        self.assertEqual(p2.returncode, 0, p2.stderr)
        self.assertIn("retry in", (self.r / "gh_body.md").read_text())
        self.assertEqual(len(self.remote_ledger()), 1)

    def test_dry_run_changes_nothing(self) -> None:
        p = self.run_local("7", "--dry-run")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("Seeker scoring report", p.stdout)
        self.assertEqual(self.remote_ledger(), [])
        self.assertEqual((self.ledger / "ledger.jsonl").read_text(), "")
        log = (self.r / "gh.log").read_text()
        for verb in ("issue comment", "issue edit", "issue close", "issue lock"):
            self.assertNotIn(verb, log)

    def test_email_csv_report_file_and_stamp(self) -> None:
        f = self.r / "mail.csv"
        f.write_text(self.csv(), encoding="utf-8")
        p = self.run_local(str(f), "--submitter", "email:a@b.c")
        self.assertEqual(p.returncode, 0, p.stderr)
        entry = json.loads(self.remote_ledger()[0])
        self.assertEqual((entry["input"], entry["submitter"]), ("email", "email:a@b.c"))
        reports = list((self.r / "email" / "reports").glob("*-report.md"))
        self.assertEqual(len(reports), 1)
        self.assertIn("Seeker scoring report", reports[0].read_text())
        self.assertNotIn("issue", (self.r / "gh.log").read_text() if (self.r / "gh.log").exists() else "")

    def test_email_needs_submitter(self) -> None:
        f = self.r / "mail.csv"
        f.write_text(self.csv(), encoding="utf-8")
        self.assertNotEqual(self.run_local(str(f)).returncode, 0)

    def test_quota_used_up_points_to_email(self) -> None:
        old = [json.dumps({"t": 0.0, "submitter": "alice", "release": REL, "unit": "cell",
                           "benchmark": f"B{i}"}) for i in range(10)]
        (self.ledger / "ledger.jsonl").write_text("\n".join(old) + "\n", encoding="utf-8")
        for cmd in (["add", "ledger.jsonl"], ["commit", "-q", "-m", "fill"],
                    ["push", "-q", "origin", "HEAD"]):
            subprocess.run(["git", "-C", str(self.ledger), *cmd], check=True, capture_output=True)
        p = self.run_local("7")
        self.assertEqual(p.returncode, 0, p.stderr)
        text = (self.r / "gh_body.md").read_text()
        self.assertIn("REFUSED: limit reached", text)
        self.assertIn("jamieson dit peter at gmail dit com", text)
        self.assertEqual(len(self.remote_ledger()), 10)

    def test_unknown_release_refused_without_key(self) -> None:
        p = self.run_local("7", body=self.body(release="seeker-evil-v9"))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("unknown", (self.r / "gh_body.md").read_text())
        self.assertEqual(self.remote_ledger(), [])

    def test_ledger_push_failure_releases_no_report(self) -> None:
        hook = self.remote / "hooks" / "pre-receive"
        hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        hook.chmod(0o755)
        p = self.run_local("7")
        self.assertNotEqual(p.returncode, 0)
        self.assertFalse((self.r / "gh_body.md").exists())  # no report released
        self.assertIn("ledger push failed", p.stderr)

    def test_no_passphrase_use(self) -> None:
        sh = SH.read_text(encoding="utf-8")
        for bad in ("SEEKER_KEY_PASS", "seeker-pass", "gpg", "--passphrase"):
            self.assertNotIn(bad, sh)


if __name__ == "__main__":
    unittest.main()
