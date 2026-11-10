# Submitting a detector to Seeker's Dilemma v2.0

You get a rating of your Trojan detector on the Seeker v2.0 circuits without the answer key being
public. Full design and threat model: `docs/specs/2026-11-02-scoring-design.md`.

## What you get and what you may use

- The public evaluation release: circuits (BLIF), a manifest, and one clean **golden** per base
  (the unmodified circuit). No label of any circuit is published.
- Train on the goldens (reference-based detectors) or on anything you generate yourself. Your
  detector should look at one circuit at a time.

## Pick a subset

Per benchmark the release has a golden and SeekerSets of exactly 100 circuits: `<benchmark>-K4`, `<benchmark>-K6`,
`<benchmark>-gates` and, where it exists, `<benchmark>-silicon`. `<benchmark>` is all its sets together and the
family bundle is `Comb`, `Seq` or `Proc`. Release names: `seeker-comb-v2.0`, `seeker-seq-v2.0`, `seeker-proc-v2.0`.
Each benchmark package also holds a neutral stimulus that no Trojan reacts to.

## Where to submit

Open an issue with the form `score-request` in https://github.com/drpaj12/seeker-scoring and paste the CSV. The
report comes back as a comment and the issue closes. Downloads:
https://github.com/drpaj12/lemanrussIII/releases/tag/seeker-v2.0

## File format

One CSV file. Header lines first, then the column row, then one row per circuit of the subset:

    # seeker-release: seeker-comb-v2.0
    # subset: C432-K4
    # detector: my-detector-v1
    # team: My Lab
    # contact: me@example.org
    id,infected,score,count,locations
    sc0012,1,0.93,2,n104;n377
    sc0013,0,0.04,0,
    sc0015,1,0.51,,

| column | meaning | tier |
|---|---|---|
| `id` | circuit id of the subset, every one exactly once | |
| `infected` | 0 or 1: does the circuit hold at least one Trojan, at your threshold | primary |
| `score` | finite number, higher = more likely infected (AUROC) | primary |
| `count` | Trojans you claim, 0 to 3; 0 exactly when `infected` is 0; may be empty | bonus |
| `locations` | up to **10** released net names, `;` separated, where you think a Trojan is; may be empty | bigger bonus |

A circuit with several Trojans is infected, and a multi-Trojan circuit you call clean is a miss:
the report shows your found-rate for 1, 2 and 3 Trojans. Headers: `contact` is optional, the others
are required. `docs/user/submission.schema.json` describes the same content as JSON.

Refused (nothing scored, no quota used): wrong release or subset, a missing, repeated or unknown
id, a duplicate, `NaN` or infinite score, `infected` not 0/1, a count outside 0..3 or disagreeing
with `infected`, more than 10 locations, a file over 5 MiB. The message names the line.

## What the report shows

Aggregates over a hidden random sample (70 of every 100-circuit set, new every time): confusion
matrix, TPR, FPR, precision, F1, accuracy, AUROC with a 95 percent interval (over bases for a family bundle; over circuits, optimistic, for a set or benchmark), found-rate
by Trojan count, the breakdown by mapping set, a comparison with the size-only control and the
sanity detector, then the count bonus (accuracy, error, rounded matrix) and the location bonus
(hit rate next to the chance level). Cells with fewer than 10 circuits are suppressed. Never
per-circuit results.

## Limits

One scored submission per 24 hours, 10 in total, 3 per benchmark and 3 family bundles per identity per release. A refused
submission does not count. The quota exists so that the key cannot be recovered by repeated
queries; the threat model and numbers are in the spec.
