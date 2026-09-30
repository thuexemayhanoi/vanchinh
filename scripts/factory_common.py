#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""factory_common.py - shared factory library (Python)."""
import csv
import json
import os
import pathlib
import re
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
MATRIX = pathlib.Path(os.environ.get("CONTENT_MATRIX", str(ROOT / "data" / "content-matrix.csv")))
FACTS = json.loads((ROOT / "config" / "business-facts.json").read_text(encoding="utf-8"))
RUBRIC = json.loads((ROOT / "config" / "article-rubric.json").read_text(encoding="utf-8"))
OWNERSHIP = json.loads((ROOT / "config" / "seo-ownership.json").read_text(encoding="utf-8"))
PROGRESS = pathlib.Path(os.environ.get("PROGRESS_FILE", str(ROOT / "reports" / "batches" / "factory-progress.json")))
# LOCK/TXN are env-overridable so sandbox tests NEVER create markers at the
# production paths. Defaults unchanged = production contract.
LOCK = pathlib.Path(os.environ.get("LOCK_FILE", str(ROOT / "data" / "batches" / "lock.json")))
TXN = pathlib.Path(os.environ.get("TXN_FILE", str(ROOT / "data" / "batches" / "txn" / "txn.json")))

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


def article_region(html):
    """Return the <article>...</article> editorial region of an article file.

    Content QA (link classification, word count, anchors, paragraphs, sources)
    runs on this region so site chrome (header/sidebar/footer added by the
    article shell) never contaminates article scoring. Head/schema checks
    (title, canonical, JSON-LD) stay on the full document. Bare writer
    articles contain exactly one <article> so this is a no-op scope there.
    """
    m = re.search(r"<article[\s>].*?</article>", html, flags=re.S)
    return m.group(0) if m else html


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
            raise LockHeld(f"lock.json held by {data.get('operator', '?')} age={age_h:.2f}h; "
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
    """FAIL-CLOSED transaction recovery (docs/RECOVERY.md contract).

    Verifies the pending transaction against repository truth (matrix +
    article files). Only a PROVEN deterministic state may complete or roll
    back; consistency PASS is required BEFORE the marker is removed. Any
    ambiguity or conflict KEEPS the marker and returns non-zero so no
    further mutation can happen until an operator resolves it.

    Safe verdicts (marker cleared, rc 0):
      - verified rollback: every plan article is still in its pre-write
        state (PASS) with its file present - the publish never mutated the
        matrix, nothing was half-written, no derived output was touched.
      - verified completion: every plan article is PUBLISHED and its file
        exists; the remaining deterministic derived outputs (sitemap, hub
        lists, article shells, progress) are regenerated and verified
        FIRST - only then is the marker cleared.
    Everything else (missing files, matrix/file disagreement, partial
    publish, malformed/ambiguous marker or plan, unknown plan ids) is a
    conflict: marker KEPT, rc 1, exact conflicts reported.
    Recover NEVER guesses a status, NEVER rewrites the matrix, NEVER
    resets repair counts, NEVER force-clears the marker.
    """
    if not txn_pending():
        print("no pending transaction")
        return 0
    try:
        data = json.loads(TXN.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"RECOVERY BLOCKED: cannot parse transaction marker {TXN}: {e}")
        print("marker kept; no mutation performed; operator must resolve manually")
        return 1
    plan = data.get("plan") if isinstance(data, dict) else None
    articles = plan.get("articles") if isinstance(plan, dict) else None
    if not isinstance(articles, list) or not articles:
        print(f"RECOVERY BLOCKED: malformed or empty transaction plan in {TXN}")
        print("marker kept; no mutation performed; operator must resolve manually")
        return 1
    rows = load_matrix()
    by_id = {r["article_id"]: r for r in rows}
    conflicts = []
    completed = []
    rolled_back = []
    for item in articles:
        if not isinstance(item, dict):
            conflicts.append(f"malformed plan item: {item!r}")
            continue
        aid = item.get("article_id")
        out = item.get("output_path")
        if not aid or not out:
            conflicts.append(f"plan item missing article_id/output_path: {item!r}")
            continue
        r = by_id.get(aid)
        if r is None:
            conflicts.append(f"{aid}: plan article not found in matrix")
            continue
        target = item.get("target_status", "PUBLISHED")
        f = ROOT / out
        if target == "PUBLISHED":
            if r["status"] == "PUBLISHED":
                if f.exists():
                    completed.append(aid)
                else:
                    conflicts.append(f"{aid}: matrix status PUBLISHED but file missing {out}")
            elif r["status"] == "PASS":
                if f.exists():
                    rolled_back.append(aid)
                else:
                    conflicts.append(f"{aid}: pre-write status PASS but file missing {out}")
            else:
                conflicts.append(
                    f"{aid}: ambiguous matrix status {r['status']} for pending PUBLISH "
                    f"(file exists={f.exists()})")
        else:
            # the transaction marker only exists for publish transactions;
            # any other recorded target is an ambiguous/unsupported plan.
            conflicts.append(
                f"{aid}: unsupported/ambiguous plan target_status {target} "
                f"(file exists={f.exists()})")
    if conflicts:
        print("RECOVERY BLOCKED: transaction state is ambiguous or inconsistent")
        for c in conflicts:
            print(" -", c)
        print(f"marker KEPT at {TXN}; no mutation performed; no publish will proceed")
        print("operator must resolve the conflicts above, then re-run recover")
        return 1
    if completed and rolled_back:
        print("RECOVERY BLOCKED: partial publish detected "
              f"(completed={sorted(completed)}, rolled_back={sorted(rolled_back)})")
        print("marker KEPT; operator must resolve the partial publish manually")
        return 1
    if rolled_back:
        TXN.unlink()
        print(f"recovery: verified rollback of {len(rolled_back)} article(s): "
              f"{', '.join(sorted(rolled_back))}")
        print("transaction marker cleared after verified rollback (no publish happened)")
        return 0
    # verified completion: regenerate the remaining deterministic derived
    # outputs FIRST; only a fully successful regeneration clears the marker.
    for script in ("generate_sitemap.py", "generate_hub_lists.py", "build_article_shell.py"):
        p = subprocess.run([sys.executable, str(pathlib.Path(__file__).parent / script)],
                           capture_output=True, text=True)
        if p.returncode != 0:
            print(f"RECOVERY BLOCKED: deterministic regeneration failed ({script})")
            print("marker kept; operator must resolve and re-run recover")
            return 1
    write_progress()
    TXN.unlink()
    print(f"recovery: verified completion of {len(completed)} article(s): "
          f"{', '.join(sorted(completed))}")
    print("transaction marker cleared after consistency pass "
          "(derived outputs regenerated and verified)")
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


# --- Chunked writer checkpoint + throughput (operational state) ------------
# Matrix remains the ULTIMATE source of truth; the checkpoint is operational
# state only. On any conflict (e.g. checkpoint says pending but matrix says
# PUBLISHED) the MATRIX wins.
CHECKPOINT = pathlib.Path(os.environ.get("WRITER_CHECKPOINT", str(ROOT / "data" / "batches" / "writer-checkpoint.json")))
THROUGHPUT = pathlib.Path(os.environ.get("FACTORY_THROUGHPUT", str(ROOT / "reports" / "batches" / "factory-throughput.json")))
DEFAULT_CHUNK = 50  # Simple Production Mode: batch = chunk = 50 articles
SEO_PASS_MIN = 90  # publish gate: quality PASS AND seo_score >= 90

CHECKPOINT_SCHEMA = "1"


def read_checkpoint():
    if not CHECKPOINT.exists():
        return None
    try:
        cp = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    except Exception:
        return None
    if cp.get("schema_version") != CHECKPOINT_SCHEMA:
        return None
    # Reconcile against the matrix (matrix > checkpoint): every pending list
    # is DERIVED from current matrix statuses so stale entries are impossible.
    # A repaired row that now PASSes leaves pending_repair_ids; a published
    # row leaves every pending list. The checkpoint never overrides the matrix.
    rows = load_matrix()
    by_id = {r["article_id"]: r for r in rows}
    status = {aid: r["status"] for aid, r in by_id.items()}
    published = {aid for aid in (cp.get("published_ids") or [])
                 if status.get(aid) == "PUBLISHED"}
    cp["published_ids"] = sorted(published)
    derived_keep = {
        # key: (keep predicate on current matrix status)
        "pending_qa_ids": lambda s: s in ("WRITING", "QA"),
        "pending_repair_ids": lambda s: s == "REPAIR",
        "pass_ids": lambda s: s == "PASS",
        "pending_publish_ids": lambda s: s == "PASS",
        "written_ids": lambda s: s != "PLANNED",
    }
    for key, keep in derived_keep.items():
        vals = set(cp.get(key) or [])
        vals = {v for v in vals if v in by_id and keep(status[v])}
        cp[key] = sorted(vals)
    cp["current_chunk_ids"] = [i for i in (cp.get("current_chunk_ids") or [])
                               if i in by_id and status[i] != "PUBLISHED"]
    return cp


def write_checkpoint(batch=None, chunk_size=None, current_chunk_ids=None,
                     last_completed_step=None, **lists):
    cp = read_checkpoint() or {
        "schema_version": CHECKPOINT_SCHEMA, "batch": batch, "chunk_size": chunk_size,
        "current_chunk_ids": [], "written_ids": [], "pending_qa_ids": [],
        "pending_repair_ids": [], "pass_ids": [], "pending_publish_ids": [],
        "published_ids": [], "last_completed_step": "", "started_at": None,
        "updated_at": None,
    }
    if batch:
        cp["batch"] = batch
    if chunk_size:
        cp["chunk_size"] = chunk_size
    if current_chunk_ids is not None:
        cp["current_chunk_ids"] = sorted(set(current_chunk_ids))
    if not cp.get("started_at"):
        cp["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for key in ("written_ids", "pending_qa_ids", "pending_repair_ids", "pass_ids",
                "pending_publish_ids", "published_ids"):
        if key in lists and lists[key] is not None:
            cp[key] = sorted(set(lists[key]))
        elif key in lists:
            pass
    if last_completed_step:
        cp["last_completed_step"] = last_completed_step
    cp["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT.write_text(json.dumps(cp, ensure_ascii=False, indent=2), encoding="utf-8")
    return cp


def clear_checkpoint():
    if CHECKPOINT.exists():
        CHECKPOINT.unlink()


def write_throughput():
    """Derived, REAL numbers only (from matrix + checkpoint). No estimates."""
    rows = load_matrix()
    cp = read_checkpoint() or {}
    by_id = {r["article_id"]: r for r in rows}
    written = [r for r in rows if r["status"] != "PLANNED"]
    out = {
        "current_batch": cp.get("batch"),
        "chunk_size": cp.get("chunk_size"),
        "chunks_completed": cp.get("chunks_completed", 0) if cp else 0,
        "written": len(written),
        "quality_pass": len([r for r in rows if r["status"] in ("PASS", "PUBLISHED")]),
        "seo_pass": len([r for r in rows if r["status"] in ("PASS", "PUBLISHED")]),
        "published": len([r for r in rows if r["status"] == "PUBLISHED"]),
        "repair_count": sum(int(r["repair_attempts"] or 0) for r in rows),
        "publish_operations": cp.get("publish_operations", 0) if cp else 0,
        "elapsed_minutes": cp.get("elapsed_minutes", 0) if cp else 0,
        "effective_articles_per_hour": 0,
    }
    started = cp.get("started_at") if cp else None
    if started:
        try:
            t0 = time.mktime(time.strptime(started, "%Y-%m-%dT%H:%M:%SZ"))
            elapsed = max(1, (time.time() - t0) / 60)
            out["elapsed_minutes"] = round(elapsed, 1)
            out["effective_articles_per_hour"] = round(out["published"] / (elapsed / 60), 1)
        except Exception:
            pass
    if out["publish_operations"] and out["elapsed_minutes"]:
        pass  # effective rate already real-derived above
    THROUGHPUT.parent.mkdir(parents=True, exist_ok=True)
    THROUGHPUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out