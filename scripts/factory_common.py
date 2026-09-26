#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""factory_common.py - shared factory library (Python)."""
import csv
import json
import os
import pathlib
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
MATRIX = pathlib.Path(os.environ.get("CONTENT_MATRIX", str(ROOT / "data" / "content-matrix.csv")))
FACTS = json.loads((ROOT / "config" / "business-facts.json").read_text(encoding="utf-8"))
RUBRIC = json.loads((ROOT / "config" / "article-rubric.json").read_text(encoding="utf-8"))
OWNERSHIP = json.loads((ROOT / "config" / "seo-ownership.json").read_text(encoding="utf-8"))
PROGRESS = ROOT / "reports" / "batches" / "factory-progress.json"
LOCK = ROOT / "data" / "batches" / "txn" / "run.lock"
TXN = ROOT / "data" / "batches" / "txn" / "txn.json"

STATES = ["PLANNED", "WRITING", "QA", "REVIEW", "REPAIR", "PASS", "PUBLISHED", "FAIL", "BLOCKED"]
TRANSITIONS = {
    "PLANNED": ["WRITING"],
    "WRITING": ["QA"],
    "QA": ["PASS", "REVIEW", "FAIL"],
    "REVIEW": ["REPAIR", "BLOCKED"],
    "REPAIR": ["QA"],
    "PASS": ["PUBLISHED"],
    "PUBLISHED": [],
    "FAIL": ["REPAIR"],
    "BLOCKED": [],
}
MAX_REPAIR = 3
CATEGORIES = {"KN": "kinhnghiem.html", "AT": "antoan.html", "XM": "xemay.html",
              "DL": "dulich.html", "CD": "cungduong.html", "HD": "hoidap.html"}
BASE = "https://thuexemayhanoi.github.io/vanchinh/"

# --- Navigation taxonomy contract -------------------------------------------
# UI exposes exactly 3 public "Cẩm nang" groups; the factory taxonomy keeps
# 6 canonical categories. Groups live in config/seo-ownership.json
# ("navigation_groups"); these helpers validate/derive from that config.
HUB_PAGE_SIZE = 50  # deterministic pagination: max article links per hub page


def nav_groups():
    """Ordered [(group_name, [hub_page, ...])] from source-of-truth config."""
    return [(g["name"], list(g["hubs"])) for g in OWNERSHIP["navigation_groups"]]


def nav_group_categories():
    """Ordered [(group_name, [category_code, ...])] from source-of-truth config."""
    return [(g["name"], list(g["categories"])) for g in OWNERSHIP["navigation_groups"]]


def validate_nav_taxonomy():
    """Return list of taxonomy violations (empty list = valid)."""
    problems = []
    gs = OWNERSHIP.get("navigation_groups", [])
    if len(gs) != 3:
        problems.append(f"expected exactly 3 navigation groups, found {len(gs)}")
    seen_hubs, seen_cats = [], []
    for g in gs:
        seen_hubs += g["hubs"]
        seen_cats += g["categories"]
        for hub, cat in zip(g["hubs"], g["categories"]):
            if CATEGORIES.get(cat) != hub:
                problems.append(f"group '{g['name']}': hub {hub} does not match category {cat}")
    if sorted(seen_hubs) != sorted(set(seen_hubs)):
        problems.append("a hub appears in more than one navigation group")
    if sorted(seen_hubs) != sorted(CATEGORIES.values()):
        problems.append("navigation groups do not cover exactly the 6 canonical hubs")
    if sorted(seen_cats) != sorted(CATEGORIES.keys()):
        problems.append("navigation groups do not cover exactly the 6 canonical categories")
    return problems


def listing_page(hub_id, page_number):
    """Deterministic listing page path for hub pagination (page >= 2)."""
    return f"{hub_id}-trang-{page_number}.html"

MATRIX_FIELDS = ["article_id", "batch_id", "category", "status", "primary_keyword",
                 "secondary_keywords", "search_intent", "working_title", "slug", "output_path",
                 "parent_hub", "requires_sources", "source_policy", "internal_link_targets",
                 "commercial_link_target", "author", "score", "quality_status",
                 "repair_attempts", "published_date", "last_checked", "notes"]


def load_matrix():
    with MATRIX.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def save_matrix(rows):
    with MATRIX.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=MATRIX_FIELDS)
        w.writeheader()
        w.writerows(rows)


def valid_transition(old, new):
    return new in TRANSITIONS.get(old, [])


class LockHeld(Exception):
    pass


