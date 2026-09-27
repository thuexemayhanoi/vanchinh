#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_article_batch.py - chunked batch orchestrator with lock + transaction + resume.

The external WRITER (Mistral run) writes article files; this tool manages
state, QA gates, publish consistency and reports.

Chunked, resume-safe flow (see docs/CONTENT-FACTORY.md):
  claim B01 --limit 5     -> lock + mark EXACTLY the selected rows WRITING
  (writer writes those files)
  qa B01 --ids ...        -> scoped QA (quality + SEO score) of the current
                             chunk only; untouched rows stay untouched
  publish B01             -> grouped transactional publish of eligible PASS
                             rows (quality PASS AND seo >= 90)

Batch stays 50 articles; the writer works in chunks (pilot 5, then 10).
Selection is deterministic: batch_id + article_id order.

Commands:
  plan [batch_id]          -> print unfinished work of a batch (resume-first)
  claim [batch_id] [--limit N | --ids a,b]  -> acquire lock + mark rows WRITING
  qa [batch_id] [--ids a,b | --limit N]     -> scoped score of chunk rows
  publish [batch_id] [--ids a,b] [--all]    -> PASS->PUBLISHED transaction
  checkpoint               -> print current writer checkpoint state
  recover                  -> verify/finish pending transaction
  progress                 -> regenerate factory-progress.json
  throughput               -> regenerate factory-throughput.json
