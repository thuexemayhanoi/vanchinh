#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate_content_matrix.py - deterministic matrix integrity gate."""
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import factory_common as fc

EXPECTED = {"KN": 350, "AT": 300, "XM": 350, "DL": 400, "CD": 300, "HD": 300}
BATCH_SIZE = 50
EXPECTED_BATCHES = 40


def main():
    errors, warnings = [], []
    rows = fc.load_matrix()
    if len(rows) != 2000:
        errors.append(f"row count {len(rows)} != 2000")
    ids = [r["article_id"] for r in rows]
    if len(set(ids)) != len(ids):
        dupes = {i for i in ids if ids.count(i) > 1}
        errors.append(f"duplicate article_id: {sorted(dupes)[:5]}")
    paths = [r["output_path"] for r in rows]
    if len(set(paths)) != len(paths):
        dupes = {p for p in paths if paths.count(p) > 1}
        errors.append(f"duplicate output_path: {sorted(dupes)[:5]}")
    slugs = [r["slug"] for r in rows]
    if len(set(slugs)) != len(slugs):
        errors.append("duplicate slug")
    cats = {}
    for r in rows:
        cats[r["category"]] = cats.get(r["category"], 0) + 1
        if r["category"] not in fc.CATEGORIES:
            errors.append(f"invalid category {r['category']}")
    for cat, n in EXPECTED.items():
        if cats.get(cat) != n:
            errors.append(f"category {cat}: {cats.get(cat)} != {n}")
    batches = {}
    for r in rows:
        batches.setdefault(r["batch_id"], []).append(r)
    if len(batches) != EXPECTED_BATCHES:
        errors.append(f"batch count {len(batches)} != {EXPECTED_BATCHES}")
    for b, rs in batches.items():
        if len(rs) != BATCH_SIZE:
            errors.append(f"batch {b} has {len(rs)} rows != {BATCH_SIZE}")
    for r in rows:
        if r["status"] not in fc.STATES:
            errors.append(f"{r['article_id']}: invalid status {r['status']}")
        if r["parent_hub"] != fc.CATEGORIES.get(r["category"]):
            errors.append(f"{r['article_id']}: parent_hub {r['parent_hub']} != {fc.CATEGORIES.get(r['category'])}")
        if not r["output_path"].startswith(f"cam-nang/"):
            errors.append(f"{r['article_id']}: output_path {r['output_path']} not under cam-nang/")
        if not r["output_path"].endswith(r["slug"] + ".html"):
            errors.append(f"{r['article_id']}: slug/output_path mismatch")
        if r["requires_sources"] == "true" and r["source_policy"] != "OFFICIAL_VN_PRIMARY":
            errors.append(f"{r['article_id']}: requires_sources=true but source_policy={r['source_policy']}")
        if r["commercial_link_target"] not in ("thuengay.html", "banggia.html", "chinhsach.html", "faq.html"):
            errors.append(f"{r['article_id']}: bad commercial_link_target {r['commercial_link_target']}")
        if r["repair_attempts"].strip() and not r["repair_attempts"].isdigit():
            errors.append(f"{r['article_id']}: repair_attempts not numeric")
        try:
            ra = int(r["repair_attempts"] or 0)
        except ValueError:
            ra = 99
        if ra > fc.MAX_REPAIR:
            errors.append(f"{r['article_id']}: repair_attempts {ra} > {fc.MAX_REPAIR}")
    if fc.txn_pending():
        warnings.append("pending transaction marker present - run recover before mutations")
    problems = fc.validate_nav_taxonomy()
    for e in problems:
        print("ERROR taxonomy:", e)
    for e in errors:
        print("ERROR:", e)
    for w in warnings:
        print("WARN:", w)
    print(f"matrix rows={len(rows)} categories={cats} batches={len(batches)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
