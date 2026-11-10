# Security

This repository scores Trojan-detector submissions for Seeker's Dilemma v2.0. It holds no answer
key, label, seed or ledger. The key archives (encrypted) and the ledger live in a private
repository; the passphrase, ledger token and repository name are Actions secrets.

How the workflow protects them:

- Trigger: `issues: opened` only. Never `pull_request_target`; nothing from an issue or pull
  request is checked out or executed. The workflow runs the code on the default branch.
- The issue body is data. It reaches `scripts/score.sh` through an environment variable and is
  parsed by a Python extractor; it is never interpolated into a shell line.
- Minimal permissions (`issues: write`, `contents: read`); one run at a time (concurrency group).
- The key archive is decrypted with `gpg` reading the passphrase from standard input, unpacked
  under the runner temp directory, never printed, never uploaded as an artifact, and removed at
  the end of the run. The scorer process runs without the passphrase and ledger token.
- Reports are aggregates over a hidden random sample; the scorer's error text never depends on a
  label. Scorer error output is not posted.
- A ledger update that cannot be pushed fails the run, and no report is released.
- `main` is protected: changes to the workflow or the scorer need review.

Report a vulnerability privately to the maintainer (GitHub security advisory on this repository),
not in an issue.
