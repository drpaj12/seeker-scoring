# Security

This repository scores Trojan-detector submissions for Seeker's Dilemma v2.0. It holds no answer
key, label, seed or ledger. The key archives (encrypted) and the ledger live in a private
repository; the passphrase, ledger token and repository name are Actions secrets.

Scoring is manual (Peter, 2026-11-10). The workflow (`.github/workflows/score.yml`) never scores: it replies "staged"
with a fixed text, adds the label `staged` and leaves the issue open. It never reads the issue body, checks out no code,
decrypts no key and writes no ledger. The secrets `SEEKER_KEY_PASS`, `LEDGER_TOKEN` and `LEDGER_REPO` stay defined in the
repository settings but are unused by any workflow.

How the repository protects the key:

- Trigger: `issues: opened` only. Never `pull_request_target`; nothing from an issue or pull
  request is checked out or executed. Minimal permissions (`issues: write`, `contents: read`).
- Scoring is `scripts/score-local.sh` on the maintainer's machine, with plain key archives kept outside this repository;
  the passphrase is never used there. The issue body is data: it is parsed by a Python extractor and never
  interpolated into a shell line.
- An attached submission is downloaded only from a link that fully matches
  `https://github.com/user-attachments/files/<digits>/<name>.csv|.txt` (or the older
  `https://github.com/<this repo>/files/<digits>/<name>`), by `curl` over https only with a redirect
  limit, 8 MB cap and 60 s limit, with no credential. The file must be UTF-8 text without NUL bytes; it is then handled
  like a pasted body. One link only; anything else is refused with a reason, the issue closes, and no quota is used.
- Reports are aggregates over a hidden random sample; the scorer's error text never depends on a
  label. Scorer error output is not posted.
- The ledger line is pushed before the report is posted; a ledger update that cannot be pushed fails the run and no report
  is released.
- `main` is protected: changes to the workflow or the scorer need review.

Report a vulnerability privately to the maintainer (GitHub security advisory on this repository),
not in an issue.
