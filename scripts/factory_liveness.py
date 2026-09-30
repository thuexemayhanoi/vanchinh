#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""factory_liveness.py - READ-ONLY factory liveness watchdog.

Detects the failure mode "CI/workflow can be green while the factory stands
still". Reads repository truth ONLY:

  - matrix            (CONTENT_MATRIX)
  - writer-checkpoint (WRITER_CHECKPOINT)
  - factory-progress  (PROGRESS_FILE)
  - factory-throughput (FACTORY_THROUGHPUT)
  - txn marker        (TXN_FILE)
  - writer lock       (LOCK_FILE)

Verdicts (deterministic, evaluated in order):
  STALE_TXN                                   -> FAIL (rc 1)
  EXPIRED_OR_STALE_LOCK_WITH_UNFINISHED_WORK  -> FAIL (rc 1)
  CHECKPOINT_STALE                            -> FAIL (rc 1)
  STALLED_ACTIVE                              -> FAIL (rc 1)
  HEALTHY_ACTIVE                              -> PASS (rc 0)
  HEALTHY_IDLE                                -> PASS (rc 0)

Contract:
  - PLANNED rows alone are NEVER a stall: the external writer may rest
    legitimately between chunks; with no in-flight work that is HEALTHY_IDLE.
  - In-flight rows (WRITING/QA/REVIEW/REPAIR/PASS) with no checkpoint
    progress for longer than LIVENESS_STALL_HOURS (default 6h) are
    STALLED_ACTIVE.
  - A lock older than LIVENESS_LOCK_STALE_HOURS (default 6h) while
    unfinished (non-terminal) rows exist is
    EXPIRED_OR_STALE_LOCK_WITH_UNFINISHED_WORK.
  - A checkpoint whose current_chunk_ids disagree with matrix truth
    (unknown ids, or rows still PLANNED) is CHECKPOINT_STALE.
  - ABSOLUTELY READ-ONLY: this checker never recovers, never deletes a
    lock or txn marker, never claims, never publishes, never writes
    anything. It only reports and exits non-zero on unhealthy states.
"""
import json
import os
import sys
import time
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import factory_common as fc  # noqa: E402

TERMINAL = ("PUBLISHED", "BLOCKED", "FAIL")
IN_FLIGHT = ("WRITING", "QA", "REVIEW", "REPAIR", "PASS")


def _env_hours(name, default):
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return float(default)


def _parse_iso(ts):
    if not ts:
        return None
    try:
        return time.mktime(time.strptime(str(ts), "%Y-%m-%dT%H:%M:%SZ"))
    except Exception:
        return None


def check():
    stall_h = _env_hours("LIVENESS_STALL_HOURS", 6.0)
    lock_stale_h = _env_hours("LIVENESS_LOCK_STALE_HOURS", 6.0)
    now = time.time()
    rows = fc.load_matrix()
    by_id = {r["article_id"]: r for r in rows}
    unfinished = [r for r in rows if r["status"] not in TERMINAL]
    in_flight = [r for r in rows if r["status"] in IN_FLIGHT]

    # raw checkpoint read: timestamps and raw chunk ids come from the file;
    # matrix truth still wins for any status decision.
    cp_raw = None
    if fc.CHECKPOINT.exists():
        try:
            cp_raw = json.loads(fc.CHECKPOINT.read_text(encoding="utf-8"))
        except Exception:
            cp_raw = None

    out = {
        "rows": len(rows),
        "published": len([r for r in rows if r["status"] == "PUBLISHED"]),
        "unfinished": len(unfinished),
        "in_flight": {s: len([r for r in rows if r["status"] == s])
                      for s in IN_FLIGHT},
        "txn_pending": fc.txn_pending(),
        "lock_present": fc.LOCK.exists(),
        "checkpoint_present": bool(cp_raw),
        "checkpoint_updated_at": (cp_raw or {}).get("updated_at"),
        "current_chunk_ids": (cp_raw or {}).get("current_chunk_ids") or [],
        "thresholds": {"stall_hours": stall_h, "lock_stale_hours": lock_stale_h},
    }
    # progress/throughput are context signals only (never decide the verdict)
    for label, path in (("progress", fc.PROGRESS), ("throughput", fc.THROUGHPUT)):
        if path.exists():
            try:
                out[label] = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                out[label] = None

    # --- deterministic verdicts (ordered) -------------------------------
    if fc.txn_pending():
        out["status"] = "STALE_TXN"
        out["action"] = ("pending transaction marker blocks every mutation; "
                         "run recover and resolve it before anything else")
        return out
    if fc.LOCK.exists():
        age_h = (now - fc.LOCK.stat().st_mtime) / 3600
        out["lock_age_hours"] = round(age_h, 2)
        if age_h >= lock_stale_h and unfinished:
            out["status"] = "EXPIRED_OR_STALE_LOCK_WITH_UNFINISHED_WORK"
            out["action"] = ("stale writer lock while unfinished work exists; verify "
                            "the owner is gone, then recover the lock explicitly "
                            "(audited FORCE_STALE_LOCK_RECOVERY)")
            return out
    if cp_raw:
        chunk_ids = cp_raw.get("current_chunk_ids") or []
        bad = sorted(i for i in chunk_ids
                     if i not in by_id or by_id[i]["status"] == "PLANNED")
        if bad:
            out["status"] = "CHECKPOINT_STALE"
            out["conflict_ids"] = bad
            out["action"] = ("checkpoint claims a current chunk that is missing from "
                             "the matrix or still PLANNED; operator must reconcile "
                             "checkpoint and matrix before resuming")
            return out
    if in_flight:
        updated = _parse_iso((cp_raw or {}).get("updated_at"))
        fresh = updated is not None and (now - updated) / 3600 < stall_h
        if not fresh:
            out["status"] = "STALLED_ACTIVE"
            out["action"] = (f"in-flight rows with no checkpoint progress for more "
                             f"than {stall_h}h; operator must resume or recover the "
                             "stalled chunk")
            return out
        out["status"] = "HEALTHY_ACTIVE"
        out["action"] = "in-flight work with recent checkpoint progress"
        return out
    out["status"] = "HEALTHY_IDLE"
    out["action"] = ("no unfinished active work; PLANNED rows alone are not a "
                     "stall (the external writer may rest between chunks)")
    return out


def main():
    out = check()
    ok = out["status"] in ("HEALTHY_IDLE", "HEALTHY_ACTIVE")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"VANCHINH_FACTORY_LIVENESS_{out['status']}")
    print("VANCHINH_FACTORY_LIVENESS_PASS" if ok
          else "VANCHINH_FACTORY_LIVENESS_FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
