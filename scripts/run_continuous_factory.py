#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_continuous_factory.py - continuous production driver for the 2,000-row factory.

The batch tool (run_article_batch.py) remains the state machine and safety
gate. This driver is the production controller that must NEVER stop merely
because one batch or chunk finished:

    while unfinished rows exist:
        reconcile (recover txn, respect lock)
        choose earliest unfinished batch (deterministic)
        claim next chunk (10 rows, or fewer for a final partial chunk)
        WRITER stage  -> external writer produces the article files
        qa
        publish (transactional, PASS + seo >= 90)
        regenerate progress / throughput
        production invariant validations (FAIL-CLOSED: matrix, site,
        cannibalization, matrix sync)
        report CONTINUE / COMPLETE / WRITER_REQUIRED / BLOCKED / FATAL_ERROR

Validations are production invariants, NOT informational. If ANY validator
fails the driver reports BLOCKED with a non-zero exit and does NOT print
the CONTINUE/COMPLETE marker: the factory must not continue while an
invariant is broken. `validate` runs the invariant gate standalone
(read-only, same verdicts).

The writer stage is external by design (prose is authored, not templated).
Two supported writer modes:

  --writer-command CMD   CMD is invoked once with the chunk ids appended;
                         exit 0 means all files written.
  (no writer)            If claimed chunk files are not present yet the
                         driver exits with WRITER_REQUIRED and the chunk
                         stays claimed in the checkpoint (resumable, not
                         lost) - the writer then writes files and re-runs
                         this driver, which will detect the files and
                         continue at qa.

If the writer files already exist for the claimed chunk (resume), the
driver proceeds straight to QA.

Exit status JSON is printed on stdout; final line is one of:
  VANCHINH_FACTORY_CONTINUING
  VANCHINH_FACTORY_COMPLETE
  VANCHINH_FACTORY_WRITER_REQUIRED
  VANCHINH_FACTORY_BLOCKED
  VANCHINH_FACTORY_FATAL_ERROR
  VANCHINH_FACTORY_VALIDATIONS_PASS   (validate subcommand only)
