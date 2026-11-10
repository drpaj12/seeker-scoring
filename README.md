# seeker-scoring

Public scoring of hardware-Trojan detectors on Seeker's Dilemma v2.0 (Leman Russ III).
Open an issue with the "Score a detector" form, paste your CSV (or drag the file in), and the report comes back as a
comment; the issue then closes. The answer key stays private.

- Benchmarks (Comb 10, Seq 26, Proc 3): https://github.com/drpaj12/lemanrussIII/releases/tag/seeker-v2.0
- Format, subsets, report: [SUBMISSION.md](SUBMISSION.md)
- Releases scored: `seeker-comb-v2.0`, `seeker-seq-v2.0`, `seeker-proc-v2.0` (chosen from the
  `seeker-release` header of your CSV)

Quotas per GitHub account and release: 1 scored submission per 24 hours, 10 in total,
3 per benchmark, 3 family bundles. A refused submission does not count. GitHub limits an issue
body to 65,536 characters, so a family bundle is attached as a `.csv` or `.txt` file instead
(one file, 8 MB at most; see [SUBMISSION.md](SUBMISSION.md)).

The scorer in `lemanruss/` is a vendored copy at the commit in [PIN.md](PIN.md) (standard
library only). Security model: [SECURITY.md](SECURITY.md).

## Enabling (maintainer)

The job carries `if: false` and the workflow is disabled. To enable: protect `main`, replace
`if: false` in `.github/workflows/score.yml` by the `contains(...)` line in the comment above it,
then `gh workflow enable score.yml`.

## Tests

    python3 -m unittest discover -s tests

Static checks of the workflow and a dry run with a toy key (encrypted with a toy passphrase), a
toy ledger remote and a fake `gh`.