def acquire_lock(operator="operator", max_age_hours=6):
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    if LOCK.exists():
        age_h = (time.time() - LOCK.stat().st_mtime) / 3600
        data = {}
        try:
            data = json.loads(LOCK.read_text(encoding="utf-8"))
        except Exception:
            pass
        if age_h < max_age_hours:
            raise LockHeld(f"run.lock held by {data.get('operator', '?')} age={age_h:.2f}h; "
                           f"refuse mutations. Stale recovery: verify owner then delete {LOCK} (explicit, audited).")
        # stale lock: require explicit flag
        if os.environ.get("FORCE_STALE_LOCK_RECOVERY") != "1":
            raise LockHeld(f"STALE lock (age {age_h:.2f}h). Re-run with FORCE_STALE_LOCK_RECOVERY=1 "
                           f"after verifying no other operator is active.")
        os.environ.pop("FORCE_STALE_LOCK_RECOVERY", None)
    LOCK.write_text(json.dumps({"operator": operator, "acquired": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                               ensure_ascii=False), encoding="utf-8")
    return True


def release_lock():
    if LOCK.exists():
        LOCK.unlink()


def txn_pending():
    return TXN.exists()


def begin_txn(plan):
    TXN.parent.mkdir(parents=True, exist_ok=True)
    if txn_pending():
        raise RuntimeError(f"Pending transaction marker exists: {TXN}. Run --recover first; refusing new mutations.")
    TXN.write_text(json.dumps({"plan": plan, "state": "IN_PROGRESS",
                               "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                              ensure_ascii=False, indent=2), encoding="utf-8")


def finish_txn(result):
    data = json.loads(TXN.read_text(encoding="utf-8"))
    data["state"] = "COMPLETE"
    data["result"] = result
    data["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    TXN.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    TXN.unlink()


def recover_txn():
    """Recover/verify after interruption. Without git here, we verify matrix/file consistency
    against the recorded plan; incomplete writes are reverted by re-deriving from plan."""
    if not txn_pending():
        print("no pending transaction")
        return 0
    data = json.loads(TXN.read_text(encoding="utf-8"))
    plan = data.get("plan", {})
    rows = load_matrix()
    by_id = {r["article_id"]: r for r in rows}
    problems = []
    for item in plan.get("articles", []):
        r = by_id.get(item["article_id"])
        target = item.get("target_status", "PUBLISHED")
        f = ROOT / item["output_path"]
        if target == "PUBLISHED":
            if r["status"] not in ("PUBLISHED", "PASS"):
                problems.append(f"{item['article_id']}: matrix status {r['status']} but file exists={f.exists()}")
            if not f.exists():
                # not written yet -> roll back to WRITING
                if r["status"] not in ("PLANNED", "WRITING"):
                    r["status"] = "WRITING"
        else:
            if r["status"] != target:
                r["status"] = target
    save_matrix(rows)
    if problems:
        print("RECOVER problems:")
        for p in problems:
            print(" -", p)
    TXN.unlink()
    print("transaction marker cleared after consistency pass")
    return 0


def write_progress(published_commit_sha=""):
    rows = load_matrix()
    counts = {s: 0 for s in STATES}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    batches = {}
    for r in rows:
        b = r["batch_id"]
        st = batches.setdefault(b, {"total": 0, "published": 0})
        st["total"] += 1
        if r["status"] == "PUBLISHED":
            st["published"] += 1
    completed = [b for b, s in sorted(batches.items()) if s["published"] == s["total"]]
    active = next((b for b, s in sorted(batches.items()) if 0 < s["published"] < s["total"]), None)
    next_batch = next((b for b, s in sorted(batches.items()) if s["published"] == 0), None)
    prev = {}
    if PROGRESS.exists():
        try:
            prev = json.loads(PROGRESS.read_text(encoding="utf-8"))
        except Exception:
            pass
    out = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total": len(rows),
        "planned": counts.get("PLANNED", 0),
        "writing": counts.get("WRITING", 0),
        "qa": counts.get("QA", 0),
        "review": counts.get("REVIEW", 0),
        "repair": counts.get("REPAIR", 0),
        "pass": counts.get("PASS", 0),
        "published": counts.get("PUBLISHED", 0),
        "fail": counts.get("FAIL", 0),
        "blocked": counts.get("BLOCKED", 0),
        "completed_batches": len(completed),
        "active_batch": active,
        "next_batch": next_batch,
        "published_commit_sha": published_commit_sha or prev.get("published_commit_sha", ""),
    }
    PROGRESS.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