"""
import argparse
import json
import subprocess
import sys
import time
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import factory_common as fc
import score_article_seo

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent


def batch_rows(rows, batch_id):
    return [r for r in rows if r["batch_id"] == batch_id]


def run(cmd):
    return subprocess.run([sys.executable, str(SCRIPTS_DIR / cmd[0])] + cmd[1:], capture_output=True, text=True)


def _parse_ids(value):
    if not value:
        return None
    return [v.strip() for v in value.split(",") if v.strip()]


def cmd_plan(batch_id):
    rows = fc.load_matrix()
    br = batch_rows(rows, batch_id)
    unfinished = [r["article_id"] for r in br if r["status"] not in ("PUBLISHED", "BLOCKED")]
    cp = fc.read_checkpoint()
    print(json.dumps({
        "batch": batch_id, "total": len(br),
        "published": len([r for r in br if r["status"] == "PUBLISHED"]),
        "unfinished": unfinished,
        "checkpoint": ({"batch": cp.get("batch"), "chunk_size": cp.get("chunk_size"),
                        "current_chunk_ids": cp.get("current_chunk_ids"),
                        "last_completed_step": cp.get("last_completed_step")} if cp else None),
        "note": "resume unfinished rows first; never claim a fresh batch while work remains",
    }, ensure_ascii=False, indent=2))
    return 0


def _select_claim_rows(br, limit, ids, cp):
    """Deterministic chunk selection: batch_id + article_id order.
    PLANNED rows first; WRITING rows of the checkpointed current chunk are
    re-selected so a resumed claim does not strand them."""
    order = {r["article_id"]: i for i, r in enumerate(br)}
    planned = sorted([r for r in br if r["status"] == "PLANNED"],
                     key=lambda r: r["article_id"])
    if ids:
        wanted = set(ids)
        sel = [r for r in br if r["article_id"] in wanted
               and r["status"] in ("PLANNED", "WRITING")]
        sel = sorted(sel, key=lambda r: r["article_id"])
        return sel
    current = set((cp or {}).get("current_chunk_ids") or [])
    resumed = sorted([r for r in br if r["article_id"] in current and r["status"] == "WRITING"],
                    key=lambda r: r["article_id"])
    fresh = planned[: max(0, (limit or fc.DEFAULT_CHUNK) - len(resumed))]
    return resumed + [r for r in fresh if r not in resumed]


def _claimable_batch(rows):
    """First batch (deterministic matrix order) that still has non-terminal rows.

    Terminal production states: PUBLISHED, BLOCKED, FAIL. The current
    unfinished batch MUST finish first: claiming any other batch is refused.
    Returns None when every row is terminal (factory idle)."""
    order = []
    for r in rows:
        if r["batch_id"] not in order:
            order.append(r["batch_id"])
    for b in order:
        if any(r["status"] not in ("PUBLISHED", "BLOCKED", "FAIL")
               for r in rows if r["batch_id"] == b):
            return b
    return None


def cmd_claim(batch_id, limit=None, ids=None):
    fc.acquire_lock(operator=f"batch-{batch_id}")
    try:
        rows = fc.load_matrix()
        # Invariant: the current unfinished batch must finish first.
        claimable = _claimable_batch(rows)
        if claimable is not None and claimable != batch_id:
            print(json.dumps({"error": "refusing claim: current unfinished batch must finish first",
                              "claimable_batch": claimable, "requested_batch": batch_id}))
            return 1
        br = batch_rows(rows, batch_id)
        cp = fc.read_checkpoint()
        sel = _select_claim_rows(br, limit, ids, cp)
        changed = 0
        for r in rows:
            if any(s["article_id"] == r["article_id"] for s in sel) and r["status"] == "PLANNED":
                r["status"] = "WRITING"
                changed += 1
        fc.save_matrix(rows)
        fc.write_progress()
        chunk_ids = [r["article_id"] for r in sel]
        written = set((cp or {}).get("written_ids") or []) | set(chunk_ids)
        fc.write_checkpoint(batch=batch_id,
                            chunk_size=len(chunk_ids),
                            current_chunk_ids=chunk_ids,
                            written_ids=sorted(written),
                            pending_qa_ids=chunk_ids,
                            last_completed_step="claim")
        print(json.dumps({"claimed": changed, "batch": batch_id, "chunk_ids": chunk_ids,
                          "chunk_size": len(chunk_ids)}))
    finally:
        fc.release_lock()
    return 0


def _qa_row(r):
    """Score one row: quality (canonical scorer) + SEO (second gate)."""
    p = run(["score_article.py", r["article_id"]])
    try:
        qres = json.loads(p.stdout)
    except Exception:
        qres = {"quality_status": "FAIL", "critical": ["scorer crashed"], "score": 0}
    sres = score_article_seo.score_article_seo(r["article_id"], write=True)
    return qres, sres


def _qa_verdict(qres, sres):
    """PASS requires quality PASS AND seo >= 90. Critical quality failure
    always overrides SEO. Quality FAIL and REVIEW handled by the state
    machine exactly as before; SEO < 90 downgrades PASS to REVIEW."""
    q = qres.get("quality_status", "FAIL")
    seo = int(sres.get("seo_score", 0) or 0)
    if q == "FAIL" or qres.get("critical"):
        return "FAIL"
    if q == "PASS":
        return "PASS" if seo >= fc.SEO_PASS_MIN else "REVIEW"
    return "REVIEW"  # quality REVIEW


def cmd_qa(batch_id, ids=None, limit=None):
    fc.acquire_lock(operator=f"batch-{batch_id}")
    try:
        rows = fc.load_matrix()
        br = batch_rows(rows, batch_id)
        cp = fc.read_checkpoint() or {}
        # scope: explicit ids > checkpoint current chunk > explicit limit > all
        if ids:
            scope = set(ids)
        elif cp.get("batch") == batch_id and cp.get("current_chunk_ids"):
            scope = set(cp["current_chunk_ids"])
        elif limit:
            wr = sorted([r for r in br if r["status"] in ("WRITING", "QA", "REPAIR")],
                        key=lambda r: r["article_id"])
            scope = {r["article_id"] for r in wr[:limit]}
        else:
            scope = {r["article_id"] for r in br if r["status"] in ("WRITING", "QA", "REPAIR")}
        results = {"PASS": 0, "REVIEW": 0, "FAIL": 0}
        pass_ids, review_ids, fail_ids, repair_ids = set(), set(), set(), set()
        for r in rows:
            if r["batch_id"] != batch_id or r["article_id"] not in scope:
                continue
            if r["status"] not in ("WRITING", "QA", "REPAIR"):
                continue
            qres, sres = _qa_row(r)
            verdict = _qa_verdict(qres, sres)
            results[verdict if verdict != "REVIEW" else "REVIEW"] += 1
            r["score"] = str(qres.get("score", ""))
            r["last_checked"] = time.strftime("%Y-%m-%d", time.gmtime())
            if verdict == "PASS":
                r["status"] = "PASS"
                r["quality_status"] = "PASS"
                pass_ids.add(r["article_id"])
            elif verdict == "REVIEW":
                r["status"] = "REVIEW"
                r["quality_status"] = "REVIEW"
                review_ids.add(r["article_id"])
            else:
                ra = int(r["repair_attempts"] or 0)
                if ra + 1 > fc.MAX_REPAIR:
                    r["status"] = "BLOCKED"
                    r["quality_status"] = "FAIL"
                    r["notes"] = "max repair attempts exceeded"
                else:
                    r["status"] = "REPAIR"
                    r["repair_attempts"] = str(ra + 1)
                    r["quality_status"] = "FAIL"
                    repair_ids.add(r["article_id"])
                fail_ids.add(r["article_id"])
        fc.save_matrix(rows)
        fc.write_progress()
        merged = dict(cp)
        merged_pass = set(merged.get("pass_ids") or []) | pass_ids
        pending_repair = set(merged.get("pending_repair_ids") or []) | repair_ids
        pending_publish = set(merged.get("pending_publish_ids") or []) | pass_ids
        fc.write_checkpoint(batch=batch_id,
                            current_chunk_ids=sorted(scope),
                            pass_ids=sorted(merged_pass),
                            pending_repair_ids=sorted(pending_repair),
                            pending_publish_ids=sorted(pending_publish),
                            pending_qa_ids=[],
                            last_completed_step="qa")
        score_article_seo.seo_summary()
        fc.write_throughput()
        print(json.dumps({"batch": batch_id, "scoped": sorted(scope), "results": results,
                          "pass": sorted(pass_ids), "repair": sorted(repair_ids)}))
    finally:
        fc.release_lock()
    return 0


def cmd_publish(batch_id, ids=None, all_pass=False):
    fc.acquire_lock(operator=f"batch-{batch_id}")
    try:
        rows = fc.load_matrix()
        to_publish = [r for r in rows if r["batch_id"] == batch_id and r["status"] == "PASS"]
        if ids:
            wanted = set(ids)
            to_publish = [r for r in to_publish if r["article_id"] in wanted]
        if not all_pass and not ids:
            # grouped publish of the current chunk only (checkpoint scope)
            cp = fc.read_checkpoint() or {}
            scope = set(cp.get("pending_publish_ids") or []) | set(cp.get("current_chunk_ids") or [])
            if scope:
                to_publish = [r for r in to_publish if r["article_id"] in scope]
        missing = [r["article_id"] for r in to_publish if not (fc.ROOT / r["output_path"]).exists()]
        if missing:
            print(json.dumps({"error": "refusing publish: PASS rows without files", "missing": missing}))
            return 1
        # SEO gate: quality PASS AND seo >= 90, both required
        seo_block = []
        for r in to_publish:
            sres = score_article_seo.score_article_seo(r["article_id"], write=True)
            if int(sres.get("seo_score", 0) or 0) < fc.SEO_PASS_MIN:
                seo_block.append({"article_id": r["article_id"], "seo_score": sres.get("seo_score")})
        if seo_block:
            print(json.dumps({"error": "refusing publish: SEO score below threshold",
                              "threshold": fc.SEO_PASS_MIN, "blocked": seo_block}))
            return 1
        # taxonomy contract gate (must pass BEFORE any mutation)
        problems = fc.validate_nav_taxonomy()
        for r in to_publish:
            if r["category"] not in fc.CATEGORIES:
                problems.append(f"{r['article_id']}: invalid category {r['category']}")
            if r["parent_hub"] != fc.CATEGORIES.get(r["category"]):
                problems.append(f"{r['article_id']}: parent_hub {r['parent_hub']} != {fc.CATEGORIES.get(r['category'])}")
        if problems:
            print(json.dumps({"error": "refusing publish: taxonomy violations", "problems": problems[:20]}))
            return 1
        plan = {"articles": [{"article_id": r["article_id"], "output_path": r["output_path"],
                              "target_status": "PUBLISHED"} for r in to_publish],
                "updates": ["content-matrix", "hubs", "sitemap.xml", "article-shells", "reports"]}
        fc.begin_txn(plan)
        for r in to_publish:
            r["status"] = "PUBLISHED"
            r["published_date"] = time.strftime("%Y-%m-%d", time.gmtime())
        fc.save_matrix(rows)
        r_sitemap = run(["generate_sitemap.py"])
        r_hubs = run(["generate_hub_lists.py"])
        if r_sitemap.returncode != 0 or r_hubs.returncode != 0:
            for r in to_publish:
                r["status"] = "PASS"
                r["published_date"] = ""
            fc.save_matrix(rows)
            rr_sitemap = run(["generate_sitemap.py"])
            rr_hubs = run(["generate_hub_lists.py"])
            fc.write_progress()
            if rr_sitemap.returncode == 0 and rr_hubs.returncode == 0:
                fc.TXN.unlink()
                print(json.dumps({"error": "publish rolled back: sitemap/hub regeneration failed",
                                  "batch": batch_id,
                                  "sitemap_rc": r_sitemap.returncode, "hubs_rc": r_hubs.returncode}))
                return 1
            print(json.dumps({"error": "publish rollback incomplete: run recover", "batch": batch_id}))
            return 1
        # rebuild the article shell UI layer for all PUBLISHED articles
        # (derived state, deterministic + idempotent, same transaction)
        r_shell = run(["build_article_shell.py"])
        if r_shell.returncode != 0:
            for r in to_publish:
                r["status"] = "PASS"
                r["published_date"] = ""
            fc.save_matrix(rows)
            run(["generate_sitemap.py"])
            run(["generate_hub_lists.py"])
            fc.write_progress()
            fc.TXN.unlink()
            print(json.dumps({"error": "publish rolled back: article shell rebuild failed",
                              "batch": batch_id}))
            return 1
        fc.write_progress()
        fc.finish_txn({"published": len(to_publish), "batch": batch_id})
        # checkpoint bookkeeping
        cp = fc.read_checkpoint() or {}
        published = set(cp.get("published_ids") or []) | {r["article_id"] for r in to_publish}
        pending_pub = set(cp.get("pending_publish_ids") or []) - published
        pass_ids = set(cp.get("pass_ids") or []) - published
        cp2 = fc.write_checkpoint(batch=batch_id,
                                  pass_ids=sorted(pass_ids),
                                  pending_publish_ids=sorted(pending_pub),
                                  published_ids=sorted(published),
                                  last_completed_step="publish")
        cp2["chunks_completed"] = int(cp2.get("chunks_completed") or 0) + 1
        cp2["publish_operations"] = int(cp2.get("publish_operations") or 0) + 1
        fc.CHECKPOINT.write_text(json.dumps(cp2, ensure_ascii=False, indent=2), encoding="utf-8")
        score_article_seo.seo_summary()
        fc.write_throughput()
        print(json.dumps({"published": len(to_publish), "batch": batch_id,
                          "ids": [r["article_id"] for r in to_publish]}))
    finally:
        fc.release_lock()
    return 0


def cmd_checkpoint():
    cp = fc.read_checkpoint()
    print(json.dumps(cp, ensure_ascii=False, indent=2) if cp else "no active checkpoint")
    return 0


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("command", choices=["plan", "claim", "qa", "publish", "recover",
                                        "progress", "checkpoint", "throughput"])
    ap.add_argument("batch_id", nargs="?")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--ids", type=str, default=None)
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    cmd = args.command
    if cmd == "recover":
        return fc.recover_txn()
    if cmd == "progress":
        print(json.dumps(fc.write_progress(), ensure_ascii=False, indent=2))
        return 0
    if cmd == "throughput":
        print(json.dumps(fc.write_throughput(), ensure_ascii=False, indent=2))
        return 0
    if cmd == "checkpoint":
        return cmd_checkpoint()
    if not args.batch_id:
        print("missing batch_id")
        return 2
    batch_id = args.batch_id
    ids = _parse_ids(args.ids)
    if cmd == "plan":
        return cmd_plan(batch_id)
    if cmd == "claim":
        return cmd_claim(batch_id, limit=args.limit, ids=ids)
    if cmd == "qa":
        return cmd_qa(batch_id, ids=ids, limit=args.limit)
    if cmd == "publish":
        return cmd_publish(batch_id, ids=ids, all_pass=args.all)
    print(f"unknown command {cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())