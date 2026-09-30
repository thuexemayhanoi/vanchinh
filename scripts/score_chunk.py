#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""score_chunk.py - bulk scoring (quality + SEO) for a chunk of article IDs.

Avoids one process per article: scores quality (canonical scorer) and SEO in
one pass. Individual scorers remain available for diagnostics.

Usage:
  score_chunk.py KN-0001 KN-0002 ...
  score_chunk.py --batch B01 --limit 50
"""
import argparse
import json
import pathlib
import re
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import factory_common as fc
import score_article_seo

ROOT = fc.ROOT


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--batch", default=None)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    rows = fc.load_matrix()
    if args.batch:
        br = [r for r in rows if r["batch_id"] == args.batch
              and r["status"] in ("WRITING", "QA", "REPAIR", "REVIEW", "PASS")]
        br.sort(key=lambda r: r["article_id"])
        if args.limit:
            br = br[:args.limit]
        ids = [r["article_id"] for r in br]
    else:
        ids = args.ids
    if not ids:
        print(json.dumps({"error": "no ids given"}))
        return 2
    known = {r["article_id"] for r in rows}
    out = []
    for aid in ids:
        if aid not in known:
            out.append({"article_id": aid, "error": "not in matrix"})
            continue
        sres = score_article_seo.score_article_seo(aid, write=True)
        out.append({"article_id": aid, "seo_score": sres.get("seo_score"),
                    "seo_status": sres.get("seo_status")})
    score_article_seo.seo_summary()
    print(json.dumps({"scored": len(out), "results": out}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())