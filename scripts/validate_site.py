#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate_site.py - static site quality gate (hours, domain, links, canonicals, H1, sitemap, robots).

Deterministic; exit 1 on any error. Run from repo root.
"""
import re
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import factory_common as fc

ROOT = fc.ROOT
BASE = fc.BASE
ERRORS = []


def err(msg):
    ERRORS.append(msg)


def main():
    pages = sorted(p for p in ROOT.glob("*.html"))
    if len(pages) < 20:
        err(f"unexpected page count {len(pages)}")
    canonicals = {}
    for p in pages:
        html = p.read_text(encoding="utf-8")
        name = p.name
        # canonical
        m = re.search(r'<link rel="canonical" href="([^"]+)"', html)
        expected = BASE + ("" if name == "index.html" else name)
        if not m:
            err(f"{name}: canonical missing")
        elif m.group(1) != expected:
            err(f"{name}: canonical {m.group(1)} != {expected}")
        else:
            canonicals.setdefault(m.group(1), []).append(name)
        # title / description / h1
        if not re.search(r"<title>[^<]{5,}</title>", html):
            err(f"{name}: title missing")
        if not re.search(r'<meta name="description" content="[^"]{10,}"', html):
            err(f"{name}: meta description missing")
        if html.count("<h1") != 1:
            err(f"{name}: h1 count {html.count('<h1')}")
        # forbidden domains / hours / claims
        if "chothuexemayohanoi" in html:
            err(f"{name}: wrong owner domain remains")
        for bad in ("9h - 21h", "9h-21h", "8h - 17h", "8h-17h", '"closes": "21:00"', '"closes": "08:00"'):
            if bad in html:
                err(f"{name}: forbidden hours '{bad}'")
        if re.search(r"mở cửa[^<]*24/7|hỗ trợ[^<]*24/7|cứu hộ[^<]*24/7", html, re.I):
            err(f"{name}: 24/7 support/opening claim")
        if "cọc 0đ" in html.lower():
            err(f"{name}: 'cọc 0đ' claim")
        if "giao xe 24/7" in html.lower():
            err(f"{name}: 'giao xe 24/7' claim")
        if re.search(r"[\u4e00-\u9fff\u0400-\u04ff\u3040-\u30ff]", html):
            err(f"{name}: foreign-script corruption")
        # local links / assets
        for href in set(re.findall(r'(?:href|src)="([^"#]+)"', html)):
            if href.startswith(("http", "tel:", "mailto:", "//", "data:")):
                continue
            if not (ROOT / href).exists():
                err(f"{name}: broken local target {href}")
        # schema hours if LocalBusiness present
        if '"LocalBusiness"' in html:
            mm = re.search(r'"opens": "(\d\d:\d\d)",\s*"closes": "(\d\d:\d\d)"', html)
            if not mm or mm.group(1) != "09:00" or mm.group(2) != "17:00":
                err(f"{name}: schema opening hours not 09:00-17:00")
    for url, names in canonicals.items():
        if len(names) > 1:
            err(f"duplicate canonical {url}: {names}")

    # sitemap
    sm = (ROOT / "sitemap.xml").read_text(encoding="utf-8") if (ROOT / "sitemap.xml").exists() else ""
    if not sm:
        err("sitemap.xml missing")
    else:
        locs = re.findall(r"<loc>([^<]+)</loc>", sm)
        if len(locs) != len(set(locs)):
            err("sitemap duplicate urls")
        for loc in locs:
            if not loc.startswith(BASE):
                err(f"sitemap url bad base: {loc}")
            rel = loc[len(BASE):]
            if rel and not (ROOT / rel).exists():
                err(f"sitemap url target missing: {rel}")
        # all published articles present
        published = {r["output_path"] for r in fc.load_matrix() if r["status"] == "PUBLISHED"}
        for pth in published:
            if BASE + pth not in locs:
                err(f"sitemap missing PUBLISHED article {pth}")
        unpublished = {r["output_path"] for r in fc.load_matrix() if r["status"] != "PUBLISHED"}
        for pth in unpublished:
            if BASE + pth in locs:
                err(f"sitemap contains non-published article {pth}")

    # robots
    rb = (ROOT / "robots.txt").read_text(encoding="utf-8") if (ROOT / "robots.txt").exists() else ""
    if not rb:
        err("robots.txt missing")
    elif "Disallow: /" in rb.replace("User-agent: *", "") and "Allow" not in rb:
        err("robots.txt blocks all content")
    if f"Sitemap: {BASE}sitemap.xml" not in rb:
        err("robots.txt sitemap reference missing/incorrect")

    # --- navigation taxonomy contract ---------------------------------------
    taxonomy = fc.validate_nav_taxonomy()
    for t in taxonomy:
        err(f"taxonomy: {t}")
    groups = fc.nav_groups()  # exactly 3 [(name, [hub, hub])]
    if len(groups) != 3:
        err(f"expected exactly 3 public cẩm nang groups, found {len(groups)}")
    for name, hubs in groups:
        if len(hubs) != 2:
            err(f"group '{name}' must expose exactly 2 canonical hubs")
        for h in hubs:
            if not (ROOT / h).exists():
                err(f"group '{name}': missing canonical hub page {h}")
    for hub in fc.CATEGORIES.values():
        if not (ROOT / hub).exists():
            err(f"missing canonical hub page {hub}")
    for p in pages:
        html = p.read_text(encoding="utf-8")
        m_side = re.search(r'<aside id="sidebar-menu".*?</aside>', html, re.S)
        m_foot = re.search(r"<footer.*?</footer>", html, re.S)
        for region, tag in ((m_side, "sidebar"), (m_foot, "footer")):
            if not region:
                err(f"{p.name}: {tag} region missing")
                continue
            block = region.group(0)
            for name, hubs in groups:
                if name.replace("&", "&amp;") not in block:
                    err(f"{p.name}: {tag} missing group label '{name}'")
            # menu/footer must never link individual articles from the corpus
            if 'href="cam-nang/' in block:
                err(f"{p.name}: {tag} contains direct article links (only hub/group links allowed)")
            for other in re.findall(r'href="([a-z]+-trang-\d+\.html)"', block):
                err(f"{p.name}: {tag} links listing page {other} (not allowed in nav)")
    # hub lists derive from Matrix truth (page 1 chunk per category)
    for hub_id, cat in {"kinhnghiem": "KN", "antoan": "AT", "xemay": "XM",
                        "dulich": "DL", "cungduong": "CD", "hoidap": "HD"}.items():
        hp = ROOT / f"{hub_id}.html"
        if not hp.exists():
            continue
        html = hp.read_text(encoding="utf-8")
        m = re.search(r'<div id="hub-list-' + hub_id + r'"[^>]*>(.*?)</div>', html, re.S)
        if not m:
            err(f"{hub_id}.html: hub-list container missing")
            continue
        listed = {h for h in re.findall(r'href="([^"]+)"', m.group(1)) if h.startswith("cam-nang/")}
        published = {r["output_path"] for r in fc.load_matrix()
                      if r["category"] == cat and r["status"] == "PUBLISHED"}
        page1 = set(sorted(published)[:fc.HUB_PAGE_SIZE])
        if listed != page1:
            err(f"{hub_id}.html: hub list drifts from Matrix truth "
                f"(listed={len(listed)} expected={len(page1)})")

    for e in ERRORS:
        print("ERROR:", e)
    print(f"validate_site: pages={len(pages)} errors={len(ERRORS)}")
    return 1 if ERRORS else 0


if __name__ == "__main__":
    sys.exit(main())
