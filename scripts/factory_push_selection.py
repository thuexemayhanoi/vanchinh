#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""factory_push_selection.py - deterministic push-scope selection for the
automated factory-publish workflow (WRITE-AHEAD QUEUE contract).

The workflow derives the article scope from the files the writer actually
added/modified in the push - never a blind limit-based claim that grabs
PLANNED rows whose files do not exist yet.

TURBO QUEUE CONTRACT (supersedes the old "exact 2 per push" contract):
  - one writer push may queue 2..MAX_PER_PUSH (10) consecutive article files;
  - the queue is validated against repository/matrix truth (no duplicates,
    no PUBLISHED rows, no rows outside the active batch, matrix order);
  - the queue is split into deterministic PAIRS of 2 which the factory
    processes sequentially inside the SAME production run
    (pair -> scoped QA -> transactional publish (PASS only) -> checkpoint ->
    next pair); a failed pair NEVER rolls back already-published pairs and
    stays recoverable (REVIEW/REPAIR/BLOCKED states) for a repair push.

Inputs (newline-separated path lists, one path per line):
  --added <file>     paths ADDED in this push    (git diff --diff-filter=A)
  --modified <file>  paths MODIFIED in this push (git diff --diff-filter=M)

Output: JSON on stdout describing the exact, verifiable scope:
  {
    "proceed": bool,          # false => workflow skips everything
    "mode": "new"|"repair"|"backlog"|"skip",
    "batch": "B35"|null,     # active (first non-terminal) batch
    "claim_ids": [...],      # PLANNED->WRITING claim targets (never >10)
    "qa_ids": [...],         # explicit QA targets (the full queue, matrix order)
    "queue": [...],          # same as qa_ids (matrix order)
    "pairs": [[a,b],[c,d]]   # deterministic 2-article pairs, matrix order
    "pair_count": int,
    "refuse": null|"reason"  # non-null => the push violates the contract
  }

Selection rules (deterministic, matrix truth):
  NEW mode:     PLANNED rows of the active batch whose output_path is in the
                ADDED list AND the file exists. More than MAX_PER_PUSH => REFUSE
                (the writer must push at most 10 new article files per commit).
                A PLANNED row whose file is NOT in the added list (or whose
                file is missing) is NEVER claimed.
  REPAIR mode:  rows of the active batch in WRITING/QA/REVIEW/REPAIR/PASS
                whose output_path is in the ADDED or MODIFIED list AND the
                file exists. These are QA'd/published pair by pair; a repair
                push NEVER claims fresh PLANNED rows. Also capped at
                MAX_PER_PUSH.
  BACKLOG mode: no added/modified article files, but PLANNED rows of the
                active batch already have files in the repo (e.g. a previous
                pipeline failure). Deterministic first-MAX_PER_PUSH in matrix
                order, queued as pairs.
  SKIP:         nothing to do (e.g. tooling-only push, or a shell-rebuild-only
                push touching only PUBLISHED article files).
  REFUSE:       >MAX_PER_PUSH queued article files in one push; or the push
                touches article rows that contradict matrix truth (rows of a
                non-active batch, terminal FAIL/BLOCKED rows).

