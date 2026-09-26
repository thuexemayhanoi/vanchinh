#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_article_batch.py - batch orchestrator with lock + transaction + resume.

The external WRITER (Mistral run) writes article files; this tool manages
state, QA gates, publish consistency and reports.

Commands:
  run_article_batch.py plan [batch_id]          -> print unfinished work of a batch (resume-first)
  run_article_batch.py claim [batch_id]         -> acquire lock + mark rows WRITING
  run_article_batch.py qa [batch_id]            -> score all WRITING/QA rows of batch, transition
  run_article_batch.py publish [batch_id]       -> PASS->PUBLISHED with transaction + hub/sitemap/report updates
  run_article_batch.py recover                  -> verify/finish pending transaction
  run_article_batch.py progress                -> regenerate factory-progress.json
"""
import json
import subprocess
import sys
import time
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import factory_common as fc


def batch_rows(rows, batch_id):
    return [r for r in rows if r["batch_id"] == batch_id]


def run(cmd):
    return subprocess.run([sys.executable] + cmd, capture_output=True, text=True)


def cmd_plan(batch_id):
    rows = fc.load_matrix()
    br = batch_rows(rows, batch_id)
    unfinished = [r["article_id"] for r in br if r["status"] not in ("PUBLISHED", "BLOCKED")]
    print(json.dumps({
        "batch": batch_id, "total": len(br),
        "published": len([r for r in br if r["status"] == "PUBLISHED"]),
        "unfinished": unfinished,
        "note": "resume unfinished rows first; never claim a fresh batch while work remains",
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_claim(batch_id):
    fc.acquire_lock(operator=f"batch-{batch_id}")
    rows = fc.load_matrix()
    changed = 0
    for r in rows:
        if r["batch_id"] == batch_id and r["status"] in ("PLANNED", "WRITING"):
            if r["status"] == "PLANNED":
                r["status"] = "WRITING"
                changed += 1
    fc.save_matrix(rows)
    fc.write_progress()
    fc.release_lock()
    print(json.dumps({"claimed": changed, "batch": batch_id}))
    return 0


def cmd_qa(batch_id):
    fc.acquire_lock(operator=f"batch-{batch_id}")
    rows = fc.load_matrix()
    results = {"PASS": 0, "REVIEW": 0, "FAIL": 0}
    for r in rows:
        if r["batch_id"] != batch_id or r["status"] not in ("WRITING", "QA", "REPAIR"):
            continue
        p = run(["score_article.py", r["article_id"]])
        try:
            res = json.loads(p.stdout)
        except Exception:
            res = {"quality_status": "FAIL", "critical": ["scorer crashed"], "score": 0}
        q = res["quality_status"]
        results[q] += 1
        r["score"] = str(res.get("score", ""))
        if q == "PASS":
            r["status"] = "PASS"
            r["quality_status"] = "PASS"
        elif q == "REVIEW":
            r["status"] = "REVIEW"
            r["quality_status"] = "REVIEW"
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
        r["last_checked"] = time.strftime("%Y-%m-%d", time.gmtime())
    fc.save_matrix(rows)
    fc.write_progress()
    fc.release_lock()
    print(json.dumps({"batch": batch_id, "results": results}))
    return 0


def cmd_publish(batch_id):
    fc.acquire_lock(operator=f"batch-{batch_id}")
    rows = fc.load_matrix()
    to_publish = [r for r in rows if r["batch_id"] == batch_id and r["status"] == "PASS"]
    missing = [r["article_id"] for r in to_publish if not (fc.ROOT / r["output_path"]).exists()]
    if missing:
        print(json.dumps({"error": "refusing publish: PASS rows without files", "missing": missing}))
        fc.release_lock()
        return 1
    # taxonomy contract gate (must pass BEFORE any mutation):
    # each article in one valid category, correct parent hub, valid group mapping
    problems = fc.validate_nav_taxonomy()
    for r in to_publish:
        if r["category"] not in fc.CATEGORIES:
            problems.append(f"{r['article_id']}: invalid category {r['category']}")
        if r["parent_hub"] != fc.CATEGORIES.get(r["category"]):
            problems.append(f"{r['article_id']}: parent_hub {r['parent_hub']} != {fc.CATEGORIES.get(r['category'])}")
    if problems:
        print(json.dumps({"error": "refusing publish: taxonomy violations", "problems": problems[:20]}))
        fc.release_lock()
        return 1
    plan = {"articles": [{"article_id": r["article_id"], "output_path": r["output_path"],
                          "target_status": "PUBLISHED"} for r in to_publish],
            "updates": ["content-matrix", "hubs", "sitemap.xml", "reports"]}
    fc.begin_txn(plan)
    for r in to_publish:
        r["status"] = "PUBLISHED"
        r["published_date"] = time.strftime("%Y-%m-%d", time.gmtime())
    fc.save_matrix(rows)
    run(["generate_sitemap.py"])  # regenerate sitemap (PUBLISHED only)
    run(["generate_hub_lists.py"])  # regenerate hub article lists (grouped, paginated)
    fc.write_progress()
    fc.finish_txn({"published": len(to_publish), "batch": batch_id})
    fc.release_lock()
    print(json.dumps({"published": len(to_publish), "batch": batch_id}))
    return 0


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = sys.argv[1]
    if cmd == "recover":
        return fc.recover_txn()
    if cmd == "progress":
        print(json.dumps(fc.write_progress(), ensure_ascii=False, indent=2))
        return 0
    if len(sys.argv) < 3:
        print("missing batch_id")
        return 2
    batch_id = sys.argv[2]
    if cmd == "plan":
        return cmd_plan(batch_id)
    if cmd == "claim":
        return cmd_claim(batch_id)
    if cmd == "qa":
        return cmd_qa(batch_id)
    if cmd == "publish":
        return cmd_publish(batch_id)
    print(f"unknown command {cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
