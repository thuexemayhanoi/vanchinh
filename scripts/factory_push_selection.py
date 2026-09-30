#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""factory_push_selection.py - deterministic push-scope selection for the
automated factory-publish workflow.

The workflow MUST claim exactly the article IDs whose files the writer
actually added/modified in the push - never a blind limit-based claim that grabs
PLANNED rows whose files do not exist yet.

Inputs (newline-separated path lists, one path per line):
  --added <file>     paths ADDED in this push    (git diff --diff-filter=A)
  --modified <file>  paths MODIFIED in this push (git diff --diff-filter=M)

Output: JSON on stdout describing the exact, verifiable scope:
  {
    "proceed": bool,          # false => workflow skips everything
    "mode": "new"|"repair"|"backlog"|"skip",
    "batch": "B18"|null,     # active (first non-terminal) batch
    "claim_ids": [...],      # PLANNED->WRITING claim targets (never >50)
    "qa_ids": [...],         # explicit QA targets (claim_ids + repaired ids)
    "refuse": null|"reason"  # non-null => the push violates the contract
  }

Selection rules (deterministic, matrix truth):
  NEW mode:     PLANNED rows of the active batch whose output_path is in the
                ADDED list AND the file exists. More than 50 => REFUSE (the
                writer must push at most 50 new article files per commit).
                A PLANNED row whose file is NOT in the added list (or whose
                file is missing) is NEVER claimed.
  REPAIR mode:  rows of the active batch in WRITING/QA/REVIEW/REPAIR/PASS
                whose output_path is in the ADDED or MODIFIED list AND the
                file exists. These are QA'd/published EXPLICITLY; a repair
                push NEVER claims fresh PLANNED rows.
  BACKLOG mode: no added/modified article files, but PLANNED rows of the
                active batch already have files in the repo (e.g. a previous
                pipeline failure). Deterministic first-50 by article_id.
  SKIP:         nothing to do (e.g. tooling-only push).

Exit codes: 0 ok, 3 refuse (contract violation; state unchanged).
"""
import argparse
import json
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import factory_common as fc

TERMINAL = ("PUBLISHED", "BLOCKED", "FAIL")
MAX_CLAIM = 50  # Simple Production Mode: up to 50 new articles per push (= one batch)
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


def select(added, modified):
    rows = fc.load_matrix()
    batch = active_batch(rows)
    out = {"proceed": False, "mode": "skip", "batch": batch,
           "claim_ids": [], "qa_ids": [], "refuse": None}
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

    def has_file(row):
        return (fc.ROOT / row["output_path"]).is_file()

    # NEW: PLANNED rows of the active batch whose file was ADDED and exists.
    new_ids = sorted(r["article_id"] for r in br
                     if r["status"] == "PLANNED" and r["output_path"] in set(added)
                     and has_file(r))
    # REPAIR: non-terminal pre-publish rows touched (added or modified).
    repair_ids = sorted(r["article_id"] for r in br
                        if r["status"] in REPAIRABLE and r["output_path"] in touched
                        and has_file(r))
    if new_ids and len(new_ids) > MAX_CLAIM:
        out["refuse"] = (f"push adds {len(new_ids)} new article files; "
                         f"max {MAX_CLAIM} per commit - split the push deterministically")
        return out
    if new_ids:
        out["mode"] = "new"
        out["claim_ids"] = new_ids
        out["qa_ids"] = sorted(set(new_ids) | set(repair_ids))
        out["proceed"] = True
        return out
    if repair_ids:
        # repair/resume push: process EXACTLY these IDs; never claim PLANNED.
        out["mode"] = "repair"
        out["qa_ids"] = repair_ids
        out["proceed"] = True
        return out
    # BACKLOG: PLANNED rows whose files already exist (no files in this push).
    backlog = sorted((r["article_id"] for r in br
                      if r["status"] == "PLANNED" and has_file(r)),
                     )[:MAX_CLAIM]
    if backlog:
        out["mode"] = "backlog"
        out["claim_ids"] = backlog
        out["qa_ids"] = backlog
        out["proceed"] = True
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