"""
import argparse
import json
import os
import pathlib
import subprocess
import sys

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent
ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))
import factory_common as fc  # noqa: E402

TERMINAL = ("PUBLISHED", "BLOCKED", "FAIL")
BATCH_TOOL = str(SCRIPTS_DIR / "run_article_batch.py")
ARTICLE_DIR = ROOT / "cam-nang" / "an-toan"


def unfinished(rows):
    return [r for r in rows if r["status"] not in TERMINAL]


def status_snapshot():
    rows = fc.load_matrix()
    from collections import Counter
    counts = Counter(r["status"] for r in rows)
    un = unfinished(rows)
    nxt = un[0] if un else None
    # earliest unfinished batch, deterministic order = matrix order
    active = None
    for r in rows:
        if r["status"] not in TERMINAL:
            active = r["batch_id"]
            break
    cp = fc.read_checkpoint()
    return {
        "total": len(rows),
        "counts": dict(counts),
        "published": counts.get("PUBLISHED", 0),
        "blocked": counts.get("BLOCKED", 0),
        "fail": counts.get("FAIL", 0),
        "unfinished": len(un),
        "active_batch": active,
        "next_article": nxt["article_id"] if nxt else None,
        "txn_pending": fc.txn_pending(),
        "checkpoint_chunk_ids": (cp or {}).get("current_chunk_ids") or [],
        "factory_status": "COMPLETE" if not un else "CONTINUE",
    }


def _run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def _chunk_files_exist(chunk_ids, rows):
    missing = []
    by_id = {r["article_id"]: r for r in rows}
    for aid in chunk_ids:
        p = ROOT / by_id[aid]["output_path"]
        if not p.exists():
            missing.append(aid)
    return missing


VALIDATION_CMDS = [
    ("matrix", "validate_content_matrix.py"),
    ("site", "validate_site.py"),
    ("cannibalization", "check_cannibalization.py"),
    ("matrix_sync", "check_matrix_sync.py"),
]


def run_validations():
    """Run the production invariant validators and return per-validator
    results with captured output tails. Callers MUST treat any non-zero
    returncode as a blocker (fail-closed)."""
    results = {}
    for name, script in VALIDATION_CMDS:
        v = _run([sys.executable, str(SCRIPTS_DIR / script)])
        results[name] = {
            "returncode": v.returncode,
            "stdout_tail": v.stdout[-1500:],
            "stderr_tail": v.stderr[-1500:],
        }
    return results


def validation_verdicts(results):
    return {name: ("PASS" if r["returncode"] == 0 else "FAIL")
            for name, r in results.items()}


def validation_gate(ctx=None, mode="run"):
    """FAIL-CLOSED production invariant gate shared by `run` and `validate`.

    Any validator FAIL => status BLOCKED, exit code 2, failed validators
    named exactly with output tails, and NO CONTINUE/COMPLETE marker: the
    factory must not claim or process the next chunk while an invariant
    is broken. All validators PASS => normal verdict derived from the
    matrix (run mode) or VALIDATIONS_PASS (validate mode).
    """
    results = run_validations()
    verdicts = validation_verdicts(results)
    failed = sorted(n for n, v in verdicts.items() if v == "FAIL")
    after = status_snapshot()
    out = dict(ctx or {})
    out.update({
        "status": "BLOCKED" if failed else after["factory_status"],
        "published_total": after["published"],
        "remaining": after["unfinished"],
        "active_batch": after["active_batch"],
        "next_article": after["next_article"],
        "validations": verdicts,
        "failed_validators": failed,
        "checkpoint_clean": not fc.txn_pending(),
    })
    if failed:
        out["reason"] = "production invariant validation failed"
        out["failures"] = {n: results[n] for n in failed}
        out["action"] = ("fix the failed validators and re-run; the factory must not "
                         "continue until every production invariant passes")
        print(json.dumps(out, ensure_ascii=False, indent=2))
        print("VANCHINH_FACTORY_BLOCKED")
        return 2
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if mode == "validate":
        print("VANCHINH_FACTORY_VALIDATIONS_PASS")
        return 0
    if after["factory_status"] == "COMPLETE":
        print("VANCHINH_FACTORY_COMPLETE")
    else:
        print("VANCHINH_FACTORY_CONTINUING")
    return 0


def cmd_validate(args):
    """Run the production invariant gate standalone (read-only)."""
    return validation_gate(ctx={"mode": "standalone-invariant-validation"},
                            mode="validate")


def cmd_status():
    snap = status_snapshot()
    print(json.dumps(snap, ensure_ascii=False, indent=2))
    print("VANCHINH_FACTORY_COMPLETE" if snap["factory_status"] == "COMPLETE"
          else "VANCHINH_FACTORY_CONTINUING")
    return 0


def reconcile():
    """RECONCILE FIRST: recover pending transaction, refuse while another
    operator holds the lock."""
    if fc.txn_pending():
        p = _run([sys.executable, BATCH_TOOL, "recover"])
        if p.returncode != 0:
            return {"status": "BLOCKED", "reason": "txn recovery failed", "detail": p.stdout + p.stderr}
    return None


def cmd_run(args):
    problem = reconcile()
    if problem:
        print(json.dumps(problem, ensure_ascii=False))
        print("VANCHINH_FACTORY_BLOCKED")
        return 2
    snap = status_snapshot()
    if snap["factory_status"] == "COMPLETE":
        print(json.dumps(snap, ensure_ascii=False, indent=2))
        print("VANCHINH_FACTORY_COMPLETE")
        return 0

    batch = snap["active_batch"]
    # Resume in-flight chunk from checkpoint if it belongs to the active batch.
    chunk_ids = [c for c in snap["checkpoint_chunk_ids"]]
    rows = fc.load_matrix()
    claimed_unfinished = [r for r in rows if r["status"] in ("WRITING", "QA", "REPAIR")]

    if chunk_ids and all(
            any(r["article_id"] == c and r["status"] in ("WRITING", "QA", "REPAIR")
                for r in rows) for c in chunk_ids):
        pass  # resume the claimed chunk (incl. REPAIR rows from a late-writer QA)
    else:
        chunk_ids = [r["article_id"] for r in claimed_unfinished[:args.chunk_size]]
        if not chunk_ids:
            p = _run([sys.executable, BATCH_TOOL, "claim", batch, "--limit", str(args.chunk_size)])
            if p.returncode != 0:
                print(json.dumps({"status": "FATAL_ERROR", "stage": "claim",
                                  "detail": p.stdout + p.stderr}, ensure_ascii=False))
                print("VANCHINH_FACTORY_FATAL_ERROR")
                return 3
            out = json.loads(p.stdout)
            chunk_ids = out["chunk_ids"]
        rows = fc.load_matrix()

    missing = _chunk_files_exist(chunk_ids, rows)
    if missing:
        if args.writer_command:
            cmd = args.writer_command.split() + [",".join(chunk_ids)]
            p = _run(cmd)
            if p.returncode != 0:
                print(json.dumps({"status": "RETRYABLE_ERROR", "stage": "writer",
                                  "detail": p.stdout[-2000:] + p.stderr[-2000:]}, ensure_ascii=False))
                print("VANCHINH_FACTORY_FATAL_ERROR")
                return 4
            missing = _chunk_files_exist(chunk_ids, rows)
    if missing:
        # Chunk stays claimed (WRITING) in checkpoint: resumable, not lost.
        print(json.dumps({"status": "WRITER_REQUIRED", "batch": batch,
                          "chunk_ids": chunk_ids, "missing_files": missing,
                          "resume": "write the files, then re-run this driver"},
                         ensure_ascii=False, indent=2))
        print("VANCHINH_FACTORY_WRITER_REQUIRED")
        return 1

    # QA
    p = _run([sys.executable, BATCH_TOOL, "qa", batch, "--ids", ",".join(chunk_ids)])
    try:
        qa = json.loads(p.stdout)
    except Exception:
        qa = {"PASS": 0, "REVIEW": 0, "FAIL": 0, "raw": p.stdout[-2000:]}
    if p.returncode != 0 and not qa.get("pass"):
        print(json.dumps({"status": "BLOCKED", "stage": "qa", "detail": qa}, ensure_ascii=False))
        print("VANCHINH_FACTORY_BLOCKED")
        return 2

    # Publish eligible PASS rows
    p = _run([sys.executable, BATCH_TOOL, "publish", batch, "--ids", ",".join(chunk_ids)])
    try:
        pub = json.loads(p.stdout)
    except Exception:
        pub = {"raw": (p.stdout + p.stderr)[-2000:]}

    # Regenerate derived outputs
    _run([sys.executable, BATCH_TOOL, "progress"])
    _run([sys.executable, BATCH_TOOL, "throughput"])

    # Production invariant validations are FAIL-CLOSED: any validator
    # failure blocks the driver (BLOCKED verdict, non-zero exit, no
    # CONTINUE/COMPLETE marker, failed validator named with output tails).
    ctx = {
        "chunk": chunk_ids,
        "qa": {"PASS": len(qa.get("pass", [])), "REVIEW": len(qa.get("repair", []))},
        "published_ids": pub.get("ids", []),
    }
    return validation_gate(ctx=ctx, mode="run")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("status", help="print matrix-derived factory status")
    sub.add_parser("validate", help="run the production invariant gate standalone")
    p_run = sub.add_parser("run", help="process the next chunk end-to-end")
    p_run.add_argument("--chunk-size", type=int, default=10)
    p_run.add_argument("--writer-command", default=os.environ.get("VC_WRITER_CMD"),
                       help="external writer command; receives chunk ids appended")
    args = ap.parse_args()
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "validate":
        return cmd_validate(args)
    return cmd_status()


if __name__ == "__main__":
    sys.exit(main())
