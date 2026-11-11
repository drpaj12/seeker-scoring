# seeker-scoring

Public scoring of hardware-Trojan detectors on Seeker's Dilemma v2.0 (Leman Russ III).
Open an issue with the "Score a detector" form and paste your CSV (or drag the file in). The issue is a request: an
automatic reply says it is staged, and the maintainer scores it by hand (same scorer, key and ledger), usually within a
few days. The report is posted as a comment and the issue then closes. The answer key stays private.

- Benchmarks (Comb 10, Seq 26, Proc 3): https://github.com/drpaj12/lemanrussIII/releases/tag/seeker-v2.0
- Format, subsets, report: [SUBMISSION.md](SUBMISSION.md)
- Releases scored: `seeker-comb-v2.0`, `seeker-seq-v2.0`, `seeker-proc-v2.0` (chosen from the
  `seeker-release` header of your CSV)

Quotas per GitHub account and release: 1 scored submission per 24 hours, 10 in total,
3 per benchmark, 3 family bundles. A refused submission does not count. You can also email your CSV to jamieson dit peter at gmail dit com (also the route when your quota is used up); it is scored by hand the same way.
GitHub limits an issue
body to 65,536 characters, so a family bundle is attached as a `.csv` or `.txt` file instead
(one file, 8 MB at most; see [SUBMISSION.md](SUBMISSION.md)).

The scorer in `lemanruss/` is a vendored copy at the commit in [PIN.md](PIN.md) (standard
library only). Security model: [SECURITY.md](SECURITY.md).

## Maintainer: scoring by hand

GitHub Actions only stages a request (`.github/workflows/score.yml`: fixed reply, label `staged`, issue stays open).
Scoring runs on the maintainer's machine:

    scripts/score-local.sh <issue-number|csv-file> [--submitter ID] [--dry-run]

It uses the plain key archives and the cloned ledger, pushes the ledger line, then comments the report, removes
`staged`, closes and locks the issue (an emailed CSV gets a `report.md` instead). `--dry-run` scores against a scratch copy
of the ledger and posts nothing.

## Tests

    python3 -m unittest discover -s tests

Static checks of the staging workflow and runs of `scripts/score-local.sh` with a toy key, a toy
ledger remote and a fake `gh`.
