#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""score_article.py - deterministic 100-point rubric scorer.

Usage: score_article.py <article_id>
Scores the article file at the matrix output_path (or WRITING draft path),
applies weights from config/article-rubric.json, applies critical-failure
overrides, and prints JSON {score, quality_status, critical}.
"""
import json
import pathlib
import re
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import factory_common as fc


def main():
    if len(sys.argv) < 2:
        print("usage: score_article.py <article_id>")
        return 2
    aid = sys.argv[1]
    rows = [r for r in fc.load_matrix() if r["article_id"] == aid]
    if not rows:
        print(json.dumps({"article_id": aid, "error": "not in matrix"}))
        return 1
    row = rows[0]
    path = fc.ROOT / row["output_path"]
    if not path.exists():
        print(json.dumps({"article_id": aid, "score": 0, "quality_status": "FAIL",
                          "critical": ["file_path_mismatch: article file missing"]}))
        return 0
    html = path.read_text(encoding="utf-8")

    req = fc.RUBRIC["requirements"]
    score, critical = 0.0, []

    # word count
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    wc = len(re.findall(r"[A-Za-zÀ-ỹ0-9]+", text))
    bands = fc.RUBRIC["word_count"]
    if bands["target_min"] <= wc <= bands["target_max"]:
        score += bands["weight"]
    elif bands["review_min"] <= wc <= bands["review_max"]:
        score += bands["weight"] * 0.6
    else:
        critical.append(f"word_count {wc} FAIL band")

    score += req["one_primary_intent"]["weight"] if len(re.findall(r"<h1", html)) == 1 else 0
    score += req["exactly_one_h1"]["weight"] if html.count("<h1") == 1 else 0
    title = re.search(r"<title>([^<]+)</title>", html)
    score += req["unique_title"]["weight"] if title else 0
    desc = re.search(r'<meta name="description" content="([^"]+)"', html)
    score += req["unique_meta_description"]["weight"] if desc else 0

    canon = re.search(r'<link rel="canonical" href="([^"]+)"', html)
    if canon and canon.group(1) == fc.BASE + row["output_path"]:
        score += req["self_canonical"]["weight"]
    else:
        critical.append("canonical incorrect")

    score += req["lang_vi"]["weight"] if 'lang="vi"' in html else 0
    score += req["article_jsonld"]["weight"] if '"Article"' in html or "Article" in html else 0
    score += req["breadcrumb_jsonld"]["weight"] if "BreadcrumbList" in html else 0
    score += req["author_date_metadata"]["weight"] if ("author" in html and "datePublished" in html) else 0

    local = [h for h in re.findall(r'href="([^"#]+)"', html)
             if not h.startswith(("http", "tel:", "mailto:", "//"))]
    editorial = [h for h in local if h in ("kinhnghiem.html", "antoan.html", "xemay.html",
                                           "dulich.html", "cungduong.html", "hoidap.html")]
    if req["internal_editorial_links"]["min"] <= len(editorial) <= req["internal_editorial_links"]["max"]:
        score += req["internal_editorial_links"]["weight"]
    elif len(editorial) > req["internal_editorial_links"]["max"]:
        score += req["internal_editorial_links"]["weight"] * 0.5
    else:
        score -= 5

    art_dir = path.resolve().parent
    hub_ok = any(str((art_dir / h).resolve()).endswith(row["parent_hub"]) for h in local)
    if hub_ok:
        score += req["parent_hub_link_required"]["weight"]
    else:
        critical.append("parent hub link missing")

    commercial_pages = {o["page"] for o in fc.OWNERSHIP["commercial_owners"]}
    commercial = [h for h in local if h in commercial_pages]
    if len(commercial) <= req["commercial_link_limit"]["max"]:
        score += req["commercial_link_limit"]["weight"]
    else:
        critical.append(f"commercial links {len(commercial)} > 1")

    # no duplicated paragraphs
    paras = re.findall(r"<p[^>]*>(.*?)</p>", html, flags=re.S)
    paras_n = [" ".join(p.split()) for p in paras if len(p.split()) > 12]
    if len(paras_n) != len(set(paras_n)):
        critical.append("duplicated paragraph detected")

    anchors = re.findall(r"<a[^>]*>([^<]{2,40})</a>", html)
    if len(anchors) - len(set(a.strip() for a in anchors)) <= 1:
        score += req["diverse_descriptive_anchors"]["weight"]

    for claim in fc.RUBRIC["forbidden_unsupported_claims"]:
        if claim.lower() in html.lower():
            critical.append(f"forbidden unsupported claim: {claim}")
    if re.search(r"[\u4e00-\u9fff\u0400-\u04ff\u3040-\u30ff]", html):
        critical.append("foreign-script corruption")
    for href in set(local):
        if not (art_dir / href).resolve().exists():
            critical.append(f"broken local link: {href}")
    if row["requires_sources"] == "true" and "nguồn" not in html.lower():
        critical.append("source section missing (requires_sources=true)")

    score = max(0, min(100, score))
    bands_cfg = fc.RUBRIC["score_bands"]
    if critical or score <= bands_cfg["FAIL"]["max"]:
        quality = "FAIL"
    elif score >= bands_cfg["PASS"]["min"]:
        quality = "PASS"
    else:
        quality = "REVIEW"
    out = {"article_id": aid, "word_count": wc, "score": round(score, 1),
           "quality_status": quality, "critical": critical}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
