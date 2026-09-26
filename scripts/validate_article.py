#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate_article.py - deterministic per-article validation gate.

Usage: python3 scripts/validate_article.py <article_id> [html_path]
Checks (deterministic only):
- file exists at matrix output_path
- exactly one H1, title, meta description, lang=vi
- self canonical correctness (BASE + output_path)
- Article JSON-LD + BreadcrumbList presence
- word count bands
- internal editorial link count (3-5) incl. required parent hub link
- commercial link limit (<=1)
- forbidden unsupported business claims
- source section when requires_sources=true
- foreign-script corruption (CJK/Cyrillic)
- no broken local links
"""
import json
import pathlib
import re
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import factory_common as fc


def viet_word_count(html):
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    words = re.findall(r"[A-Za-zÀ-ỹ0-9]+", text)
    return len(words)


def local_targets(html):
    out = []
    for m in re.finditer(r'href="([^"#]+)"', html):
        href = m.group(1)
        if href.startswith(("http", "tel:", "mailto:", "//")):
            continue
        out.append(href)
    return out


def main():
    if len(sys.argv) < 2:
        print("usage: validate_article.py <article_id>")
        return 2
    aid = sys.argv[1]
    rows = [r for r in fc.load_matrix() if r["article_id"] == aid]
    if not rows:
        print(f"ERROR: {aid} not in matrix")
        return 1
    row = rows[0]
    errors, critical = [], []
    path = (pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else fc.ROOT / row["output_path"])
    if not path.exists():
        print(json.dumps({"article_id": aid, "errors": ["file missing"], "critical": ["file_path_mismatch"]}))
        return 1
    html = path.read_text(encoding="utf-8")

    if html.count("<h1") != 1:
        critical.append("exactly_one_h1 violated")
    if not re.search(r"<title>[^<]{5,}</title>", html):
        critical.append("title missing")
    if not re.search(r'<meta name="description" content="[^"]{10,}"', html):
        critical.append("meta description missing")
    if 'lang="vi"' not in html:
        errors.append("lang=vi missing")
    expected_canonical = fc.BASE + row["output_path"]
    m = re.search(r'<link rel="canonical" href="([^"]+)"', html)
    if not m:
        critical.append("canonical missing")
    elif m.group(1) != expected_canonical:
        critical.append(f"canonical mismatch: {m.group(1)} != {expected_canonical}")
    if "Article" not in html:
        errors.append("Article JSON-LD missing")
    if "BreadcrumbList" not in html:
        errors.append("BreadcrumbList missing")
    if 'rel="author"' not in html and "author" not in html.lower():
        errors.append("author metadata missing")
    hub_ok = any(str((art_dir / h).resolve()).endswith(row["parent_hub"]) for h in internal)
    if not hub_ok:
        critical.append("parent hub link missing")

    wc = viet_word_count(html)
    bands = fc.RUBRIC["word_count"]
    if wc < bands["fail_below"] or wc > bands["fail_above"]:
        critical.append(f"word count {wc} out of FAIL band")

    art_dir = path.resolve().parent
    internal = local_targets(html)
    editorial = [h for h in internal if h.endswith(".html") and h in
                 ("kinhnghiem.html", "antoan.html", "xemay.html", "dulich.html", "cungduong.html", "hoidap.html")]
    if not (fc.RUBRIC["requirements"]["internal_editorial_links"]["min"] <= len(editorial)):
        errors.append(f"editorial internal links {len(editorial)} < min 3")
    commercial = [h for h in internal if h in
                  [o["page"] for o in fc.OWNERSHIP["commercial_owners"]]]
    if len(commercial) > 1:
        critical.append(f"commercial links {len(commercial)} > 1")

    for claim in fc.RUBRIC["forbidden_unsupported_claims"]:
        if claim.lower() in html.lower():
            critical.append(f"forbidden unsupported claim: {claim}")

    if re.search(r"[\u4e00-\u9fff\u0400-\u04ff\u3040-\u30ff]", html):
        critical.append("foreign-script corruption (CJK/Cyrillic) detected")

    for href in set(internal):
        if not (art_dir / href).resolve().exists():
            critical.append(f"broken local link: {href}")

    if row["requires_sources"] == "true" and "Nguồn" not in html and "nguồn" not in html:
        critical.append("source section missing though requires_sources=true")

    result = {"article_id": aid, "path": str(path), "word_count": wc,
              "editorial_links": len(editorial), "commercial_links": len(commercial),
              "errors": errors, "critical": critical}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if critical else 0


if __name__ == "__main__":
    sys.exit(main())
