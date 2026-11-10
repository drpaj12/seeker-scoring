"""`lemanruss build`: run the first benchmark build over a directory of Verilog base designs."""

from __future__ import annotations

import argparse
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lemanruss")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build", help="build and verify a first HTL benchmark")
    build_parser.add_argument("--base-dir", type=Path, required=True)
    build_parser.add_argument("--out", type=Path, required=True)

    fam = subparsers.add_parser("family", help="build a Seeker v2.0 family (comb or seq)")
    fam.add_argument("name", choices=["Seeker-Comb", "Seeker-Seq"])
    fam.add_argument("--bases", type=Path, nargs="+", required=True)
    fam.add_argument("--out", type=Path, required=True)
    fam.add_argument("--seed", type=int, default=None,
                     help="generator seed (default: LEMANRUSS_RELEASE_SEED or LEMANRUSS_SEED_FILE)")
    fam.add_argument("--max-blocks", type=int, default=30000)
    fam.add_argument("--workers", type=int, default=1)

    fver = subparsers.add_parser(
        "family-verify", help="cross-check, fire check and cec of a family build tree")
    fver.add_argument("root", type=Path)
    fver.add_argument("--workers", type=int, default=4)

    ver = subparsers.add_parser("verify", help="independent check of a release directory")
    ver.add_argument("release", type=Path)
    ver.add_argument("--workers", type=int, default=6)
    ver.add_argument("--scratch", type=Path, required=True)
    ver.add_argument("--json", type=Path, required=True, dest="json_out")

    rel = subparsers.add_parser("release", help="package a family build as a release directory")
    rel.add_argument("root", type=Path)
    rel.add_argument("--out", type=Path, required=True)
    rel.add_argument("--family", choices=["Seeker-Comb", "Seeker-Seq"], required=True)
    rel.add_argument("--licences", type=Path)
    rel.add_argument("--odin3-build-pin", required=True)
    rel.add_argument("--odin3-checkout", required=True)
    rel.add_argument("--abc", required=True)
    rel.add_argument("--version", default="2.0-rc1")
    rel.add_argument("--n200", action="store_true", help="n = 200 per base build tree (round 8)")
    rel.add_argument("--exclude-base", action="append", default=[], metavar="BASE=REASON",
                     help="built but not released base, with the reason (repeatable)")

    rr = subparsers.add_parser("release-report", help="markdown report from verify JSON files")
    rr.add_argument("reports", type=Path, nargs="+")
    rr.add_argument("--out", type=Path, required=True)
    rr.add_argument("--title", default="Release v2.0-rc1: verify report (2026-10-31)")

    rs = subparsers.add_parser("restructure", help="apply the ABC restructurings to a family")
    rs.add_argument("root", type=Path)
    rs.add_argument("--short", required=True, choices=["sc", "ss"])
    rs.add_argument("--workers", type=int, default=4)

    h2b = subparsers.add_parser("hdl2blif", help="Verilog bases to .names-only BLIF via Odin III")
    h2b.add_argument("--out", type=Path, required=True)
    h2b.add_argument("--arch", type=Path, help="architecture XML: VTR-primitive designs")
    h2b.add_argument("--flatten", action="store_true", help="flatten module instances")
    h2b.add_argument("--top-stem", action="store_true", help="top module = the file name stem")
    h2b.add_argument("--timeout", type=int, default=600)
    h2b.add_argument("--mem-gb", type=int, default=10)
    h2b.add_argument("sources", type=Path, nargs="+")

    bs = subparsers.add_parser("bases", help="bases from the Mimir registry (round 5)")
    bs.add_argument("suite", choices=["verilogeval", "vtr-verilog"])
    bs.add_argument("--mimir-root", type=Path, required=True)
    bs.add_argument("--out", type=Path, required=True)

    rt = subparsers.add_parser("rtl-tb", help="RTL Trojans: sim_tb vs iverilog (round 5)")
    rt.add_argument("--mimir-root", type=Path, required=True)
    rt.add_argument("--out", type=Path, required=True)
    rt.add_argument("--odin3-bin", type=Path, required=True)
    rt.add_argument("--tb-compare", type=Path, required=True)
    rt.add_argument("--seed", type=int, default=0)

    en_p = subparsers.add_parser("energy", help="energy payload toggle counts (round 5)")
    en_p.add_argument("--out", type=Path, required=True)
    en_p.add_argument("bases", type=Path, nargs="+")

    ip = subparsers.add_parser("insertion", help="edit-API insertion counts of family builds")
    ip.add_argument("roots", type=Path, nargs="+")
    r6 = subparsers.add_parser("r6-report", help="round 6: counts and rareness per base set")
    r6.add_argument("root", type=Path)
    r6.add_argument("--new", nargs="+", required=True)
    r6.add_argument("--log", type=Path)
    r6.add_argument("--not-released", nargs="*", default=[])
    pd = subparsers.add_parser("prov-demo", help="provenance of inserted objects on one base")
    pd.add_argument("base", type=Path)
    pd.add_argument("--out", type=Path, required=True)

    ocb = subparsers.add_parser("oc-bases", help="OpenCores bases to BLIF (Seq rc8 admission)")
    ocb.add_argument("--external", type=Path, required=True, help="dir holding opencores/ etc.")
    ocb.add_argument("--odin3-bin", type=Path, required=True)
    ocb.add_argument("--out", type=Path, required=True)
    sq = subparsers.add_parser("seq-rc8", help="Seeker-Seq rc8: OpenCores build and merge")
    sq.add_argument("step", choices=["build", "merge"])
    sq.add_argument("--bases", type=Path, nargs="*", default=[])
    sq.add_argument("--out", type=Path, required=True)
    sq.add_argument("--seed", type=int, default=None)
    sq.add_argument("--workers", type=int, default=1)
    sq.add_argument("--first-index", type=int, default=36)
    sq.add_argument("--rc7", type=Path, help="unpacked rc7 release (circuits/, answer_key/)")
    sq.add_argument("--rc7-manifest", type=Path, help="rc7 release manifest.json.gz")
    sq.add_argument("--new", type=Path, help="the OpenCores build tree")
    n2 = subparsers.add_parser("n200", help="build a family at n = 200 per base (round 8)")
    n2.add_argument("name", choices=["Seeker-Comb", "Seeker-Seq"])
    n2.add_argument("--bases", type=Path, nargs="+", required=True)
    n2.add_argument("--out", type=Path, required=True)
    n2.add_argument("--seed", type=int, default=None,
                    help="generator seed (default: LEMANRUSS_RELEASE_SEED or LEMANRUSS_SEED_FILE)")
    n2.add_argument("--workers", type=int, default=1)
    n2.add_argument("--max-gates", type=int, default=10**9)
    n2t = subparsers.add_parser("n200-report", help="markdown tables of an n200 tree or release")
    n2t.add_argument("root", type=Path)

    sc = subparsers.add_parser("score", help="score one detector submission (aggregate report)")
    sc.add_argument("submission", type=Path)
    sc.add_argument("--key", type=Path, required=True, help="answer key directory (private)")
    sc.add_argument("--subsets", type=Path, help="subsets.json (default: KEY/subsets.json)")
    sc.add_argument("--ledger", type=Path, help="rate-limit ledger (default: KEY/ledger.jsonl)")
    sc.add_argument("--submitter", help="authenticated identity for the rate limit")
    sc.add_argument("--hidden-sample", type=int, help="circuits scored (default 70 percent)")
    sc.add_argument("--seed", type=int, help="sample seed (tests and audit; default random)")
    sc.add_argument("--out-dir", type=Path, help="write report.md and report.json here")

    kp = subparsers.add_parser("key-pack", help="pack the trimmed key of a public release")
    kp.add_argument("key", type=Path, help="answer_key directory (private)")
    kp.add_argument("public", type=Path, help="public family dir: <benchmark>/sets.txt")
    kp.add_argument("--release", required=True, help="e.g. seeker-comb-v2.0")
    kp.add_argument("--family", required=True, choices=["comb", "seq", "proc"])
    kp.add_argument("--out", type=Path, required=True, help="output .tar.gz (keep private)")

    ku = subparsers.add_parser("key-unpack", help="unpack a key archive; prints the key dir")
    ku.add_argument("archive", type=Path)
    ku.add_argument("--out", type=Path, required=True)

    sb = subparsers.add_parser("subsets", help="draw the named subsets of a release (ids only)")
    sb.add_argument("--key", type=Path, required=True)
    sb.add_argument("--release", required=True)
    sb.add_argument("--seed", type=int, default=0)
    sb.add_argument("--out", type=Path, required=True)

    rg = subparsers.add_parser("regions", help="build KEY/regions.json (Trojan regions)")
    rg.add_argument("release", type=Path)
    rg.add_argument("--key", type=Path, required=True)
    rg.add_argument("--workers", type=int, default=2)
    rg.add_argument("--out", type=Path, help="output file (default: KEY/regions.json)")

    an = subparsers.add_parser("anonymise", help="anonymise base names of a release (b001...)")
    an.add_argument("release", type=Path)
    an.add_argument("--key", type=Path, required=True)
    an.add_argument("--out", type=Path, required=True)
    an.add_argument("--seed", type=int, default=0)

    subparsers.add_parser("extract-csv", help="issue body on stdin to submission CSV on stdout")

    args = parser.parse_args(argv)
    if args.command == "extract-csv":
        import sys

        from lemanruss.score.extract import extract_csv

        sys.stdout.write(extract_csv(sys.stdin.read()))
        return 0
    if args.command == "score":
        return _score_cmd(args)
    if args.command == "key-pack":
        from lemanruss.score import keypack

        for fname, size in keypack.pack(args.key, args.public, args.release, args.family,
                                        args.out).items():
            print(f"{fname}: {size} bytes")
        return 0
    if args.command == "key-unpack":
        from lemanruss.score import keypack

        print(keypack.unpack(args.archive, args.out))
        return 0
    if args.command == "subsets":
        from lemanruss.score.subsets import make

        drawn = make(args.key, args.release, args.seed, args.out)
        for name, v in drawn["subsets"].items():
            print(f"{name}: {v['n']}")
        return 0
    if args.command == "regions":
        import json

        from lemanruss.score.regions import build

        reg = build(args.release, args.key, args.workers)
        (args.out or args.key / "regions.json").write_text(
            json.dumps(reg) + "\n", encoding="utf-8")
        print(f"{len(reg)} infected circuits")
        return 0
    if args.command == "anonymise":
        from lemanruss.score.anonymise import anonymise

        print(anonymise(args.release, args.key, args.out, args.seed))
        return 0
    if args.command == "oc-bases":
        from lemanruss.htl import ocbases

        conv = [ocbases.convert_design(args.external, d, args.odin3_bin, args.out)
                for d in ocbases.admitted()]
        ocbases.write_record(args.out / "admission.json", conv)
        for cr in conv:
            print(f"{cr.name}: {'ok' if cr.ok else 'FAILED ' + cr.why} gates {cr.gates} "
                  f"latches {cr.latches}")
        return 0 if all(cr.ok for cr in conv) else 1
    if args.command == "seq-rc8":
        if args.step == "build":
            from lemanruss.htl.n200rc7 import run_family_rc7
            from lemanruss.seedsrc import release_seed

            res7 = run_family_rc7(args.bases, args.out, release_seed(args.seed, "Seeker-Seq-rc8"),
                                  args.workers, first_index=args.first_index)
            print(f"{len(res7)} bases built")
            return 0
        from lemanruss.htl.seqoc import merge_roots

        assert args.rc7 and args.rc7_manifest and args.new
        print(merge_roots(args.rc7, args.rc7_manifest, args.new, args.out))
        return 0
    if args.command == "n200":
        from lemanruss.htl.n200run import run_family as n200_run
        from lemanruss.seedsrc import release_seed

        res = n200_run(args.name, args.bases, args.out, release_seed(args.seed, args.name),
                       args.workers, args.max_gates)
        print(f"{len(res)} bases built")
        return 0
    if args.command == "n200-report":
        from lemanruss.htl.n200run import cut_table, tables

        print("\n".join(tables(args.root)))
        if (args.root / "answer_key" / "cuts.json").exists():
            print("\n".join(cut_table(args.root)))
        return 0
    if args.command == "insertion":
        from lemanruss.htl.r5report import insertion_summary

        for root in args.roots:
            print(f"{root.name}:")
            print("\n".join(insertion_summary(root)))
        return 0
    if args.command == "r6-report":
        from lemanruss.htl.r6report import report as r6_lines

        print("\n".join(r6_lines(args.root, args.new, args.log, args.not_released)))
        return 0
    if args.command == "prov-demo":
        from lemanruss.htl.r5report import provenance_demo

        print("\n".join(provenance_demo(args.base, args.out)))
        return 0
    if args.command == "energy":
        import json
        from dataclasses import asdict

        from lemanruss.htl.energy import run_one

        args.out.mkdir(parents=True, exist_ok=True)
        en_rows = [run_one(b, args.out, f"en{i:03d}", 0)
                   for i, b in enumerate(sorted(args.bases), 1)]
        (args.out / "energy.json").write_text(
            json.dumps([asdict(e) for e in en_rows], indent=1) + "\n", encoding="utf-8")
        for e in en_rows:
            print(f"{e.circuit} {e.base}: {e.signals_equal}/{e.signals_compared} signals equal; "
                  f"delta/cycle odin {e.odin_delta_per_cycle:.2f} python "
                  f"{e.python_delta_per_cycle:.2f} expected {e.expected_delta_per_cycle:.2f} "
                  f"{e.error}")
        return 0
    if args.command == "rtl-tb":
        import json
        from dataclasses import asdict

        from lemanruss.htl.bases import combinational_sources
        from lemanruss.htl.rtl_tb import run_all, summary_lines

        srcs = combinational_sources(args.mimir_root)
        rtl = run_all(srcs, args.out, args.odin3_bin, args.tb_compare, args.seed)
        (args.out / "rtl_tb.json").write_text(
            json.dumps([asdict(r) for r in rtl], indent=1) + "\n", encoding="utf-8")
        print("\n".join(summary_lines(rtl)))
        return 0
    if args.command == "bases":
        from lemanruss.htl.bases import collect

        found = collect(args.mimir_root, args.suite, args.out)
        kept = [r for r in found if r.kept]
        print(f"{args.suite}: {len(found)} designs, {len(kept)} kept")
        for r in found:
            if not r.kept:
                print(f"  skip {r.ref}: {r.reason}")
        return 0
    if args.command == "hdl2blif":
        import time

        from lemanruss.htl.bases import convert

        args.out.mkdir(parents=True, exist_ok=True)
        for src in args.sources:
            t0 = time.monotonic()
            why = convert(src, args.out / f"{src.stem}.blif", src.stem if args.top_stem else None,
                          args.arch, args.timeout,
                          args.mem_gb * 1024**3, args.flatten)
            print(f"{src.stem}: {'FAILED ' + why if why else 'ok'} "
                  f"({time.monotonic() - t0:.0f} s)")
        return 0
    if args.command == "restructure":
        from lemanruss.htl.r4run import restructure_family, restructure_tables

        res = restructure_family(args.root, args.short, args.workers)
        report = "\n".join(restructure_tables(res)) + "\n"
        (args.root / "answer_key" / "restructured.md").write_text(report, encoding="utf-8")
        print(report)
        return 0
    if args.command == "family-verify":
        from lemanruss.htl.r4run import summarise, verify_family

        report = "\n".join(summarise(verify_family(args.root, args.workers))) + "\n"
        (args.root / "answer_key" / "verification.md").write_text(report, encoding="utf-8")
        print(report)
        return 0
    if args.command == "verify":
        import json

        from lemanruss.htl.relverify import verify_release

        if args.release.name.startswith("seeker-proc-"):
            from lemanruss.htl.proc_rc1_release import verify_proc_rc1

            rep = verify_proc_rc1(args.release)
        elif (args.release / "answer_key" / "sets.json").exists():
            from lemanruss.htl.n200verify import verify_n200

            rep = verify_n200(args.release, args.scratch, args.workers)
        else:
            rep = verify_release(args.release, args.scratch, args.workers)
        args.json_out.write_text(json.dumps(rep, indent=1) + "\n", encoding="utf-8")
        print(f"{args.release.name}: {'PASS' if rep['ok'] else 'FAIL'}")
        return 0 if rep["ok"] else 1
    if args.command == "release":
        from lemanruss.htl.release import Tools, build_release

        short = "sc" if args.family == "Seeker-Comb" else "ss"
        tools = Tools(args.odin3_build_pin, args.odin3_checkout, args.abc)
        if args.n200:
            from lemanruss.htl.n200release import build_release_n200

            info = build_release_n200(args.root, args.out, args.family, short, tools,
                                      args.licences, args.version)
        else:
            info = build_release(
                args.root, args.out, args.family, short, 0, tools, args.licences,
                args.version, dict(x.split("=", 1) for x in args.exclude_base), False)
        print(info)
        return 0
    if args.command == "release-report":
        from lemanruss.htl.relreport import render_reports

        args.out.write_text(render_reports(args.reports, args.title), encoding="utf-8")
        return 0
    if args.command == "family":
        from lemanruss.htl.rareness import (
            pooled_comb,
            pooled_seq,
            seq_table_rows,
            table_rows,
        )
        from lemanruss.htl.seeker import run_family
        from lemanruss.seedsrc import release_seed

        built, fails = run_family(
            args.name, sorted(args.bases), args.out, release_seed(args.seed, args.name),
            args.max_blocks, args.workers)
        recs = [b.record for b in built]
        comb = args.name == "Seeker-Comb"
        lines = (table_rows(recs) if comb else seq_table_rows(recs))
        lines += [""] + (pooled_comb(recs) if comb else pooled_seq(recs))
        lines += ["", "Failures / band unreachable:"]
        lines += [f"- {f.base} [{f.variant}]: {f.reason}" for f in fails]
        report = "\n".join(lines) + "\n"
        (args.out / "answer_key" / "rareness.md").write_text(report, encoding="utf-8")
        print(report)
        return 0
    if args.command == "build":
        from lemanruss.htl.build import build_benchmark

        base_designs = sorted(args.base_dir.glob("*.v")) + sorted(args.base_dir.glob("*.sv"))
        if not base_designs:
            print(f"lemanruss build: no .v files found under {args.base_dir}")
            return 1
        entries, failures = build_benchmark(base_designs, args.out)
        print(f"{len(entries)} Trojan(s) built, {len(failures)} failure(s)")
        for failure in failures:
            print(f"  FAILED {failure.base_design}: {failure.reason}")
        for entry in entries:
            v = entry.verification
            print(
                f"  {entry.base_design}: {entry.trojan.id} fires={v['fires']} "
                f"equivalent={v['equivalent_clean_part']} "
                f"activation_p={v['activation_probability']:.4g}"
            )
        return 0
    return 1


def _score_cmd(args: argparse.Namespace) -> int:
    import json

    from lemanruss.score import ledger
    from lemanruss.score.key import load
    from lemanruss.score.scorer import render, score
    from lemanruss.score.submission import SubmissionError
    from lemanruss.score.subsets import load_subsets

    release, subs = load_subsets(args.subsets or args.key / "subsets.json")
    try:
        rep = score(args.submission.read_text(encoding="utf-8"), load(args.key), release, subs,
                    ledger_path=args.ledger or args.key / "ledger.jsonl",
                    submitter=args.submitter, hidden_sample=args.hidden_sample, seed=args.seed)
    except (SubmissionError, ledger.RateLimitError) as exc:
        print(f"REFUSED: {exc}")
        return 2
    except OSError as exc:
        print(f"FAILED: file error, ledger not updated ({type(exc).__name__}); not scored")
        return 3
    text = render(rep)
    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        (args.out_dir / "report.md").write_text(text, encoding="utf-8")
        (args.out_dir / "report.json").write_text(
            json.dumps(rep, indent=1) + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
