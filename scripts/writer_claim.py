#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""writer_claim.py - MULTI-WRITER lease registry for the write-ahead queue.

Contract (TURBO MULTI-WRITER):
  - up to 3 independent writers prepare articles in parallel and NEVER
    collide on article IDs;
  - a writer leases up to MAX_LEASE (10) PLANNED rows of the active batch,
    in deterministic matrix order, skipping rows already covered by a LIVE
    lease from another writer;
  - leases expire after TTL_HOURS (48h) and are reclaimed automatically;
  - the registry lives at data/batches/writer-claims.json (env WRITER_CLAIMS)
    and is committed/pushed by the writers themselves. That path is NOT in
    the factory workflow paths filter, so registry pushes never trigger a
    production run;
  - when a registry push loses a race (non-fast-forward), the writer must
    fetch fresh main, run `merge` with the remote registry, re-claim what
    is still free, and push again (never force-push).

Commands:
  claim   --writer W [--count N|--ids A,B]  lease N free PLANNED rows (or
                                           exactly --ids when still free)
  release --writer W --ids A,B              drop leases (e.g. after push)
  show                                      print the registry + free rows
  merge   --file registry.json              merge a remote registry copy
                                           into the local one (earlier
                                           claim wins on conflicts)

Exit codes: 0 ok, 1 error (nothing mutated on error).
"""
import argparse
import json
import os
import pathlib
import sys
import time
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import factory_common as fc
from factory_push_selection import active_batch

REGISTRY = pathlib.Path(os.environ.get("WRITER_CLAIMS",
                                       str(fc.ROOT / "data" / "batches" / "writer-claims.json")))
MAX_LEASE = 10     # per-writer live lease cap (write-ahead buffer)
TTL_HOURS = 48.0   # leases older than this are dead and reclaimable
MAX_WRITERS = 3    # advisory cap; the registry refuses a 4th writer


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _epoch_of(iso):
    try:
        return time.mktime(time.strptime(iso, "%Y-%m-%dT%H:%M:%SZ"))
    except Exception:  # noqa: BLE001 - corrupt timestamps are treated as dead
        return 0.0


def load_registry():
    if not REGISTRY.is_file():
        return {"schema_version": "1", "updated_at": None, "leases": {}}
    try:
        d = json.loads(REGISTRY.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - corrupt registry = empty registry
        return {"schema_version": "1", "updated_at": None, "leases": {}}
    d.setdefault("schema_version", "1")
    d.setdefault("leases", {})
    return d


def save_registry(reg):
    reg["schema_version"] = "1"
    reg["updated_at"] = _now()
    reg["leases"] = {w: l for w, l in sorted(reg["leases"].items())}
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")


def _live_leases(reg, now=None):
    """{article_id: (writer, lease)} for all NON-expired leases."""
    now = now if now is not None else time.time()
    out = {}
    for w, l in reg["leases"].items():
        if _epoch_of(l.get("expires_at", "")) < now:
            continue  # expired -> dead, reclaimable
        for a in l.get("ids", []):
            out.setdefault(a, (w, l))
    return out


def _prune_expired(reg, now=None):
    """Drop expired leases in place (TTL reclaim); returns number dropped."""
    now = now if now is not None else time.time()
    dead = [w for w, l in reg["leases"].items()
            if _epoch_of(l.get("expires_at", "")) < now]
    for w in dead:
        del reg["leases"][w]
    return len(dead)


def _free_planned(rows, batch):
    """PLANNED rows of the active batch, deterministic matrix order."""
    return [r for r in rows if r["batch_id"] == batch and r["status"] == "PLANNED"]


def _expires_at(now=None):
    now = now if now is not None else time.time()
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + TTL_HOURS * 3600))


def cmd_claim(writer, count=None, ids=None, now=None):
    reg = load_registry()
    _prune_expired(reg, now)
    rows = fc.load_matrix()
    batch = active_batch(rows)
    if batch is None:
        print(json.dumps({"error": "factory complete: no active batch", "writer": writer}))
        return 1
    live = _live_leases(reg, now)
    mine = reg["leases"].get(writer)
    already = list(mine["ids"]) if mine else []
    want_ids = [a for a in (ids or []) if a]
    want_count = len(want_ids) if want_ids else (count or MAX_LEASE)
    if want_count > MAX_LEASE or len(already) + want_count > MAX_LEASE:
        print(json.dumps({"error": f"live lease cap is {MAX_LEASE} per writer",
                          "writer": writer, "already_leased": already,
                          "requested": want_count}))
        return 1
    planned = _free_planned(rows, batch)
    planned_ids = [r["article_id"] for r in planned]
    batch_of = {r["article_id"]: r["batch_id"] for r in rows}
    status_of = {r["article_id"]: r["status"] for r in rows}
    # explicit ids: must be PLANNED rows of the active batch and free
    for a in want_ids:
        if status_of.get(a) != "PLANNED" or batch_of.get(a) != batch:
            print(json.dumps({"error": f"{a}: not a PLANNED row of active batch {batch}",
                              "writer": writer}))
            return 1
        holder = live.get(a)
        if holder and holder[0] != writer:
            print(json.dumps({"error": f"{a}: already leased by writer {holder[0]}",
                              "writer": writer}))
            return 1
    # deterministic free ids: matrix order, skip live leases of other writers
    free = [a for a in planned_ids
            if a not in live or live[a][0] == writer]
    if want_ids:
        new_ids = [a for a in want_ids if a not in already]
    else:
        new_ids = [a for a in free if a not in already][:want_count]
    if not new_ids:
        print(json.dumps({"error": "no free PLANNED rows to lease",
                          "writer": writer, "batch": batch, "free_count": 0}))
        return 1
    lease_ids = sorted(set(already + new_ids))
    reg["leases"][writer] = {"ids": lease_ids, "claimed_at": _now(),
                             "expires_at": _expires_at(now),
                             "batch": batch}
    if len(reg["leases"]) > MAX_WRITERS:
        print(json.dumps({"error": f"registry already holds {MAX_WRITERS} writers",
                          "writers": sorted(reg["leases"])[:5]}))
        return 1
    save_registry(reg)
    out = {"writer": writer, "batch": batch, "claimed": new_ids,
           "leased_total": lease_ids, "count": len(lease_ids),
           "expires_at": reg["leases"][writer]["expires_at"],
           "registry": str(REGISTRY)}
    print("VANCHINH_WRITER_CLAIM " + json.dumps(out, ensure_ascii=False))
    return 0


def cmd_release(writer, ids):
    reg = load_registry()
    mine = reg["leases"].get(writer)
    if not mine:
        print(json.dumps({"writer": writer, "released": [], "leased_total": []}))
        return 0
    drop = [a for a in ids if a in mine["ids"]]
    keep = [a for a in mine["ids"] if a not in set(drop)]
    if keep:
        mine["ids"] = keep
    else:
        del reg["leases"][writer]
    save_registry(reg)
    print(json.dumps({"writer": writer, "released": drop, "leased_total": keep}))
    return 0


def cmd_show():
    reg = load_registry()
    _prune_expired(reg)
    rows = fc.load_matrix()
    batch = active_batch(rows)
    live = _live_leases(reg)
    planned = _free_planned(rows, batch) if batch else []
    taken = set(live)
    out = {"batch": batch,
           "writers": {w: l["ids"] for w, l in reg["leases"].items()},
           "planned_free": [r["article_id"] for r in planned
                             if r["article_id"] not in taken][:MAX_LEASE],
           "planned_total": len(planned), "registry": str(REGISTRY)}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_merge(path):
    """Merge a remote registry copy into the local registry. Every incoming
    id is checked against ALL local leases (including for writers not yet
    known locally); on a conflict the EARLIER claimed_at wins (tie: smaller
    writer name). The losing writer keeps its remaining ids and is reported
    so it can claim replacements. Never force-overrides; result is saved."""
    other = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    reg = load_registry()
    _prune_expired(reg)
    conflicts, lost = [], []
    for w, l in other.get("leases", {}).items():
        incoming = list(l.get("ids", []))
        keep = []
        for a in incoming:
            holder = next(((ow, ol) for ow, ol in reg["leases"].items()
                           if ow != w and a in ol["ids"]), None)
            if holder is None:
                keep.append(a)
                continue
            ow, ol = holder
            if (_epoch_of(l.get("claimed_at") or ""), w) < \
               (_epoch_of(ol.get("claimed_at") or ""), ow):
                # incoming (remote) claim is older -> remote wins the id
                ol["ids"] = [x for x in ol["ids"] if x != a]
                if not ol["ids"]:
                    del reg["leases"][ow]
                conflicts.append({"id": a, "winner": w, "loser": ow})
                keep.append(a)
            else:
                lost.append({"id": a, "winner": ow, "loser": w})
        if keep:
            lease = reg["leases"].get(w) or {}
            lease["ids"] = sorted(set(list(lease.get("ids", [])) + keep))[:MAX_LEASE]
            lease["claimed_at"] = l.get("claimed_at")
            lease["expires_at"] = l.get("expires_at")
            lease["batch"] = l.get("batch")
            reg["leases"][w] = lease
    save_registry(reg)
    print(json.dumps({"merged": True, "conflicts": conflicts,
                      "lost_to_other_writer": lost,
                      "writers": {w: l["ids"] for w, l in reg["leases"].items()}},
                     ensure_ascii=False, indent=2))
    return 0


def main():
    ap = argparse.ArgumentParser(add_help=True)
    sub = ap.add_subparsers(dest="command", required=True)
    c = sub.add_parser("claim")
    c.add_argument("--writer", required=True)
    g = c.add_mutually_exclusive_group()
    g.add_argument("--count", type=int, default=None)
    g.add_argument("--ids", default=None, help="comma-separated explicit ids")
    r = sub.add_parser("release")
    r.add_argument("--writer", required=True)
    r.add_argument("--ids", required=True)
    sub.add_parser("show")
    m = sub.add_parser("merge")
    m.add_argument("--file", required=True, help="remote registry JSON copy")
    args = ap.parse_args()
    if args.command == "claim":
        ids = [v.strip() for v in args.ids.split(",") if v.strip()] if args.ids else None
        return cmd_claim(args.writer, count=args.count, ids=ids)
    if args.command == "release":
        return cmd_release(args.writer, [v.strip() for v in args.ids.split(",") if v.strip()])
    if args.command == "show":
        return cmd_show()
    if args.command == "merge":
        return cmd_merge(args.file)
    return 2


if __name__ == "__main__":
    sys.exit(main())
