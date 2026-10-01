#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""factory_queue.py - WRITE-AHEAD QUEUE processor for the factory-publish
workflow (TURBO QUEUE contract).

Input contract (produced by scripts/factory_push_selection.py from the push):
  one writer push queues 2..10 article IDs; this processor consumes the queue
  as deterministic PAIRS of 2, sequentially, inside ONE production run:

      pair -> claim (new mode only, exact pair IDs) -> scoped QA
           -> transactional publish (PASS only, quality PASS AND seo >= 80)
           -> checkpoint
           -> next pair

Safety contract:
  - ONE run-lock for the whole queue run (publisher concurrency = 1);
  - each pair's publish is its OWN transaction; a failed pair NEVER rolls
    back already-published pairs;
  - a failed/review pair stays RECOVERABLE (REVIEW/REPAIR/BLOCKED states in
    the matrix, checkpoint pending lists) and is reported explicitly for a
    follow-up repair push;
  - repository truth is revalidated BEFORE any mutation: IDs must exist in
    the matrix, belong to the requested batch, never be PUBLISHED, and carry
    no duplicates;
  - full-site gates are NOT part of this hot loop (Simple Production Mode);
    the workflow runs the light matrix smoke after the queue.

Run report: reports/batches/factory-queue-last-run.json is rewritten after
every pair (crash-resilient) and lists per-pair outcomes, the published
total and the recoverable IDs.

Usage:
  python3 scripts/factory_queue.py run --batch B35 --mode new  --ids A,B,C,...
  python3 scripts/factory_queue.py run --batch B35 --mode repair --ids A,B,...

Exit codes:
  0 = queue fully processed (published or recoverable states committed;
      partial QA failures are recoverable and do not fail the run)
  1 = fatal, nothing mutated (pending txn, lock held, invalid queue)
