#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""score_article_seo.py - deterministic SEO score 0-100 per article.

Second, INDEPENDENT gate beside the canonical article quality score
(score_article.py). It never overrides critical quality failures:
publish requires quality PASS AND seo_score >= 90.

Weights (total 100):
  technical 20 | intent/on-page 25 | structure 20
  internal links 15 | structured data 10 | AI/GEO readiness 10

Bands: PASS >= 90, REVIEW 80-89, FAIL < 80.

Usage: score_article_seo.py <article_id> [--write/--no-write]
Writes reports/seo/articles/<article-id>.json unless --no-write.
"""
import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import factory_common as fc

import os
SEO_DIR = pathlib.Path(os.environ.get("SEO_REPORTS_DIR", str(fc.ROOT / "reports" / "seo")))
ARTICLES_DIR = SEO_DIR / "articles"

WEIGHTS = {"technical": 20, "intent": 25, "structure": 20,
           "internal_links": 15, "schema": 10, "ai_geo": 10}


def _text(html):
    t = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", " ", html, flags=re.S)
    return re.sub(r"<[^>]+>", " ", t)


def _norm(s):
    return re.sub(r"\s+", " ", s.strip().lower())


def score_article_seo(aid, write=True):
    rows = [r for r in fc.load_matrix() if r["article_id"] == aid]
    if not rows:
        return {"article_id": aid, "error": "not in matrix"}
    row = rows[0]
    path = fc.ROOT / row["output_path"]
    if not path.exists():
        return {"article_id": aid, "seo_score": 0, "seo_status": "FAIL",
                "sections": {k: 0 for k in WEIGHTS},
                "issues": ["article file missing"], "recommendations": ["write the article file first"]}
    html = path.read_text(encoding="utf-8")
    # Content QA scope: on-page analysis (intro, headings, paragraphs, links,
    # word count, keyword density) uses the <article> editorial region only,
    # so site chrome from the article shell cannot change SEO scoring.
    # Technical/schema checks keep using the full document.
    region = fc.article_region(html)
    text = _text(region)
    words = re.findall(r"[A-Za-zÀ-ỹ0-9]+", text)
    wc = len(words)
    pk = _norm(row["primary_keyword"])
    pk_words = pk.split()
    issues, recs = [], []
    sec = {k: 0 for k in WEIGHTS}

    # ---------------- technical (20) ----------------
    canon = re.search(r'<link rel="canonical" href="([^"]+)"', html)
    if canon and canon.group(1) == fc.BASE + row["output_path"]:
        sec["technical"] += 4
    else:
        issues.append("canonical incorrect or missing")
        recs.append("set self-canonical to base + output_path")
    if 'lang="vi"' in html:
        sec["technical"] += 2
    else:
        issues.append("lang=vi missing")
    m = re.search(r"<title>([^<]+)</title>", html)
    if m and len(m.group(1).strip()) >= 10:
        sec["technical"] += 4
    elif m:
        sec["technical"] += 2
        issues.append("title too short")
    else:
        issues.append("title missing")
    d = re.search(r'<meta name="description" content="([^"]+)"', html)
    if d:
        sec["technical"] += 3 if len(d.group(1)) >= 60 else 2
        if len(d.group(1)) < 60:
            recs.append("lengthen meta description to 60+ chars")
    else:
        issues.append("meta description missing")
    if html.count("<h1") == 1:
        sec["technical"] += 3
    else:
        issues.append("exactly one H1 violated")
    if re.search(r'<meta name="robots" content="index', html):
        sec["technical"] += 2
    else:
        issues.append("not indexable (robots meta)")
    if "<article" in html or '<main id="main"' in html or 'id="main"' in html:
        sec["technical"] += 2
    else:
        issues.append("no crawlable article content container")

    # ---------------- intent / on-page (25) ----------------
    title_txt = _norm(m.group(1)) if m else ""
    intro_words = words[:150]
    intro_txt = _norm(" ".join(intro_words))
    headings = [_norm(h) for h in re.findall(r"<h[23][^>]*>(.*?)</h[23]>", region, flags=re.S)]
    h1_txt = _norm(" ".join(re.findall(r"<h1[^>]*>(.*?)</h1>", html, flags=re.S)))
    if pk and pk in title_txt:
        sec["intent"] += 5
    elif pk_words and all(w in title_txt for w in pk_words):
        sec["intent"] += 3
    else:
        issues.append("primary keyword not represented in title")
    if pk and (pk in intro_txt or (intro_txt and all(w in intro_txt for w in pk_words))):
        sec["intent"] += 5
    elif pk and any(_norm(" ".join(words[:300])).find(w) >= 0 for w in pk_words):
        sec["intent"] += 3
    else:
        issues.append("intro does not address the primary topic early")
    if any(pk and pk in h for h in headings):
        sec["intent"] += 5
    elif any(pk_words and all(w in h for w in pk_words) for h in headings):
        sec["intent"] += 3
    else:
        recs.append("reflect the primary topic in at least one H2/H3")
    # direct answer in intro: first paragraph after H1 >= 30 words
    # first paragraph after the H1 (article shell may place metadata rows
    # between H1 and the opening paragraph)
    first_p = re.search(r"<h1.*?</h1>.*?<p[^>]*>(.*?)</p>", region, flags=re.S)
    if first_p and len(re.findall(r"[A-Za-zÀ-ỹ0-9]+", _text(first_p.group(1)))) >= 30:
        sec["intent"] += 5
    else:
        recs.append("answer the topic directly in the first paragraph after the H1")
    protected = [k for o in fc.OWNERSHIP["commercial_owners"] for k in o.get("protected_keywords", [])]
    title_lower = title_txt
    if not any(k in title_lower for k in protected):
        sec["intent"] += 5
    else:
        issues.append("title competes with a protected commercial intent")

    # ---------------- structure (20) ----------------
    h2 = re.findall(r"<h2[^>]*>", region)
    h3 = re.findall(r"<h3[^>]*>", region)
    sec["structure"] += 4 if len(h2) >= 3 else (2 if h2 else 0)
    if len(h2) < 3:
        recs.append("use at least 3 H2 sections")
    sec["structure"] += 3 if len(h3) >= 2 else (1 if h3 else 0)
    paras = [re.sub(r"<[^>]+>", " ", p) for p in re.findall(r"<p[^>]*>(.*?)</p>", region, flags=re.S)]
    paras_words = [len(re.findall(r"[A-Za-zÀ-ỹ0-9]+", p)) for p in paras if p.strip()]
    if paras_words:
        avg = sum(paras_words) / len(paras_words)
        sec["structure"] += 3 if avg <= 120 else 1
        if avg > 120:
            recs.append("break long paragraphs into readable ones")
    bands = fc.RUBRIC["word_count"]
    if bands["target_min"] <= wc <= bands["target_max"]:
        sec["structure"] += 4
    elif bands["review_min"] <= wc <= bands["review_max"]:
        sec["structure"] += 2
        recs.append("aim for 1600-2000 useful words")
    else:
        issues.append(f"word count {wc} outside usable band")
    paras_norm = [" ".join(p.split()) for p in paras if len(p.split()) > 12]
    if len(paras_norm) == len(set(paras_norm)):
        sec["structure"] += 3
    else:
        issues.append("duplicated paragraph detected")
    if re.search(r"tóm (lại|lược)|kết luận|tổng kết|điều cốt lõi", region, re.I):
        sec["structure"] += 3
    else:
        recs.append("add a summary/conclusion section")

    # ---------------- internal linking (15) ----------------
    local = [h for h in re.findall(r'href="([^"#]+)"', region)
             if not h.startswith(("http", "tel:", "mailto:", "//"))]
    art_dir = path.resolve().parent
    # basename-based classification (articles link hubs as "../../<hub>.html")
    editorial = [h for h in local if h.rsplit("/", 1)[-1] in fc.CATEGORIES.values()]
    if any(h.rsplit("/", 1)[-1] == row["parent_hub"] for h in local):
        sec["internal_links"] += 5
    else:
        issues.append("parent hub link missing")
    mn = fc.RUBRIC["requirements"]["internal_editorial_links"]["min"]
    mx = fc.RUBRIC["requirements"]["internal_editorial_links"]["max"]
    if mn <= len(editorial) <= mx:
        sec["internal_links"] += 4
    elif len(editorial) > mx:
        sec["internal_links"] += 2
        recs.append("keep editorial links within the rubric range")
    elif len(editorial) >= 2:
        sec["internal_links"] += 1
        recs.append(f"use {mn}-{mx} useful editorial links")
    else:
        recs.append(f"use {mn}-{mx} useful editorial links")
    commercial_pages = {o["page"] for o in fc.OWNERSHIP["commercial_owners"]}
    commercial = [h for h in local if h.rsplit("/", 1)[-1] in commercial_pages]
    if len(commercial) <= fc.RUBRIC["requirements"]["commercial_link_limit"]["max"]:
        sec["internal_links"] += 2
    else:
        issues.append("more than 1 commercial link")
    anchors = [a.strip() for a in re.findall(r"<a[^>]*>([^<]{2,40})</a>", region)]
    if len(anchors) - len(set(anchors)) <= 1:
        sec["internal_links"] += 2
    else:
        recs.append("diversify anchor texts")
    broken = [h for h in set(local) if not (art_dir / h).resolve().exists()]
    if not broken:
        sec["internal_links"] += 2
    else:
        issues.append(f"broken internal links: {broken[:3]}")

    # ---------------- structured data (10) ----------------
    if re.search(r'"@type"\s*:\s*"Article"', html):
        sec["schema"] += 3
    else:
        issues.append("Article JSON-LD missing")
    if "BreadcrumbList" in html:
        sec["schema"] += 2
    else:
        issues.append("BreadcrumbList JSON-LD missing")
    if re.search(r'"author"', html):
        sec["schema"] += 1
    if re.search(r'"datePublished"', html):
        sec["schema"] += 2
    else:
        recs.append("add truthful datePublished")
    if re.search(r'"mainEntityOfPage"', html):
        sec["schema"] += 2
    else:
        recs.append("add mainEntityOfPage")

    # ---------------- AI / GEO readiness (10) ----------------
    answer_passage = any(
        15 <= len(re.findall(r"[A-Za-zÀ-ỹ0-9]+", p)) <= 80 and (pk and pk in _norm(p))
        for p in paras)
    q_heading = any("?" in h for h in headings)
    if answer_passage or q_heading:
        sec["ai_geo"] += 3
    else:
        recs.append("include a concise direct-answer passage or a question heading")
    phone = re.findall(r"(?:0\d[\s.\-]?\d{2,3}[\s.\-]?\d{3,4})", region)
    correct_phone = fc.FACTS["phone"] in region or fc.FACTS.get("phone_e164", "") in region
    if (not phone) or correct_phone:
        sec["ai_geo"] += 2
    else:
        issues.append("phone number in article does not match business facts")
    if len(re.findall(r"<li[ >]", region)) >= 3:
        sec["ai_geo"] += 2
    else:
        recs.append("present factual statements as clear lists where useful")
    if wc and pk_words:
        pk_count = len(re.findall(re.escape(pk), _norm(text)))
        density = pk_count / wc * 100
        if density <= 3:
            sec["ai_geo"] += 3
        else:
            issues.append(f"keyword stuffing (density {density:.1f}%)")
            recs.append("reduce exact-keyword repetition; use natural wording")

    total = sum(sec[k] for k in WEIGHTS)
    total = max(0, min(100, round(total)))
    if total >= 90:
        status = "PASS"
    elif total >= 80:
        status = "REVIEW"
    else:
        status = "FAIL"
    out = {"article_id": aid, "word_count": wc, "seo_score": total, "seo_status": status,
           "sections": sec, "issues": issues, "recommendations": recs}
    if write:
        ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
        (ARTICLES_DIR / f"{aid}.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def seo_summary():
    """Aggregate factory-seo-summary.json from per-article reports."""
    files = sorted(ARTICLES_DIR.glob("*.json"))
    scores, statuses, all_issues = [], {"PASS": 0, "REVIEW": 0, "FAIL": 0}, {}
    for f in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        s = d.get("seo_score")
        if s is None:
            continue
        scores.append(s)
        st = d.get("seo_status", "FAIL")
        statuses[st] = statuses.get(st, 0) + 1
        for i in d.get("issues", []):
            key = i.split(":")[0][:60]
            all_issues[key] = all_issues.get(key, 0) + 1
    top = sorted(all_issues.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    out = {
        "articles_scored": len(scores),
        "average_score": round(sum(scores) / len(scores), 1) if scores else 0,
        "min_score": min(scores) if scores else 0,
        "max_score": max(scores) if scores else 0,
        "pass": statuses.get("PASS", 0),
        "review": statuses.get("REVIEW", 0),
        "fail": statuses.get("FAIL", 0),
        "top_common_issues": [{"issue": k, "count": v} for k, v in top],
    }
    SEO_DIR.mkdir(parents=True, exist_ok=True)
    (SEO_DIR / "factory-seo-summary.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("article_id", nargs="?")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--summary", action="store_true", help="regenerate aggregate summary only")
    args = ap.parse_args()
    if args.summary:
        print(json.dumps(seo_summary(), ensure_ascii=False, indent=2))
        return 0
    if not args.article_id:
        print(__doc__)
        return 2
    print(json.dumps(score_article_seo(args.article_id, write=not args.no_write),
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())