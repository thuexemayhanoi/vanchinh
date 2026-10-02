#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_cannibalization.py - protected commercial intent check.

Checks that no article (in cam-nang/) or matrix row targets a protected
commercial primary keyword owned by a commercial landing page, and that
no two commercial pages share a primary intent.
Title/H1 scan uses exact head-term matching (normalized): a long-tail
informational title that merely mentions a protected keyword targets a
different query and is not cannibalization; primary-keyword targeting by
matrix rows remains an exact-match violation.
Usage: check_cannibalization.py [article_id]
"""
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import factory_common as fc


def normalize(t):
    return " ".join(t.lower().split())


def main():
    errors = []
    protected = {}
    for o in fc.OWNERSHIP["commercial_owners"]:
        for kw in o["protected_keywords"]:
            protected.setdefault(normalize(kw), o["page"])

    # commercial page duplication
    intents = {}
    for o in fc.OWNERSHIP["commercial_owners"]:
        key = normalize(o["primary_intent"])
        if key in intents:
            errors.append(f"duplicate commercial intent: {o['page']} vs {intents[key]}")
        intents[key] = o["page"]

    rows = fc.load_matrix()
    limit = sys.argv[1] if len(sys.argv) > 1 else None
    for r in rows:
        if limit and r["article_id"] != limit:
            continue
        pk = normalize(r["primary_keyword"])
        if pk in protected:
            errors.append(f"{r['article_id']} ({r['output_path']}) targets protected keyword "
                          f"'{pk}' owned by {protected[pk]}")

    # scan existing article files for protected keywords in title/H1
    for f in (fc.ROOT / "cam-nang").rglob("*.html"):
        html = f.read_text(encoding="utf-8", errors="replace")
        mt = re_title = None
        import re
        mt = re.search(r"<title>([^<]*)</title>", html)
        h1 = re.search(r"<h1[^>]*>([^<]*)</h1>", html)
        for field, val in (("title", mt.group(1) if mt else ""), ("h1", h1.group(1) if h1 else "")):
            nv = normalize(val)
            for kw, page in protected.items():
                # exact head-term match only: long-tail informational titles
                # that mention the keyword target a different query; matrix
                # primary_keyword targeting is still checked exactly above.
                if nv == kw:
                    errors.append(f"{f} {field} targets protected keyword '{kw}' owned by {page}")

    for e in errors:
        print("ERROR:", e)
    print(f"cannibalization errors: {len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())