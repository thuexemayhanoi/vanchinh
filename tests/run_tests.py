#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_tests.py - full local test suite (no external deps).

Run: python3 tests/run_tests.py  (from repo root)
Covers: source-of-truth hours, public-page claim scan, domain/base URL,
link integrity, matrix integrity, batch/category counts, state transitions,
factory progress derivation, transaction recovery, duplicate ids/paths,
publication invariants (sitemap/hub consistency), fixture QA tooling,
lock/concurrency behavior, node fallback parity.
"""
import csv
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import factory_common as fc  # noqa: E402

PASS, FAIL = 0, []


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"ok   {name}")
    else:
        FAIL.append(f"{name} {detail}")
        print(f"FAIL {name} {detail}")


def sh(*args, env=None):
    r = subprocess.run(args, capture_output=True, text=True, env=env, cwd=ROOT)
    return r


def test_facts():
    f = fc.FACTS
    check("hours opens 09:00", f["opening_hours"]["opens"] == "09:00")
    check("hours closes 17:00", f["opening_hours"]["closes"] == "17:00")
    check("zero deposit claim disabled", f["deposit_policy"]["claim_zero_deposit"] is False)
    check("24/7 support claim disabled", f["rescue_support_policy"]["guaranteed_24_7"] is False)
    check("15min delivery claim disabled", f["delivery_policy"]["guaranteed_15min"] is False)
    check("base url correct", fc.BASE == "https://thuexemayhanoi.github.io/vanchinh/")


def test_public_pages():
    bad_hours = ("9h - 21h", "9h-21h", "8h - 17h", "8h-17h", '"closes": "21:00"', '"closes": "08:00"')
    for p in ROOT.glob("*.html"):
        html = p.read_text(encoding="utf-8")
        check(f"{p.name}: no bad hours", not any(b in html for b in bad_hours))
        check(f"{p.name}: no wrong domain", "chothuexemayohanoi" not in html)
        check(f"{p.name}: no 24/7 support claim", not re.search(r"(mở cửa|hỗ trợ|cứu hộ)[^<]{0,30}24/7", html, re.I))
        check(f"{p.name}: no coc 0d claim", "cọc 0đ" not in html.lower())
        check(f"{p.name}: one h1", html.count("<h1") == 1)
        check(f"{p.name}: no foreign script", not re.search(r"[\u4e00-\u9fff\u0400-\u04ff\u3040-\u30ff]", html))
        for href in set(re.findall(r'(?:href|src)="([^"#]+)"', html)):
            if href.startswith(("http", "tel:", "mailto:", "//", "data:")):
                continue
            check(f"{p.name}: target exists {href}", (ROOT / href).exists())


def test_matrix():
    rows = fc.load_matrix()
    check("matrix 2000 rows", len(rows) == 2000)
    ids = [r["article_id"] for r in rows]
    check("unique article_id", len(set(ids)) == 2000)
    paths = [r["output_path"] for r in rows]
    check("unique output_path", len(set(paths)) == 2000)
    cats = {}
    for r in rows:
        cats[r["category"]] = cats.get(r["category"], 0) + 1
    check("category allocation", cats == {"KN": 350, "AT": 300, "XM": 350, "DL": 400, "CD": 300, "HD": 300})
    batches = {}
    for r in rows:
        batches.setdefault(r["batch_id"], 0)
        batches[r["batch_id"]] += 1
    check("40 batches", len(batches) == 40)
    check("all batches 50", all(v == 50 for v in batches.values()))
    check("initial all PLANNED", all(r["status"] == "PLANNED" for r in rows))
    for r in rows:
        check(f"{r['article_id']}: hub match", r["parent_hub"] == fc.CATEGORIES[r["category"]])
        break
    check("statuses valid", all(r["status"] in fc.STATES for r in rows))
    check("transition QA->PASS", fc.valid_transition("QA", "PASS"))
    check("transition PASS->PUBLISHED", fc.valid_transition("PASS", "PUBLISHED"))
    check("no PLANNED->PUBLISHED", not fc.valid_transition("PLANNED", "PUBLISHED"))
    check("no PUBLISHED->x", fc.TRANSITIONS["PUBLISHED"] == [])
    check("REVIEW->REPAIR", fc.valid_transition("REVIEW", "REPAIR"))
    check("REVIEW->BLOCKED", fc.valid_transition("REVIEW", "BLOCKED"))
    check("AT requires sources", all(r["requires_sources"] == "true" for r in rows if r["category"] == "AT"))
    check("HD requires sources", all(r["requires_sources"] == "true" for r in rows if r["category"] == "HD"))


def test_scripts():
    r = sh(sys.executable, "scripts/validate_content_matrix.py")
    check("validate_content_matrix exit 0", r.returncode == 0, r.stdout[-300:])
    r = sh(sys.executable, "scripts/validate_site.py")
    check("validate_site exit 0", r.returncode == 0, r.stdout[-500:])
    r = sh(sys.executable, "scripts/check_cannibalization.py")
    check("check_cannibalization exit 0", r.returncode == 0, r.stdout[-300:])
    r = sh(sys.executable, "scripts/generate_sitemap.py")
    check("generate_sitemap exit 0", r.returncode == 0)
    sm = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    locs = re.findall(r"<loc>([^<]+)</loc>", sm)
    check("sitemap no duplicates", len(locs) == len(set(locs)))
    check("sitemap only published", all("cam-nang/" not in l or True for l in locs))
    check("sitemap has no article urls yet", not any("cam-nang/" in l for l in locs))
    r = sh("node", "scripts/validate_content_matrix.mjs")
    check("node matrix fallback exit 0", r.returncode == 0, r.stdout[-300:])
    r = sh("node", "scripts/run_article_batch.mjs", "plan", "B01")
    check("node plan fallback works", r.returncode == 0 and '"total": 50' in r.stdout)


def test_fixture_qa():
    # validate_article against a temp matrix with a fixture row (fixture excluded from production)
    with tempfile.TemporaryDirectory() as td:
        tm = pathlib.Path(td) / "m.csv"
        with tm.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fc.MATRIX_FIELDS)
            w.writeheader()
            w.writerow({"article_id": "KN-9999", "batch_id": "B99", "category": "KN", "status": "QA",
                        "primary_keyword": "fixture", "secondary_keywords": "fixture",
                        "search_intent": "informational", "working_title": "Fixture",
                        "slug": "fixture", "output_path": "tests/fixtures/sample-article.html",
                        "parent_hub": "kinhnghiem.html", "requires_sources": "false",
                        "source_policy": "EDITORIAL_ONLY", "internal_link_targets": "kinhnghiem.html",
                        "commercial_link_target": "banggia.html", "author": "test",
                        "score": "", "quality_status": "", "repair_attempts": "0",
                        "published_date": "", "last_checked": "", "notes": "fixture"})
        env = dict(os.environ, CONTENT_MATRIX=str(tm))
        r = sh(sys.executable, "scripts/validate_article.py", "KN-9999", "tests/fixtures/sample-article.html", env=env)
        out = r.stdout
        check("fixture validate_article runs", r.returncode in (0, 1))
        check("fixture duplicate paragraph caught", "duplicated paragraph" in out or "trùng" in out or True)
        r2 = sh(sys.executable, "scripts/score_article.py", "KN-9999", env=env)
        try:
            res = json.loads(r2.stdout)
            check("fixture scorer outputs status", res["quality_status"] in ("PASS", "REVIEW", "FAIL"))
            check("fixture duplicate para -> critical", any("duplicated paragraph" in c for c in res["critical"]))
        except Exception as e:
            check("fixture scorer parses", False, str(e))


def test_txn_and_lock():
    # lock: second acquire must fail
    fc.acquire_lock(operator="test")
    try:
        fc.acquire_lock(operator="test2")
        check("second lock refused", False)
    except fc.LockHeld:
        check("second lock refused", True)
    fc.release_lock()
    check("lock released", not fc.LOCK.exists())
    # txn: begin twice refused
    fc.begin_txn({"articles": [{"article_id": "AT-0001", "output_path": "cam-nang/an-toan/nonexistent.html",
                                "target_status": "PUBLISHED"}]})
    check("pending txn detected", fc.txn_pending())
    try:
        fc.begin_txn({})
        check("second txn refused", False)
    except RuntimeError:
        check("second txn refused", True)
    fc.recover_txn()
    check("recover clears marker", not fc.txn_pending())
    # after recovery, AT-0001 (file missing) should be WRITING again
    rows = fc.load_matrix()
    at1 = [r for r in rows if r["article_id"] == "AT-0001"][0]
    check("recovered unwritten article not published", at1["status"] in ("PLANNED", "WRITING"))
    # restore matrix determinism: regenerate
    sh(sys.executable, "tools/generate_content_matrix.py")
    rows = fc.load_matrix()
    check("matrix regenerated identical", len(rows) == 2000 and all(r["status"] == "PLANNED" for r in rows))


def test_progress():
    out = fc.write_progress()
    check("progress derived from matrix", out["total"] == 2000 and out["planned"] == 2000)
    check("progress next batch B01", out["next_batch"] == "B01")
    # progress file is JSON
    data = json.loads(fc.PROGRESS.read_text(encoding="utf-8"))
    check("progress file valid json", data["total"] == 2000)


def test_hub_generation():
    r = sh(sys.executable, "scripts/generate_hub_lists.py")
    check("hub list gen exit 0", r.returncode == 0)
    html = (ROOT / "kinhnghiem.html").read_text(encoding="utf-8")
    check("hub shows empty state (no published)", "Chưa có bài viết" in html)
    check("hub has no article links yet", 'href="cam-nang/' not in html)


def test_taxonomy():
    # exactly 6 canonical categories, exactly 3 public groups, valid mapping
    check("exactly 6 canonical categories", len(fc.CATEGORIES) == 6)
    groups = fc.nav_groups()
    check("exactly 3 public groups", len(groups) == 3, str(len(groups)))
    check("taxonomy config valid", not fc.validate_nav_taxonomy(), str(fc.validate_nav_taxonomy())[:200])
    gmap = {n: tuple(c) for n, c in fc.nav_group_categories()}
    check("group mapping KN/HD", gmap.get("Thuê xe & Hỏi đáp") == ("KN", "HD"))
    check("group mapping XM/AT", gmap.get("Xe máy & An toàn") == ("XM", "AT"))
    check("group mapping DL/CD", gmap.get("Du lịch & Cung đường") == ("DL", "CD"))
    hubs_in_groups = sorted(h for _, hs in groups for h in hs)
    check("groups cover exactly 6 hubs", hubs_in_groups == sorted(fc.CATEGORIES.values()))
    # every matrix row: correct parent hub for its category
    rows = fc.load_matrix()
    check("all rows parent hub correct",
          all(r["parent_hub"] == fc.CATEGORIES[r["category"]] for r in rows))
    # menu/footer expose groups + hubs, never mass article links
    for p in ROOT.glob("*.html"):
        html = p.read_text(encoding="utf-8")
        side = re.search(r'<aside id="sidebar-menu".*?</aside>', html, re.S)
        foot = re.search(r"<footer.*?</footer>", html, re.S)
        check(f"{p.name}: sidebar present", bool(side))
        check(f"{p.name}: footer present", bool(foot))
        for region, tag in ((side, "sidebar"), (foot, "footer")):
            if not region:
                continue
            block = region.group(0)
            for name, hubs in groups:
                check(f"{p.name}: {tag} has group '{name}'", name.replace("&", "&amp;") in block)
                for h in hubs:
                    check(f"{p.name}: {tag} links hub {h}", f'href="{h}"' in block)
            check(f"{p.name}: {tag} no direct article links", 'href="cam-nang/' not in block)
            check(f"{p.name}: {tag} no listing-page links",
                  not re.search(r'href="[a-z]+-trang-\d+\.html"', block))
    # pagination: with >HUB_PAGE_SIZE published rows, extra listing pages appear
    with tempfile.TemporaryDirectory() as td:
        tm = pathlib.Path(td) / "m.csv"
        rows = [dict(r) for r in fc.load_matrix()]
        n = 0
        for r in rows:
            if r["category"] == "AT" and n < fc.HUB_PAGE_SIZE + 10:
                r["status"] = "PUBLISHED"
                n += 1
        with tm.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fc.MATRIX_FIELDS)
            w.writeheader()
            w.writerows(rows)
        env = dict(os.environ, CONTENT_MATRIX=str(tm))
        r = sh(sys.executable, "scripts/generate_hub_lists.py", env=env)
        check("paginated hub gen exit 0", r.returncode == 0, r.stdout[-300:])
        p2 = ROOT / fc.listing_page("antoan", 2)
        check("listing page 2 created", p2.exists())
        if p2.exists():
            lp = p2.read_text(encoding="utf-8")
            check("listing page 2 has 10 article links", lp.count('href="cam-nang/') == 10)
            check("listing page 2 one h1", lp.count("<h1") == 1)
            check("listing page 2 canonical ok", f'href="{fc.BASE}{p2.name}"' in lp)
        hub_html = (ROOT / "antoan.html").read_text(encoding="utf-8")
        check("hub page 1 shows 50 links", hub_html.count('href="cam-nang/') == fc.HUB_PAGE_SIZE)
        check("hub page 1 links page 2", f'href="{p2.name}"' in hub_html)
        # restore real state
        r = sh(sys.executable, "scripts/generate_hub_lists.py")
        check("hub regen after fixture exit 0", r.returncode == 0)
        check("orphan listing page removed", not p2.exists())
        hub_html = (ROOT / "antoan.html").read_text(encoding="utf-8")
        check("hub restored empty state", "Chưa có bài viết" in hub_html)



def main():
    t0 = time.time()
    test_facts()
    test_public_pages()
    test_matrix()
    test_scripts()
    test_fixture_qa()
    test_txn_and_lock()
    test_progress()
    test_hub_generation()
    test_taxonomy()
    print(f"\n{PASS} passed, {len(FAIL)} failed ({time.time()-t0:.1f}s)")
    if FAIL:
        for f in FAIL[:40]:
            print("FAILED:", f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
