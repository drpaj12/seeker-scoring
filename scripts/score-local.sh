#!/usr/bin/env bash
# Manual scoring on the maintainer's machine. NOT run by GitHub Actions.
#   score-local.sh <issue-number|csv-file> [--submitter ID] [--dry-run]
# An issue number: fetch the staged request with gh, score it, push the ledger line, then comment
# the report, remove `staged`, close and lock the issue. A CSV file (emailed submission): score it
# and write report.md for the maintainer to email; --submitter is required (e.g. "email:a@b.c").
# --dry-run does everything except push the ledger and post/edit anything: it scores against a
# scratch copy of the ledger and prints the report.
# Keys: PLAIN archives (never the passphrase). Environment overrides (tests):
#   KEYS_DIR LEDGER_DIR SEEKER_REPO EMAIL_OUT_DIR
set -euo pipefail
umask 077
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ws=/home/jamiespa/odin3-ws/work
KEYS_DIR="${KEYS_DIR:-$ws/lr-v2-release/keys}"
LEDGER_DIR="${LEDGER_DIR:-$ws/seeker-ledger}"
SEEKER_REPO="${SEEKER_REPO:-drpaj12/seeker-scoring}"
EMAIL_OUT_DIR="${EMAIL_OUT_DIR:-$ws/seeker-email}"
EMAIL_FALLBACK="jamieson dit peter at gmail dit com"

target="" submitter="" dry=0
while [ $# -gt 0 ]; do
  case "$1" in
    --submitter) submitter="${2:?--submitter needs a value}"; shift 2 ;;
    --dry-run) dry=1; shift ;;
    -*) echo "unknown option $1" >&2; exit 64 ;;
    *) [ -z "$target" ] || { echo "one target only" >&2; exit 64; }; target="$1"; shift ;;
  esac
done
[ -n "$target" ] || { echo "usage: score-local.sh <issue-number|csv-file> [--submitter ID] [--dry-run]" >&2; exit 64; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
py() { PYTHONPATH="$root" python3 -m lemanruss.cli "$@"; }
att() { python3 "$root/scripts/attachment.py" "$@"; }

issue=""
if [ -f "$target" ]; then
  input=email
  [ -n "$submitter" ] || { echo "--submitter is required for a CSV file" >&2; exit 64; }
  cp "$target" "$tmp/submission.csv"
  att check "$tmp/submission.csv" || exit 2
  att normalise "$tmp/submission.csv"
elif [[ "$target" =~ ^[0-9]+$ ]]; then
  issue="$target"
  input=issue
  gh issue view "$issue" --repo "$SEEKER_REPO" --json body,author \
    --jq '.body' > "$tmp/body.txt"
  if [ -z "$submitter" ]; then
    submitter="$(gh issue view "$issue" --repo "$SEEKER_REPO" --json author --jq '.author.login')"
  fi
else
  echo "target must be an issue number or an existing CSV file" >&2; exit 64
fi

finish_issue() {  # finish_issue FILE: comment, unstage, close, lock (not on dry run)
  if [ "$dry" -eq 1 ]; then echo "--- dry run: would post this comment and close issue $issue ---"; cat "$1"; return; fi
  gh issue comment "$issue" --body-file "$1" --repo "$SEEKER_REPO"
  gh issue edit "$issue" --remove-label staged --repo "$SEEKER_REPO"
  gh issue close "$issue" --repo "$SEEKER_REPO"
  gh issue lock "$issue" --repo "$SEEKER_REPO"
}
refuse() {
  printf 'REFUSED: %s\n' "$1" > "$tmp/comment.md"
  if [ -n "$issue" ]; then finish_issue "$tmp/comment.md"; else cat "$tmp/comment.md"; fi
  exit 0
}

if [ -n "$issue" ]; then
  py extract-csv < "$tmp/body.txt" > "$tmp/submission.csv"
  if ! grep -q '^id,infected,score' "$tmp/submission.csv"; then
    rc=0
    link="$(att link "$SEEKER_REPO" < "$tmp/body.txt")" || rc=$?
    [ "$rc" -eq 0 ] || refuse "$link"
    if [ "$link" != NONE ]; then
      input=attachment
      curl -q --silent --show-error --fail --location --proto =https --proto-redir =https \
        --max-redirs 5 --max-filesize 8388608 --max-time 60 --output "$tmp/attachment.bin" "$link" \
        || refuse "the attachment could not be downloaded (too large, unreachable or not found)"
      rc=0
      msg="$(att check "$tmp/attachment.bin")" || rc=$?
      [ "$rc" -eq 0 ] || refuse "$msg"
      att normalise "$tmp/attachment.bin"
      mv "$tmp/attachment.bin" "$tmp/submission.csv"
    fi
  fi
fi
sha="$(sha256sum "$tmp/submission.csv" | cut -d' ' -f1)"
release="$(sed -n 's/^# seeker-release: *\([A-Za-z0-9._-]*\) *$/\1/p' "$tmp/submission.csv" | head -n 1)"
case "$release" in
  seeker-comb-v2.0|seeker-seq-v2.0|seeker-proc-v2.0) ;;
  *) refuse "missing or unknown 'seeker-release' header (allowed: seeker-comb-v2.0, seeker-seq-v2.0, seeker-proc-v2.0)" ;;
