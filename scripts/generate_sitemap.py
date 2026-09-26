#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""generate_sitemap.py - regenerate sitemap.xml from Matrix truth.

Includes: commercial pages, informational hubs, PUBLISHED articles only.
Never PLANNED/WRITING/QA/REVIEW/REPAIR/PASS-but-not-published rows.
"""
import re
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import factory_common as fc

TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{urls}
</urlset>
"""


def main():
    urls = []
    seen = set()
    owners = [o["page"] for o in fc.OWNERSHIP["commercial_owners"]]
    hubs = [h["page"] for h in fc.OWNERSHIP["informational_hubs"]]
    for p in owners + hubs:
        loc = fc.BASE + ("" if p == "index.html" else p)
        if loc in seen:
            continue
        seen.add(loc)
        urls.append(f"  <url><loc>{loc}</loc></url>")
    for r in fc.load_matrix():
        if r["status"] == "PUBLISHED":
            loc = fc.BASE + r["output_path"]
            if loc in seen:
                print(f"WARN duplicate sitemap url {loc}")
                continue
            seen.add(loc)
            urls.append(f"  <url><loc>{loc}</loc></url>")
    # paginated hub listing pages (exist only when a hub exceeds HUB_PAGE_SIZE)
    for f in sorted(fc.ROOT.glob("*-trang-*.html")):
        m = re.match(r"^(kinhnghiem|antoan|xemay|dulich|cungduong|hoidap)-trang-\d+\.html$", f.name)
        if not m:
            continue
        loc = fc.BASE + f.name
        if loc in seen:
            continue
        seen.add(loc)
        urls.append(f"  <url><loc>{loc}</loc></url>")
    out = fc.ROOT / "sitemap.xml"
    out.write_text(TEMPLATE.format(urls="\n".join(urls)), encoding="utf-8")
    print(f"sitemap.xml urls={len(seen)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