"""
import argparse
import json
import os
import sys
import time
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import factory_common as fc
import run_article_batch as rab

# env-overridable so sandbox tests NEVER write the production report
REPORT = pathlib.Path(os.environ.get("FACTORY_QUEUE_REPORT",
                                     str(fc.ROOT / "reports" / "batches" / "factory-queue-last-run.json")))
PAIR_SIZE = 2


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _validate_queue(batch_id, ids, mode):
    """Revalidate the queue against fresh repository truth BEFORE mutating.

    Returns (queue, error). queue = ids in matrix order, deduplicated; any
    violation is fatal and mutates nothing.
    """
    rows = fc.load_matrix()
    order = {r["article_id"]: i for i, r in enumerate(rows)}
    seen, queue = set(), []
    for a in ids:
        if a in seen:
            return None, f"duplicate id in queue: {a}"
        seen.add(a)
        queue.append(a)
    by_id = {r["article_id"]: r for r in rows}
    for a in queue:
        r = by_id.get(a)
        if r is None:
            return None, f"{a}: not found in matrix"
        if r["batch_id"] != batch_id:
            return None, f"{a}: belongs to batch {r['batch_id']}, not {batch_id}"
        if r["status"] == "PUBLISHED":
            return None, f"{a}: row is already PUBLISHED (never re-claim/overwrite)"
        if r["status"] in ("FAIL", "BLOCKED"):
            return None, f"{a}: terminal status {r['status']}"
        if mode == "new" and r["status"] not in ("PLANNED", "WRITING",
                                                 "QA", "REVIEW", "REPAIR", "PASS"):
            return None, f"{a}: status {r['status']} not queueable in mode new"
        if not (fc.ROOT / r["output_path"]).is_file():
            return None, f"{a}: article file missing at {r['output_path']}"
    queue.sort(key=lambda a: order[a])
    return queue, None


def _write_report(state):
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(state, ensure_ascii=False, indent=2),
                      encoding="utf-8")


def run_queue(batch_id, mode, ids, pair_size=PAIR_SIZE):
    started = _now()
    queue, err = _validate_queue(batch_id, ids, mode)
    if err is not None:
        print(json.dumps({"error": f"refusing queue: {err}", "batch": batch_id,
                          "mode": mode}, ensure_ascii=False))
        return 1
    if fc.txn_pending():
        print(json.dumps({"error": "pending transaction marker present; run recover first",
                          "batch": batch_id}, ensure_ascii=False))
        return 1
    pairs = [queue[i:i + pair_size] for i in range(0, len(queue), pair_size)]
    state = {"schema_version": "1", "batch": batch_id, "mode": mode,
             "queue": queue, "pair_size": pair_size, "started": started,
             "finished": None, "pairs": [], "published_total": 0,
             "recoverable_ids": [], "fatal": None}
    _write_report(state)
    try:
        fc.acquire_lock(operator=f"queue-{batch_id}")
    except fc.LockHeld as e:
        state["fatal"] = f"lock held: {e}"
        _write_report(state)
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        return 1
    try:
        for idx, pair in enumerate(pairs, 1):
            entry = {"pair_index": idx, "ids": pair, "claimed": [], "pass": [],
                      "published": [], "review": [], "repair": [],
                      "blocked": [], "publish_rc": 0, "status": "pending"}
            state["pairs"].append(entry)
            _write_report(state)
            try:
                if mode == "new":
                    rc = rab.cmd_claim(batch_id, ids=pair, lock_held=True)
                    if rc != 0:
                        entry["status"] = "claim_failed"
                        state["recoverable_ids"] += pair
                        _write_report(state)
                        continue
                    entry["claimed"] = pair
                rc = rab.cmd_qa(batch_id, ids=pair, lock_held=True)
                rows = fc.load_matrix()
                st = {r["article_id"]: r["status"] for r in rows
                      if r["article_id"] in pair}
                entry["pass"] = [a for a in pair if st.get(a) == "PASS"]
                entry["review"] = [a for a in pair if st.get(a) == "REVIEW"]
                entry["repair"] = [a for a in pair if st.get(a) == "REPAIR"]
                entry["blocked"] = [a for a in pair if st.get(a) == "BLOCKED"]
                if rc != 0:
                    entry["status"] = "qa_failed"
                    state["recoverable_ids"] += [a for a in pair
                                                 if a not in entry["pass"]]
                    _write_report(state)
                    continue
                if entry["pass"]:
                    prc = rab.cmd_publish(batch_id, ids=entry["pass"], lock_held=True)
                    entry["publish_rc"] = prc
                    rows = fc.load_matrix()
                    st2 = {r["article_id"]: r["status"] for r in rows
                           if r["article_id"] in pair}
                    entry["published"] = [a for a in pair if st2.get(a) == "PUBLISHED"]
                    state["published_total"] += len(entry["published"])
                recoverable = [a for a in pair if a not in entry["published"]]
                state["recoverable_ids"] += recoverable
                entry["status"] = ("published" if not recoverable
                                   else "partial" if entry["published"] else "recoverable")
                _write_report(state)
            except Exception as e:  # noqa: BLE001 - pair isolation contract
                entry["status"] = "error"
                entry["error"] = str(e)
                state["recoverable_ids"] += [a for a in pair
                                             if a not in entry["published"]]
                _write_report(state)
                continue
    finally:
        state["recoverable_ids"] = sorted(set(state["recoverable_ids"]))
        state["published_ids"] = sorted({a for e in state["pairs"] for a in e["published"]})
        state["finished"] = _now()
        _write_report(state)
        fc.release_lock()
    summary = {"batch": batch_id, "mode": mode, "queue": queue,
               "pairs": len(pairs), "published_total": state["published_total"],
               "published_ids": state["published_ids"],
               "recoverable_ids": state["recoverable_ids"],
               "report": str(REPORT)}
    print("VANCHINH_FACTORY_QUEUE_DONE " + json.dumps(summary, ensure_ascii=False))
    return 0


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("command", choices=["run"])
    ap.add_argument("--batch", required=True)
    ap.add_argument("--mode", choices=["new", "repair"], required=True)
    ap.add_argument("--ids", required=True,
                    help="comma-separated queue ids (matrix order revalidated)")
    ap.add_argument("--pair-size", type=int, default=PAIR_SIZE)
    args = ap.parse_args()
    ids = [v.strip() for v in args.ids.split(",") if v.strip()]
    if args.command == "run":
        return run_queue(args.batch, args.mode, ids, pair_size=args.pair_size)
    return 2


if __name__ == "__main__":
    sys.exit(main())