Exit codes: 0 ok, 3 refuse (contract violation; state unchanged).
"""
import argparse
import json
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import factory_common as fc

TERMINAL = ("PUBLISHED", "BLOCKED", "FAIL")
MAX_PER_PUSH = 10  # write-ahead queue: one writer push queues at most 10 articles
PAIR_SIZE = 2      # the factory consumes the queue as deterministic pairs of 2
REPAIRABLE = ("WRITING", "QA", "REVIEW", "REPAIR", "PASS")


def read_paths(path):
    p = pathlib.Path(path)
    if not p.exists():
        return []
    return [line.strip() for line in p.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def active_batch(rows):
    """First batch (matrix order) with any non-terminal row; None when the
    factory is complete."""
    order = []
    for r in rows:
        if r["batch_id"] not in order:
            order.append(r["batch_id"])
    for b in order:
        if any(r["status"] not in TERMINAL for r in rows if r["batch_id"] == b):
            return b
    return None


def _matrix_order(rows):
    """article_id -> position in matrix (repository/matrix order)."""
    return {r["article_id"]: i for i, r in enumerate(rows)}


def _queue_pairs(ids, order):
    """Split ordered ids into deterministic PAIR_SIZE chunks."""
    ordered = sorted(ids, key=lambda a: order.get(a, 10**9))
    return [ordered[i:i + PAIR_SIZE] for i in range(0, len(ordered), PAIR_SIZE)]


def select(added, modified):
    rows = fc.load_matrix()
    batch = active_batch(rows)
    out = {"proceed": False, "mode": "skip", "batch": batch,
           "claim_ids": [], "qa_ids": [], "queue": [], "pairs": [],
           "pair_count": 0, "refuse": None}
    if batch is None:
        return out
    br = [r for r in rows if r["batch_id"] == batch]
    by_path = {}
    for r in rows:  # duplicate output paths are a matrix violation; first wins
        by_path.setdefault(r["output_path"], r)
    touched = set(added) | set(modified)
    unmapped = sorted(p for p in touched if p not in by_path)
    if unmapped:
        out["unmapped_paths"] = unmapped  # audit only; never blocks

    # Push rows that contradict matrix truth: rows of a non-active batch or
    # terminal FAIL/BLOCKED rows of the active batch. PUBLISHED rows are the
    # article-shell rebuild surface and stay ignored by design.
    illegal = []
    for p in touched:
        r = by_path.get(p)
        if r is None or r["status"] == "PUBLISHED":
            continue
        if r["batch_id"] != batch or r["status"] in ("FAIL", "BLOCKED"):
            illegal.append(f"{p} -> {r['article_id']} ({r['batch_id']}/{r['status']})")
    if illegal:
        out["refuse"] = ("push touches article rows that contradict matrix "
                         f"truth (active batch {batch}): {'; '.join(sorted(illegal)[:5])}")
        return out

    def has_file(row):
        return (fc.ROOT / row["output_path"]).is_file()

    # NEW: PLANNED rows of the active batch whose file was ADDED and exists.
    new_ids = [r["article_id"] for r in br
               if r["status"] == "PLANNED" and r["output_path"] in set(added)
               and has_file(r)]
    # REPAIR: non-terminal pre-publish rows touched (added or modified).
    repair_ids = [r["article_id"] for r in br
                  if r["status"] in REPAIRABLE and r["output_path"] in touched
                  and has_file(r)]
    if len(set(new_ids)) > MAX_PER_PUSH:
        out["refuse"] = (f"push queues {len(set(new_ids))} new article files; "
                         f"max {MAX_PER_PUSH} per commit - split the push "
                         f"deterministically (write-ahead queue contract)")
        return out
    if len(set(repair_ids)) > MAX_PER_PUSH:
        out["refuse"] = (f"push queues {len(set(repair_ids))} repaired article "
                         f"files; max {MAX_PER_PUSH} per commit - split the push")
        return out
    if new_ids:
        out["mode"] = "new"
        out["claim_ids"] = new_ids
        out["qa_ids"] = sorted(set(new_ids) | set(repair_ids))
        out["proceed"] = True
    elif repair_ids:
        # repair/resume push: process EXACTLY these IDs; never claim PLANNED.
        out["mode"] = "repair"
        out["qa_ids"] = repair_ids
        out["proceed"] = True
    else:
        # BACKLOG: PLANNED rows whose files already exist (no files in this push).
        backlog = [r["article_id"] for r in br
                   if r["status"] == "PLANNED" and has_file(r)][:MAX_PER_PUSH]
        if backlog:
            out["mode"] = "backlog"
            out["claim_ids"] = backlog
            out["qa_ids"] = backlog
            out["proceed"] = True
    # Deterministic queue + pairs in repository/matrix order.
    order = _matrix_order(rows)
    out["queue"] = sorted(out["qa_ids"], key=lambda a: order.get(a, 10**9))
    out["pairs"] = _queue_pairs(out["queue"], order)
    out["pair_count"] = len(out["pairs"])
    return out


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--added", default=None, help="file with newline-separated added paths")
    ap.add_argument("--modified", default=None, help="file with newline-separated modified paths")
    args = ap.parse_args()
    added = read_paths(args.added) if args.added else []
    modified = read_paths(args.modified) if args.modified else []
    out = select(added, modified)
    print(json.dumps(out, ensure_ascii=False))
    return 3 if out["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
