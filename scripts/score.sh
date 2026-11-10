#!/usr/bin/env bash
# One scoring run. Input only through the environment (see .github/workflows/score.yml):
#   ISSUE_BODY SUBMITTER ISSUE_NUMBER LEDGER_TOKEN LEDGER_REPO SEEKER_KEY_PASS RUNNER_TEMP
#   GITHUB_REPOSITORY (gh), optional LEDGER_CLONE_URL (tests only).
# Exit 0 after a posted report or a posted refusal; non-zero when the ledger cannot be
# updated or the scorer fails (nothing is reported as scored then).
set -euo pipefail
umask 077
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp="${RUNNER_TEMP:?}/seeker"
mkdir -p "$tmp"
trap 'rm -rf "$tmp/key" "$tmp/key.tar.gz" "$tmp/ledger"' EXIT
py() { PYTHONPATH="$root" python3 -m lemanruss.cli "$@"; }

post() {  # post FILE: comment, close, lock
  gh issue comment "$ISSUE_NUMBER" --body-file "$1" --repo "$GITHUB_REPOSITORY"
  gh issue close "$ISSUE_NUMBER" --repo "$GITHUB_REPOSITORY"
  gh issue lock "$ISSUE_NUMBER" --repo "$GITHUB_REPOSITORY"
}
refuse() {
  printf 'REFUSED: %s\n' "$1" > "$tmp/comment.md"
  post "$tmp/comment.md"
  exit 0
}

printf '%s' "$ISSUE_BODY" | py extract-csv > "$tmp/submission.csv"
release="$(sed -n 's/^# seeker-release: *\([A-Za-z0-9._-]*\) *$/\1/p' "$tmp/submission.csv" | head -n 1)"
case "$release" in
  seeker-comb-v2.0) family=comb ;;
  seeker-seq-v2.0) family=seq ;;
  seeker-proc-v2.0) family=proc ;;
  *) refuse "missing or unknown 'seeker-release' header (allowed: seeker-comb-v2.0, seeker-seq-v2.0, seeker-proc-v2.0)" ;;
esac

url="${LEDGER_CLONE_URL:-https://x-access-token:${LEDGER_TOKEN}@github.com/${LEDGER_REPO}.git}"
git clone --quiet --depth 1 "$url" "$tmp/ledger" > /dev/null 2>&1 || { echo "ledger clone failed" >&2; exit 1; }
archive="$tmp/ledger/keys/${release}-key.tar.gz.gpg"
[ -f "$archive" ] || { echo "key archive missing" >&2; exit 1; }
printf '%s\n' "$SEEKER_KEY_PASS" | gpg --batch --quiet --pinentry-mode loopback --passphrase-fd 0 \
  --decrypt --output "$tmp/key.tar.gz" "$archive" 2> /dev/null || { echo "key decryption failed" >&2; exit 1; }
keydir="$(py key-unpack "$tmp/key.tar.gz" --out "$tmp/key")"

rc=0
env -u SEEKER_KEY_PASS -u LEDGER_TOKEN PYTHONPATH="$root" python3 -m lemanruss.cli score \
  "$tmp/submission.csv" --key "$keydir" --ledger "$tmp/ledger/ledger.jsonl" \
  --submitter "$SUBMITTER" --out-dir "$tmp/out" > "$tmp/stdout.txt" 2> "$tmp/stderr.txt" || rc=$?
case "$rc" in
  0) ;;
  2) cp "$tmp/stdout.txt" "$tmp/comment.md"; post "$tmp/comment.md"; exit 0 ;;
  *) echo "scorer failed with exit $rc" >&2; exit 1 ;;
esac

# The ledger line must be on the remote before the report is released.
git -C "$tmp/ledger" add ledger.jsonl
git -C "$tmp/ledger" -c user.name=seeker-scorer -c user.email=scorer@users.noreply.github.com \
  commit --quiet -m "ledger: one scored submission" > /dev/null
git -C "$tmp/ledger" push --quiet origin HEAD > /dev/null 2>&1 || { echo "ledger push failed" >&2; exit 1; }
post "$tmp/out/report.md"
