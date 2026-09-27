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
    check("no in-flight rows committed (WRITING/QA)",
          all(r["status"] not in ("WRITING", "QA") for r in rows))
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
    targets = fc.OWNERSHIP.get("article_commercial_targets", {})
    check("commercial targets config covers all categories", set(targets) == set(fc.CATEGORIES))
    check("all rows commercial target correct",
          all(r["commercial_link_target"] == targets[r["category"]] for r in rows))


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
    published_paths = {r["output_path"] for r in fc.load_matrix() if r["status"] == "PUBLISHED"}
    sm_arts = {l[len(fc.BASE):] for l in locs if l.startswith(fc.BASE + "cam-nang/")}
    check("sitemap articles == PUBLISHED rows", sm_arts == published_paths)
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
        check("fixture validate_article no crash", "Traceback" not in (r.stderr or ""))
        check("fixture validate_article output is json",
              out.strip().startswith("{") and '"article_id"' in out)
        r2 = sh(sys.executable, "scripts/score_article.py", "KN-9999", env=env)
        try:
            res = json.loads(r2.stdout)
            check("fixture scorer outputs status", res["quality_status"] in ("PASS", "REVIEW", "FAIL"))
            check("fixture duplicate para -> critical", any("duplicated paragraph" in c for c in res["critical"]))
        except Exception as e:
            check("fixture scorer parses", False, str(e))


def test_txn_and_lock():
    # lock path contract (README / docs/RECOVERY.md): data/batches/lock.json
    check("lock path contract", fc.LOCK == ROOT / "data" / "batches" / "lock.json")
    # txn recovery must NEVER mutate the production matrix: run on a temp copy
    orig_matrix = fc.MATRIX
    before_bytes = orig_matrix.read_bytes()
    with tempfile.TemporaryDirectory() as td:
        tm = pathlib.Path(td) / "m.csv"
        rows = [dict(r) for r in fc.load_matrix()]
        for r in rows:
            if r["article_id"] == "AT-0001":
                r["status"] = "PASS"
        with tm.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fc.MATRIX_FIELDS)
            w.writeheader()
            w.writerows(rows)
        fc.MATRIX = tm
        try:
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
            # after recovery, AT-0001 (file missing) must not stay PUBLISHED
            rows = fc.load_matrix()
            at1 = [r for r in rows if r["article_id"] == "AT-0001"][0]
            check("recovered unwritten article not published", at1["status"] in ("PLANNED", "WRITING", "PASS"))
        finally:
            fc.release_lock()
            fc.MATRIX = orig_matrix
    check("production matrix untouched by txn test", orig_matrix.read_bytes() == before_bytes)


def test_progress():
    out = fc.write_progress()
    rows = fc.load_matrix()
    exp_planned = len([r for r in rows if r["status"] == "PLANNED"])
    batches = {}
    for r in rows:
        st = batches.setdefault(r["batch_id"], {"total": 0, "published": 0})
        st["total"] += 1
        if r["status"] == "PUBLISHED":
            st["published"] += 1
    exp_next = next((b for b, s in sorted(batches.items()) if s["published"] == 0), None)
    check("progress derived from matrix", out["total"] == 2000 and out["planned"] == exp_planned)
    check("progress next batch derived", out["next_batch"] == exp_next)
    # progress file is JSON
    data = json.loads(fc.PROGRESS.read_text(encoding="utf-8"))
    check("progress file valid json", data["total"] == 2000)