esac

archive="$KEYS_DIR/${release}-key.tar.gz"
[ -f "$archive" ] || { echo "plain key archive missing: $archive" >&2; exit 1; }
keydir="$(py key-unpack "$archive" --out "$tmp/key")"

git -C "$LEDGER_DIR" pull --quiet --ff-only
if [ "$dry" -eq 1 ]; then
  cp "$LEDGER_DIR/ledger.jsonl" "$tmp/ledger.jsonl"
  ledger="$tmp/ledger.jsonl"
else
  [ -z "$(git -C "$LEDGER_DIR" status --porcelain)" ] || { echo "ledger clone is not clean" >&2; exit 1; }
  ledger="$LEDGER_DIR/ledger.jsonl"
fi

rc=0
py score "$tmp/submission.csv" --key "$keydir" --ledger "$ledger" \
  --submitter "$submitter" --out-dir "$tmp/out" > "$tmp/stdout.txt" 2> "$tmp/stderr.txt" || rc=$?
case "$rc" in
  0) ;;
  2) cp "$tmp/stdout.txt" "$tmp/comment.md"
     if grep -q "^REFUSED: limit reached" "$tmp/comment.md"; then
       printf '\nNo scored submissions left for this release on this account: email the CSV to %s\n' \
         "$EMAIL_FALLBACK" >> "$tmp/comment.md"
       printf 'and the maintainer scores it by hand with the same scorer and key.\n' >> "$tmp/comment.md"
     fi
     if [ -n "$issue" ]; then finish_issue "$tmp/comment.md"; else cat "$tmp/comment.md"; fi
     exit 0 ;;
  *) echo "scorer failed with exit $rc" >&2; exit 1 ;;
esac

if [ "$dry" -eq 0 ]; then
  att stamp "$ledger" "$input" "$sha"
  # The ledger line must be on the remote before the report is released.
  git -C "$LEDGER_DIR" add ledger.jsonl
  git -C "$LEDGER_DIR" commit --quiet -m "ledger: one scored submission ($input)" > /dev/null
  git -C "$LEDGER_DIR" push --quiet origin HEAD > /dev/null 2>&1 || { echo "ledger push failed" >&2; exit 1; }
fi

if [ -n "$issue" ]; then
  finish_issue "$tmp/out/report.md"
else
  if [ "$dry" -eq 1 ]; then
    echo "--- dry run: report for the email route ---"; cat "$tmp/out/report.md"
  else
    mkdir -p "$EMAIL_OUT_DIR/reports"
    dest="$EMAIL_OUT_DIR/reports/$(date +%F)-${sha:0:8}-report.md"
    cp "$tmp/out/report.md" "$dest"
    echo "report: $dest"
  fi
fi
echo "input=$input sha256=$sha release=$release submitter=$submitter dry_run=$dry"