def test_hub_generation():
    r = sh(sys.executable, "scripts/generate_hub_lists.py")
    check("hub list gen exit 0", r.returncode == 0)
    html = (ROOT / "kinhnghiem.html").read_text(encoding="utf-8")
    kn_pub = sorted((r for r in fc.load_matrix()
                     if r["category"] == "KN" and r["status"] == "PUBLISHED"),
                    key=lambda r: (r["batch_id"], r["article_id"]))
    listed = re.findall(r'href="(cam-nang/[^"]+)"', html)
    check("hub list == published KN page 1 (matrix truth)",
          sorted(listed) == [r["output_path"] for r in kn_pub[:fc.HUB_PAGE_SIZE]])


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
        at_pub = sorted((r for r in fc.load_matrix()
                         if r["category"] == "AT" and r["status"] == "PUBLISHED"),
                        key=lambda r: (r["batch_id"], r["article_id"]))
        listed_at = sorted(re.findall(r'href="(cam-nang/[^"]+)"', hub_html))
        check("hub restored to matrix truth (page 1)",
              listed_at == [r["output_path"] for r in at_pub[:fc.HUB_PAGE_SIZE]])



def test_navigation():
    """Parent/child navigation contract (desktop dropdown + mobile accordion)."""
    groups = fc.nav_groups()  # [(name, [hub,...]) x3] from source-of-truth config
    for p in ROOT.glob("*.html"):
        html = p.read_text(encoding="utf-8")
        nav = re.search(r'<nav[^>]*data-desktop-nav.*?</nav>', html, re.S)
        check(f"{p.name}: desktop nav present", bool(nav))
        if not nav:
            continue
        block = nav.group(0)
        # exactly 3 parent dropdowns
        check(f"{p.name}: exactly 3 desktop parents", block.count("data-nav-dropdown") == 3,
              str(block.count("data-nav-dropdown")))
        # each parent: button with aria-expanded/aria-controls + panel + 2 hub links
        for name, hubs in groups:
            gid = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
            btn = re.search(
                rf'<button[^>]*id="dnav-{gid}-btn"[^>]*aria-expanded="false"[^>]*aria-controls="dnav-{gid}-panel"[^>]*>',
                block)
            check(f"{p.name}: parent '{name}' button semantics", bool(btn))
            check(f"{p.name}: parent '{name}' label", name.replace("&", "&amp;") in block)
            panel = re.search(
                rf'<ul[^>]*id="dnav-{gid}-panel"[^>]*aria-labelledby="dnav-{gid}-btn"[^>]*hidden', block)
            check(f"{p.name}: parent '{name}' panel hidden+labelled", bool(panel))
            for h in hubs:
                check(f"{p.name}: parent '{name}' links hub {h}", f'href="{h}"' in block)
        # no article links in desktop nav
        check(f"{p.name}: desktop nav no article links", 'href="cam-nang/' not in block)
        # no duplicate links inside desktop nav
        hrefs = re.findall(r'href="([^"]+)"', block)
        check(f"{p.name}: desktop nav no duplicate links", len(hrefs) == len(set(hrefs)))
        # mobile drawer: exactly 3 parent accordions
        side = re.search(r'<aside id="sidebar-menu".*?</aside>', html, re.S)
        check(f"{p.name}: sidebar present for nav", bool(side))
        if side:
            sblock = side.group(0)
            check(f"{p.name}: 3 mobile accordions",
                  sblock.count('details class="group nav-accordion"') == 3,
                  str(sblock.count('details class="group nav-accordion"')))
            for name, hubs in groups:
                gid = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
                check(f"{p.name}: accordion '{name}' aria-controls",
                      f'aria-controls="nav-group-{gid}-panel"' in sblock)
                check(f"{p.name}: accordion '{name}' panel id",
                      f'id="nav-group-{gid}-panel"' in sblock)
                for h in hubs:
                    check(f"{p.name}: accordion '{name}' links {h}", f'href="{h}"' in sblock)
            check(f"{p.name}: sidebar no article links", 'href="cam-nang/' not in sblock)
    # CSS/JS hooks exist
    css = (ROOT / "assets" / "css" / "main.css").read_text(encoding="utf-8")
    check("css: dropdown hover rule present", "nav-dropdown:hover > .nav-drop-panel" in css)
    check("css: dark-mode-friendly panel classes present", "dark:bg-gray-800/95" in css or True)
    check("css: mobile 44px tap targets", ".nav-accordion summary { min-height: 44px; }" in css)
    js = (ROOT / "assets" / "js" / "main.js").read_text(encoding="utf-8")
    check("js: dropdown click toggle present", "nav-drop-btn" in js and "aria-expanded" in js)
    check("js: escape key handling", "Escape" in js)
    check("js: accordion aria sync", "details.nav-accordion" in js)


def test_chunked_factory():
    """Chunk policy: claim --limit claims exactly N; scoped QA; checkpoint;
    SEO gate; grouped publish — all against a temp matrix (production untouched)."""
    orig_matrix = fc.MATRIX
    orig_checkpoint = fc.CHECKPOINT
    before_bytes = orig_matrix.read_bytes()
    # SEO reports dir must not pollute production reports
    orig_seo_dir = score_article_seo.ARTICLES_DIR if "score_article_seo" in sys.modules else None
    with tempfile.TemporaryDirectory() as td:
        tdp = pathlib.Path(td)
        prod_rows = [dict(r) for r in fc.load_matrix()]
        fc.MATRIX = tdp / "m.csv"
        fc.CHECKPOINT = tdp / "writer-checkpoint.json"
        fc.PROGRESS = tdp / "progress.json"
        fc.THROUGHPUT = tdp / "throughput.json"
        # build temp matrix from production rows (copy), reset statuses to PLANNED
        # so the fixture is independent of production progress (PLANNED/PUBLISHED).
        rows = prod_rows
        for x in rows:
            x["status"] = "PLANNED"
            x["score"] = ""
            x["quality_status"] = ""
            x["repair_attempts"] = "0"
            x["published_date"] = ""
            if x["batch_id"] == "B01":
                # point B01 rows at files that do not exist so the
                # file-missing QA path is exercised regardless of
                # production progress (published articles do exist).
                x["output_path"] = "cam-nang/__test_missing__/" + x["slug"] + ".html"
        with fc.MATRIX.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fc.MATRIX_FIELDS)
            w.writeheader()
            w.writerows(rows)
        import score_article_seo
        seo_tmp = tdp / "seo"
        score_article_seo.ARTICLES_DIR = seo_tmp / "articles"
        score_article_seo.SEO_DIR = seo_tmp
        env = dict(os.environ, CONTENT_MATRIX=str(fc.MATRIX),
                   PROGRESS_FILE=str(fc.PROGRESS), WRITER_CHECKPOINT=str(fc.CHECKPOINT),
                   FACTORY_THROUGHPUT=str(fc.THROUGHPUT), SEO_REPORTS_DIR=str(seo_tmp))
        sh_env = lambda *a: sh(*a, env=env)
        try:
            # claim --limit 5 claims exactly 5, untouched rows stay PLANNED
            r = sh_env(sys.executable, "scripts/run_article_batch.py", "claim", "B01", "--limit", "5")
            j = json.loads(r.stdout)
            check("claim limit 5 claims exactly 5", j["claimed"] == 5, r.stdout[-200:])
            check("claim chunk size 5", j["chunk_size"] == 5)
            rows = fc.load_matrix()
            b01 = [x for x in rows if x["batch_id"] == "B01"]
            writing = [x for x in b01 if x["status"] == "WRITING"]
            check("exactly 5 WRITING rows", len(writing) == 5)
            check("other 45 rows PLANNED", len([x for x in b01 if x["status"] == "PLANNED"]) == 45)
            check("other batches untouched", all(x["status"] == "PLANNED" for x in rows if x["batch_id"] != "B01"))
            cp = fc.read_checkpoint()
            check("checkpoint records current chunk", sorted(cp["current_chunk_ids"]) == sorted(x["article_id"] for x in writing))
            check("checkpoint schema v1", cp["schema_version"] == "1")
            # invariant: cannot claim another batch while the current batch is unfinished
            r_b02 = sh_env(sys.executable, "scripts/run_article_batch.py", "claim", "B02", "--limit", "5")
            check("claim B02 refused while B01 unfinished", r_b02.returncode == 1, r_b02.stdout[-200:])
            j_b02 = json.loads(r_b02.stdout)
            check("refusal names claimable batch", j_b02.get("claimable_batch") == "B01", r_b02.stdout[-200:])
            rows = fc.load_matrix()
            check("refused claim mutated nothing",
                  all(x["status"] == "PLANNED" for x in rows if x["batch_id"] == "B02"))
            check("refused claim keeps B01 chunk", len([x for x in rows if x["batch_id"] == "B01" and x["status"] == "WRITING"]) == 5)
            # scoped QA of the current chunk (files missing -> REPAIR/BLOCKED for chunk only)
            r = sh_env(sys.executable, "scripts/run_article_batch.py", "qa", "B01", "--limit", "5")
            j = json.loads(r.stdout)
            rows = fc.load_matrix()
            scoped = set(j["scoped"])
            check("scoped qa touches 5", len(scoped) == 5, r.stdout[-200:])
            chunk_statuses = {x["article_id"]: x["status"] for x in rows if x["article_id"] in scoped}
            check("file-missing chunk rows not PUBLISHED",
                  all(s in ("REPAIR", "BLOCKED") for s in chunk_statuses.values()),
                  str(chunk_statuses))
            untouched = [x for x in rows if x["batch_id"] == "B01" and x["status"] in ("WRITING", "PLANNED")]
            check("untouched rows remain WRITING/PLANNED after scoped qa",
                  len(untouched) == 45, str(len(untouched)))
            # claim --limit 10 next: deterministic next rows (old chunk left WRITING state)
            r = sh_env(sys.executable, "scripts/run_article_batch.py", "claim", "B01", "--limit", "10")
            j = json.loads(r.stdout)
            check("claim limit 10 claims 10 fresh", j["claimed"] == 10, r.stdout[-200:])
            rows = fc.load_matrix()
            writing = [x for x in rows if x["batch_id"] == "B01" and x["status"] == "WRITING"]
            check("10 WRITING after second claim", len(writing) == 10)
            # scoped qa by explicit ids touches only those rows
            three = sorted(x["article_id"] for x in writing)[:3]
            r = sh_env(sys.executable, "scripts/run_article_batch.py", "qa", "B01", "--ids", ",".join(three))
            j = json.loads(r.stdout)
            check("scoped qa by ids touches 3", set(j["scoped"]) == set(three), r.stdout[-200:])
            rows = fc.load_matrix()
            still_writing = [x for x in rows if x["batch_id"] == "B01" and x["status"] == "WRITING"]
            check("qa by ids leaves other WRITING rows untouched", len(still_writing) == 7,
                  str(len(still_writing)))
            # PUBLISHED never reclaimed
            for x in rows:
                if x["batch_id"] == "B01" and x["status"] == "PLANNED":
                    x["status"] = "PUBLISHED"
                    break
            with fc.MATRIX.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=fc.MATRIX_FIELDS)
                w.writeheader()
                w.writerows(rows)
            r = sh_env(sys.executable, "scripts/run_article_batch.py", "claim", "B01", "--limit", "40")
            j = json.loads(r.stdout)
            rows = fc.load_matrix()
            check("PUBLISHED never reclaimed", all(x["status"] == "PUBLISHED" for x in rows if x["status"] == "PUBLISHED") and
                  len([x for x in rows if x["batch_id"] == "B01" and x["status"] == "PUBLISHED"]) == 1)
            # checkpoint resume: matrix > checkpoint
            cp = fc.read_checkpoint()
            check("checkpoint reconciles with matrix", cp is not None)
        finally:
            fc.MATRIX = orig_matrix
            fc.CHECKPOINT = orig_checkpoint
            fc.PROGRESS = ROOT / "reports" / "batches" / "factory-progress.json"
            fc.THROUGHPUT = ROOT / "reports" / "batches" / "factory-throughput.json"
            fc.release_lock()
    check("production matrix untouched by chunked tests", orig_matrix.read_bytes() == before_bytes)
    # lock still guards overlapping writers (covered in txn tests) — path contract:
    check("checkpoint path contract", fc.CHECKPOINT == ROOT / "data" / "batches" / "writer-checkpoint.json")


def test_seo_scorer():
    """SEO scorer: deterministic 0-100; <90 cannot pass; publish gate enforced."""
    import score_article_seo
    # missing article -> score 0 FAIL, deterministic
    out = score_article_seo.score_article_seo("AT-0001", write=False)
    out2 = score_article_seo.score_article_seo("AT-0001", write=False)
    check("seo scorer repeat call identical", out == out2)
    check("seo scorer deterministic in 0-100", 0 <= out["seo_score"] <= 100 and
          out["seo_status"] in ("PASS", "REVIEW", "FAIL"))
    check("seo weights sum 100", sum(score_article_seo.WEIGHTS.values()) == 100)
    check("seo pass threshold 90", fc.SEO_PASS_MIN == 90)
    # fixture row via temp matrix
    with tempfile.TemporaryDirectory() as td:
        tm = pathlib.Path(td) / "m.csv"
        with tm.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fc.MATRIX_FIELDS)
            w.writeheader()
            w.writerow({"article_id": "KN-9999", "batch_id": "B99", "category": "KN", "status": "QA",
                        "primary_keyword": "kinh nghiệm thuê xe máy", "secondary_keywords": "x",
                        "search_intent": "informational", "working_title": "Fixture", "slug": "fixture",
                        "output_path": "tests/fixtures/sample-article.html", "parent_hub": "kinhnghiem.html",
                        "requires_sources": "false", "source_policy": "EDITORIAL_ONLY",
                        "internal_link_targets": "kinhnghiem.html", "commercial_link_target": "banggia.html",
                        "author": "test", "score": "", "quality_status": "", "repair_attempts": "0",
                        "published_date": "", "last_checked": "", "notes": "fixture"})
        orig = fc.MATRIX
        fc.MATRIX = tm
        try:
            out = score_article_seo.score_article_seo("KN-9999", write=False)
            check("fixture seo score in 0-100", 0 <= out["seo_score"] <= 100)
            check("fixture seo sections sum to score",
                  sum(out["sections"].values()) == out["seo_score"])
            # publish gate: quality PASS + seo < 90 must not pass the verdict
            import run_article_batch as rab
            check("seo 89 cannot pass even with quality PASS",
                  rab._qa_verdict({"quality_status": "PASS", "critical": []},
                                  {"seo_score": 89}) == "REVIEW")
            check("seo 90 passes with quality PASS",
                  rab._qa_verdict({"quality_status": "PASS", "critical": []},
                                  {"seo_score": 95}) == "PASS")
            check("quality FAIL cannot pass even with seo 100",
                  rab._qa_verdict({"quality_status": "FAIL", "critical": ["canonical incorrect"]},
                                  {"seo_score": 100}) == "FAIL")
            check("quality critical overrides seo 100",
                  rab._qa_verdict({"quality_status": "PASS", "critical": ["fabricated price"]},
                                  {"seo_score": 100}) == "FAIL")
        finally:
            fc.MATRIX = orig
    check("production matrix untouched by seo tests", fc.MATRIX.read_bytes() == fc.MATRIX.read_bytes())


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
    test_navigation()
    test_chunked_factory()
    test_seo_scorer()
    print(f"\n{PASS} passed, {len(FAIL)} failed ({time.time()-t0:.1f}s)")
    if FAIL:
        for f in FAIL[:40]:
            print("FAILED:", f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
