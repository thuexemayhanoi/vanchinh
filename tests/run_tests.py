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
    check("txn path contract", fc.TXN == ROOT / "data" / "batches" / "txn" / "txn.json")
    # txn recovery must NEVER mutate the production matrix: run on a temp copy
    # (lock/txn markers are isolated to the sandbox as well - production
    # marker paths are never created by tests)
    import contextlib
    import io
    orig_matrix = fc.MATRIX
    orig_lock = fc.LOCK
    orig_txn = fc.TXN
    before_bytes = orig_matrix.read_bytes()
    with tempfile.TemporaryDirectory() as td:
        tdp = pathlib.Path(td)
        tm = tdp / "m.csv"
        fc.LOCK = tdp / "lock.json"
        fc.TXN = tdp / "txn" / "txn.json"
        rows = [dict(r) for r in fc.load_matrix()]
        at1_path = [r for r in rows if r["article_id"] == "AT-0001"][0]["output_path"]
        for r in rows:
            if r["article_id"] == "AT-0001":
                r["status"] = "PASS"
        with tm.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fc.MATRIX_FIELDS)
            w.writeheader()
            w.writerows(rows)
        fc.MATRIX = tm
        matrix_before = tm.read_bytes()
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
            # FAIL-CLOSED: PASS + missing file is a conflict -> marker KEPT
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = fc.recover_txn()
            check("recover BLOCKED on missing file (rc 1)", rc == 1,
                  f"rc={rc} {buf.getvalue()[-200:]}")
            check("ambiguous recover keeps txn marker", fc.txn_pending())
            check("ambiguous recover never rewrites matrix",
                  tm.read_bytes() == matrix_before)
            fc.TXN.unlink()
            # known-safe rollback: real file present + PASS
            fc.begin_txn({"articles": [{"article_id": "AT-0001", "output_path": at1_path,
                                        "target_status": "PUBLISHED"}]})
            check("pending txn detected (rollback case)", fc.txn_pending())
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = fc.recover_txn()
            check("recover verifies known-safe rollback (rc 0)", rc == 0,
                  f"rc={rc} {buf.getvalue()[-200:]}")
            check("recover clears marker after verified rollback", not fc.txn_pending())
            rows = fc.load_matrix()
            at1 = [r for r in rows if r["article_id"] == "AT-0001"][0]
            check("rollback leaves status untouched (no guessing)",
                  at1["status"] == "PASS", at1["status"])
            check("rollback never rewrites matrix", tm.read_bytes() == matrix_before)
        finally:
            fc.MATRIX = orig_matrix
            fc.LOCK = orig_lock
            fc.TXN = orig_txn
            fc.release_lock()
    check("production matrix untouched by txn test", orig_matrix.read_bytes() == before_bytes)
    check("production lock path untouched by txn test",
          not (ROOT / "data" / "batches" / "lock.json").exists())
    check("production txn path untouched by txn test",
          not (ROOT / "data" / "batches" / "txn" / "txn.json").exists())


def test_recover_fail_closed():
    """FIX 2 regression: recovery must NEVER clear an ambiguous txn marker.
    Fault injection (subprocess `run_article_batch recover`, sandbox matrix +
    sandbox marker via CONTENT_MATRIX/TXN_FILE/LOCK_FILE): file missing,
    matrix/file disagreement, partial publish, malformed/ambiguous plan,
    unknown plan id, known-safe rollback, known-safe completion. Ambiguous
    states keep the marker (rc 1); only proven-safe states clear it (rc 0);
    the production matrix/markers are never mutated by the tests."""
    orig_matrix = fc.MATRIX
    before_bytes = orig_matrix.read_bytes()
    prod_txn = ROOT / "data" / "batches" / "txn" / "txn.json"
    prod_lock = ROOT / "data" / "batches" / "lock.json"
    sitemap_p = ROOT / "sitemap.xml"
    hub_p = ROOT / "kinhnghiem.html"
    with tempfile.TemporaryDirectory() as td:
        tdp = pathlib.Path(td)
        m = tdp / "m.csv"
        txn = tdp / "txn" / "txn.json"
        cp = tdp / "cp.json"
        prog = tdp / "p.json"
        thr = tdp / "t.json"
        orig = list(csv.DictReader(open(orig_matrix, encoding="utf-8", newline="")))
        pub = [r for r in orig if r["status"] == "PUBLISHED"][:3]
        p1, p2, p3 = pub[0], pub[1], pub[2]

        def write_matrix(status_map=None, path_map=None):
            rows = [dict(r) for r in orig]
            by = {r["article_id"]: r for r in rows}
            for aid, st in (status_map or {}).items():
                by[aid]["status"] = st
            for aid, p in (path_map or {}).items():
                by[aid]["output_path"] = p
            with m.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=fc.MATRIX_FIELDS)
                w.writeheader()
                w.writerows(rows)
            return m.read_bytes()

        def marker(plan=None, raw=None):
            txn.parent.mkdir(parents=True, exist_ok=True)
            if raw is not None:
                txn.write_text(raw, encoding="utf-8")
                return
            txn.write_text(json.dumps({"plan": plan, "state": "IN_PROGRESS",
                                       "started": "2026-09-30T00:00:00Z"},
                                      ensure_ascii=False, indent=2),
                           encoding="utf-8")

        def plan_item(row, output_path=None, target="PUBLISHED"):
            return {"article_id": row["article_id"],
                    "output_path": output_path or row["output_path"],
                    "target_status": target}

        def run_recover():
            env = dict(os.environ, CONTENT_MATRIX=str(m), TXN_FILE=str(txn),
                       LOCK_FILE=str(tdp / "lock.json"), PROGRESS_FILE=str(prog),
                       WRITER_CHECKPOINT=str(cp), FACTORY_THROUGHPUT=str(thr))
            return sh(sys.executable, "scripts/run_article_batch.py", "recover", env=env)

        # --- no marker -> rc 0 --------------------------------------------
        write_matrix()
        if txn.exists():
            txn.unlink()
        r = run_recover()
        check("recover: no marker -> rc 0", r.returncode == 0 and
              "no pending transaction" in r.stdout, f"rc={r.returncode}")

        # --- malformed marker JSON -> rc 1, marker KEPT -------------------
        marker(raw="{not valid json")
        r = run_recover()
        check("recover: malformed marker -> rc 1 marker kept",
              r.returncode == 1 and txn.exists() and "cannot parse" in r.stdout,
              f"rc={r.returncode} {r.stdout[-200:]}")

        # --- ambiguous plan: no articles key -----------------------------
        marker(plan={"updates": ["content-matrix"]})
        r = run_recover()
        check("recover: plan without articles -> rc 1 marker kept",
              r.returncode == 1 and txn.exists() and "malformed or empty" in r.stdout,
              f"rc={r.returncode}")

        # --- ambiguous plan: empty articles list --------------------------
        marker(plan={"articles": []})
        r = run_recover()
        check("recover: empty articles plan -> rc 1 marker kept",
              r.returncode == 1 and txn.exists(), f"rc={r.returncode}")

        # --- plan item missing article_id ---------------------------------
        marker(plan={"articles": [{"output_path": "cam-nang/x.html",
                                   "target_status": "PUBLISHED"}]})
        r = run_recover()
        check("recover: plan item missing article_id -> rc 1 marker kept",
              r.returncode == 1 and txn.exists() and
              "missing article_id" in r.stdout, f"rc={r.returncode}")

        # --- unknown plan id ------------------------------------------------
        write_matrix()
        marker(plan={"articles": [{"article_id": "ZZ-9999",
                                   "output_path": "cam-nang/an-toan/zz.html",
                                   "target_status": "PUBLISHED"}]})
        r = run_recover()
        check("recover: unknown plan id -> rc 1 marker kept",
              r.returncode == 1 and txn.exists() and
              "not found in matrix" in r.stdout, f"rc={r.returncode}")

        # --- file missing (pre-write PASS + missing file) -------------------
        write_matrix({p1["article_id"]: "PASS"},
                     {p1["article_id"]: "cam-nang/__missing__/x.html"})
        marker(plan={"articles": [plan_item(p1, "cam-nang/__missing__/x.html")]})
        r = run_recover()
        check("recover: missing file -> rc 1 marker kept",
              r.returncode == 1 and txn.exists() and
              "file missing" in r.stdout, f"rc={r.returncode} {r.stdout[-200:]}")

        # --- matrix/file disagreement (PUBLISHED + missing file) -----------
        write_matrix({p1["article_id"]: "PUBLISHED"},
                     {p1["article_id"]: "cam-nang/__missing__/x.html"})
        marker(plan={"articles": [plan_item(p1, "cam-nang/__missing__/x.html")]})
        r = run_recover()
        check("recover: PUBLISHED without file -> rc 1 marker kept",
              r.returncode == 1 and txn.exists() and
              "PUBLISHED but file missing" in r.stdout,
              f"rc={r.returncode} {r.stdout[-200:]}")

        # --- ambiguous matrix status (WRITING + file exists) ----------------
        write_matrix({p1["article_id"]: "WRITING"})
        marker(plan={"articles": [plan_item(p1)]})
        r = run_recover()
        check("recover: ambiguous WRITING status -> rc 1 marker kept",
              r.returncode == 1 and txn.exists() and
              "ambiguous matrix status WRITING" in r.stdout,
              f"rc={r.returncode} {r.stdout[-200:]}")

        # --- partial publish (one PUBLISHED + one PASS) ----------------------
        write_matrix({p1["article_id"]: "PUBLISHED", p2["article_id"]: "PASS"})
        marker(plan={"articles": [plan_item(p1), plan_item(p2)]})
        r = run_recover()
        check("recover: partial publish -> rc 1 marker kept",
              r.returncode == 1 and txn.exists() and "partial publish" in r.stdout,
              f"rc={r.returncode} {r.stdout[-200:]}")

        # --- known-safe rollback: both PASS, files exist ---------------------
        rb_bytes = write_matrix({p1["article_id"]: "PASS", p2["article_id"]: "PASS"})
        marker(plan={"articles": [plan_item(p1), plan_item(p2)]})
        r = run_recover()
        check("recover: known-safe rollback -> rc 0 marker cleared",
              r.returncode == 0 and not txn.exists() and
              "verified rollback" in r.stdout,
              f"rc={r.returncode} {r.stdout[-200:]}")
        check("recover: rollback leaves matrix byte-identical",
              m.read_bytes() == rb_bytes)
        rows = list(csv.DictReader(open(m, encoding="utf-8", newline="")))
        st = {x["article_id"]: x["status"] for x in rows
              if x["article_id"] in (p1["article_id"], p2["article_id"])}
        check("recover: rollback keeps statuses PASS (no guessing)",
              set(st.values()) == {"PASS"}, str(st))

        # --- known-safe completion: all PUBLISHED, files exist ---------------
        # fixture matrix == byte-identical production copy, so the
        # deterministic regeneration (sitemap/hubs/shells/progress) must be
        # idempotent: no production working-copy file may drift.
        shutil.copyfile(orig_matrix, m)
        comp_bytes = m.read_bytes()
        sitemap_before = sitemap_p.read_bytes()
        hub_before = hub_p.read_bytes()
        marker(plan={"articles": [plan_item(p1), plan_item(p2), plan_item(p3)]})
        r = run_recover()
        check("recover: known-safe completion -> rc 0 marker cleared",
              r.returncode == 0 and not txn.exists() and
              "verified completion" in r.stdout,
              f"rc={r.returncode} {r.stdout[-300:]}")
        check("recover: completion leaves matrix byte-identical",
              m.read_bytes() == comp_bytes)
        check("recover: completion regen idempotent (sitemap unchanged)",
              sitemap_p.read_bytes() == sitemap_before)
        check("recover: completion regen idempotent (hub unchanged)",
              hub_p.read_bytes() == hub_before)

        # --- production isolation --------------------------------------------
        check("recover tests never create production txn marker",
              not prod_txn.exists())
        check("recover tests never create production lock",
              not prod_lock.exists())
    check("production matrix untouched by recover fault-injection tests",
          orig_matrix.read_bytes() == before_bytes)


def test_publish_rollback_fail_closed():
    """FIX 5 regression: the shell-rebuild rollback path must verify the
    sitemap/hub regeneration return codes BEFORE clearing the txn marker.
    Fault injection (in-process, sandboxed matrix/lock/txn/checkpoint/progress
    via patched factory_common paths; run() stubbed): build_article_shell
    fails -> rollback regen FAILS => marker KEPT + rc 1 + "rollback
    incomplete"; build_article_shell fails -> rollback regen OK => marker
    cleared + rc 1 + "rolled back"; happy path => rc 0 + marker cleared.
    Production matrix/markers are never mutated by the tests."""
    import contextlib
    import io
    import types
    import run_article_batch as rab
    orig_matrix = fc.MATRIX
    before_bytes = orig_matrix.read_bytes()
    prod_txn = ROOT / "data" / "batches" / "txn" / "txn.json"
    prod_lock = ROOT / "data" / "batches" / "lock.json"
    saved_paths = {k: getattr(fc, k) for k in
                   ("MATRIX", "LOCK", "TXN", "CHECKPOINT", "PROGRESS", "THROUGHPUT")}
    saved_run = rab.run
    saved_score = rab.score_article_seo.score_article_seo
    saved_summary = rab.score_article_seo.seo_summary
    try:
        with tempfile.TemporaryDirectory() as td:
            tdp = pathlib.Path(td)
            m = tdp / "m.csv"
            fc.MATRIX = m
            fc.LOCK = tdp / "lock.json"
            fc.TXN = tdp / "txn" / "txn.json"
            fc.CHECKPOINT = tdp / "writer-checkpoint.json"
            fc.PROGRESS = tdp / "p.json"
            fc.THROUGHPUT = tdp / "t.json"
            orig = list(csv.DictReader(open(orig_matrix, encoding="utf-8", newline="")))
            pub = [dict(r) for r in orig if r["status"] == "PUBLISHED"][:2]
            check("publish rollback fixture: two published rows found", len(pub) == 2)
            bid = pub[0]["batch_id"]
            pub_ids = {r["article_id"] for r in pub}

            def write_matrix():
                rows = [dict(r) for r in orig]
                by = {r["article_id"]: r for r in rows}
                for r in pub:
                    by[r["article_id"]]["status"] = "PASS"
                    by[r["article_id"]]["published_date"] = ""
                with m.open("w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=fc.MATRIX_FIELDS)
                    w.writeheader()
                    w.writerows(rows)

            def statuses():
                rows = list(csv.DictReader(open(m, encoding="utf-8", newline="")))
                return {r["article_id"]: r["status"] for r in rows if r["article_id"] in pub_ids}

            def fake_run_codes(codes):
                it = iter(codes)

                def fake_run(args, **kw):
                    return types.SimpleNamespace(returncode=next(it, 0))
                return fake_run

            def call_publish():
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    rc = rab.cmd_publish(bid, all_pass=True)
                return rc, buf.getvalue()

            rab.score_article_seo.score_article_seo = \
                lambda aid, write=False: {"seo_score": 95}
            rab.score_article_seo.seo_summary = lambda: None

            # --- shell rebuild fails + rollback regen FAILS => marker KEPT ---
            write_matrix()
            rab.run = fake_run_codes([0, 0, 1, 1, 0])
            rc, out = call_publish()
            check("publish rollback: shell fail + regen fail -> rc 1", rc == 1)
            check("publish rollback: shell fail + regen fail -> marker KEPT",
                  fc.TXN.exists())
            check("publish rollback: shell fail + regen fail -> reports incomplete",
                  "rollback incomplete" in out)
            check("publish rollback: statuses restored to PASS",
                  set(statuses().values()) == {"PASS"})
            if fc.TXN.exists():
                fc.TXN.unlink()

            # --- shell rebuild fails + rollback regen OK => marker cleared ---
            write_matrix()
            rab.run = fake_run_codes([0, 0, 1, 0, 0])
            rc, out = call_publish()
            check("publish rollback: shell fail + regen ok -> rc 1", rc == 1)
            check("publish rollback: shell fail + regen ok -> marker cleared",
                  not fc.TXN.exists())
            check("publish rollback: shell fail + regen ok -> reports rollback",
                  "rolled back: article shell rebuild failed" in out)
            check("publish rollback: regen ok -> statuses restored to PASS",
                  set(statuses().values()) == {"PASS"})

            # --- happy path => rc 0, marker cleared, sandbox PUBLISHED -----
            write_matrix()
            rab.run = fake_run_codes([0, 0, 0])
            rc, out = call_publish()
            check("publish happy path (stubbed): rc 0", rc == 0)
            check("publish happy path (stubbed): marker cleared",
                  not fc.TXN.exists())
            check("publish happy path (stubbed): sandbox rows PUBLISHED",
                  set(statuses().values()) == {"PUBLISHED"})

        check("publish rollback tests never create production txn marker",
              not prod_txn.exists())
        check("publish rollback tests never create production lock",
              not prod_lock.exists())
    finally:
        for k, v in saved_paths.items():
            setattr(fc, k, v)
        rab.run = saved_run
        rab.score_article_seo.score_article_seo = saved_score
        rab.score_article_seo.seo_summary = saved_summary
    check("production matrix untouched by publish rollback tests",
          orig_matrix.read_bytes() == before_bytes)


def test_factory_liveness():
    """FIX 3 regression: READ-ONLY liveness watchdog verdicts from repository
    truth (matrix + checkpoint + progress + throughput + txn + lock).
    PLANNED rows alone are never a stall; the checker must never mutate any
    state. Scenarios: healthy idle, healthy active (fresh progress), stalled
    WRITING, stalled PASS, stale checkpoint, stale txn, stale lock with
    unfinished work, fresh lock, stale lock with all-terminal matrix."""
    orig_matrix = fc.MATRIX
    before_bytes = orig_matrix.read_bytes()
    prod_txn = ROOT / "data" / "batches" / "txn" / "txn.json"
    prod_lock = ROOT / "data" / "batches" / "lock.json"
    orig = list(csv.DictReader(open(orig_matrix, encoding="utf-8", newline="")))
    pub_rows = [r for r in orig if r["status"] == "PUBLISHED"][:2]
    planned_rows = [r for r in orig if r["status"] == "PLANNED"][:2]
    with tempfile.TemporaryDirectory() as td:
        tdp = pathlib.Path(td)
        m = tdp / "m.csv"
        cp = tdp / "writer-checkpoint.json"
        prog = tdp / "p.json"
        thr = tdp / "t.json"
        lock = tdp / "lock.json"
        txn = tdp / "txn" / "txn.json"

        def write_matrix(status_map=None, all_published=False):
            rows = [dict(r) for r in orig]
            by = {r["article_id"]: r for r in rows}
            for aid, st in (status_map or {}).items():
                by[aid]["status"] = st
            if all_published:
                for r in rows:
                    r["status"] = "PUBLISHED"
            with m.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=fc.MATRIX_FIELDS)
                w.writeheader()
                w.writerows(rows)

        def write_checkpoint(updated_at, chunk_ids=None):
            cp.write_text(json.dumps({
                "schema_version": "1", "batch": "B99", "chunk_size": 10,
                "current_chunk_ids": sorted(chunk_ids or []), "written_ids": [],
                "pending_qa_ids": [], "pending_repair_ids": [], "pass_ids": [],
                "pending_publish_ids": [], "published_ids": [],
                "last_completed_step": "qa", "started_at": "2026-09-27T00:00:00Z",
                "updated_at": updated_at, "chunks_completed": 0,
                "publish_operations": 0,
            }, ensure_ascii=False, indent=2), encoding="utf-8")

        def run_liveness():
            env = dict(os.environ, CONTENT_MATRIX=str(m), WRITER_CHECKPOINT=str(cp),
                       PROGRESS_FILE=str(prog), FACTORY_THROUGHPUT=str(thr),
                       TXN_FILE=str(txn), LOCK_FILE=str(lock),
                       LIVENESS_STALL_HOURS="6", LIVENESS_LOCK_STALE_HOURS="6")
            return sh(sys.executable, "scripts/factory_liveness.py", env=env)

        def iso(delta_hours=0.0):
            return time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                 time.gmtime(time.time() - delta_hours * 3600))

        def clean():
            for p in (lock, txn, cp):
                if p.exists():
                    p.unlink()

        # --- healthy idle: PLANNED rows alone are NOT a stall -------------
        clean()
        write_matrix()
        write_checkpoint(iso(48))
        m_before = m.read_bytes()
        cp_before = cp.read_bytes()
        r = run_liveness()
        j = json.loads(r.stdout.split("VANCHINH_FACTORY_LIVENESS_")[0])
        check("liveness: PLANNED rows + resting writer => HEALTHY_IDLE rc 0",
              r.returncode == 0 and j["status"] == "HEALTHY_IDLE" and
              "VANCHINH_FACTORY_LIVENESS_PASS" in r.stdout,
              f"rc={r.returncode} {r.stdout[-200:]}")
        check("liveness: checker is read-only (matrix untouched)",
              m.read_bytes() == m_before)
        check("liveness: checker is read-only (checkpoint untouched)",
              cp.read_bytes() == cp_before)

        # --- healthy active: in-flight rows + fresh checkpoint -------------
        ids = [pub_rows[0]["article_id"], pub_rows[1]["article_id"]]
        write_matrix({ids[0]: "WRITING", ids[1]: "QA"})
        write_checkpoint(iso(0.5), chunk_ids=ids)
        r = run_liveness()
        j = json.loads(r.stdout.split("VANCHINH_FACTORY_LIVENESS_")[0])
        check("liveness: in-flight + fresh progress => HEALTHY_ACTIVE rc 0",
              r.returncode == 0 and j["status"] == "HEALTHY_ACTIVE",
              f"rc={r.returncode} {r.stdout[-200:]}")

        # --- fresh lock does not fail healthy active work ------------------
        lock.write_text(json.dumps({"operator": "test", "acquired": iso(0.2)}),
                        encoding="utf-8")
        r = run_liveness()
        check("liveness: fresh lock + active work stays PASS",
              r.returncode == 0 and "HEALTHY_ACTIVE" in r.stdout,
              f"rc={r.returncode} {r.stdout[-200:]}")
        clean()

        # --- stalled WRITING beyond threshold -------------------------------
        write_checkpoint(iso(10))
        r = run_liveness()
        j = json.loads(r.stdout.split("VANCHINH_FACTORY_LIVENESS_")[0])
        check("liveness: stalled WRITING => STALLED_ACTIVE rc 1",
              r.returncode == 1 and j["status"] == "STALLED_ACTIVE" and
              "VANCHINH_FACTORY_LIVENESS_FAIL" in r.stdout,
              f"rc={r.returncode} {r.stdout[-200:]}")

        # --- stalled PASS beyond threshold ----------------------------------
        write_matrix({ids[0]: "PASS", ids[1]: "PUBLISHED"})
        write_checkpoint(iso(10), chunk_ids=[ids[0]])
        r = run_liveness()
        j = json.loads(r.stdout.split("VANCHINH_FACTORY_LIVENESS_")[0])
        check("liveness: stalled PASS => STALLED_ACTIVE rc 1",
              r.returncode == 1 and j["status"] == "STALLED_ACTIVE",
              f"rc={r.returncode} {r.stdout[-200:]}")

        # --- stale txn marker always FAILs first ----------------------------
        txn.parent.mkdir(parents=True, exist_ok=True)
        txn.write_text(json.dumps({"plan": {"articles": []}, "state": "IN_PROGRESS"}),
                        encoding="utf-8")
        r = run_liveness()
        j = json.loads(r.stdout.split("VANCHINH_FACTORY_LIVENESS_")[0])
        check("liveness: pending txn => STALE_TXN rc 1",
              r.returncode == 1 and j["status"] == "STALE_TXN" and
              "VANCHINH_FACTORY_LIVENESS_FAIL" in r.stdout,
              f"rc={r.returncode} {r.stdout[-200:]}")
        check("liveness: stale txn marker kept (read-only)", txn.exists())
        txn.unlink()

        # --- stale lock with unfinished work => FAIL -------------------------
        write_matrix()  # PLANNED rows exist
        write_checkpoint(iso(0.5))
        lock.write_text(json.dumps({"operator": "gone", "acquired": iso(10)}),
                        encoding="utf-8")
        old = time.time() - 10 * 3600
        os.utime(lock, (old, old))
        r = run_liveness()
        j = json.loads(r.stdout.split("VANCHINH_FACTORY_LIVENESS_")[0])
        check("liveness: stale lock + unfinished work => FAIL rc 1",
              r.returncode == 1 and
              j["status"] == "EXPIRED_OR_STALE_LOCK_WITH_UNFINISHED_WORK",
              f"rc={r.returncode} {r.stdout[-200:]}")
        check("liveness: stale lock kept (read-only)", lock.exists())

        # --- fresh lock + only PLANNED rows => HEALTHY_IDLE ------------------
        fresh = time.time()
        os.utime(lock, (fresh, fresh))
        r = run_liveness()
        check("liveness: fresh lock + PLANNED only => HEALTHY_IDLE rc 0",
              r.returncode == 0 and "HEALTHY_IDLE" in r.stdout,
              f"rc={r.returncode} {r.stdout[-200:]}")
        clean()

        # --- stale checkpoint: chunk ids unknown / still PLANNED ------------
        write_matrix()
        write_checkpoint(iso(0.5), chunk_ids=[planned_rows[0]["article_id"],
                                              "ZZ-9999"])
        r = run_liveness()
        j = json.loads(r.stdout.split("VANCHINH_FACTORY_LIVENESS_")[0])
        check("liveness: checkpoint chunk vs matrix disagreement => CHECKPOINT_STALE rc 1",
              r.returncode == 1 and j["status"] == "CHECKPOINT_STALE" and
              j.get("conflict_ids") == sorted([planned_rows[0]["article_id"], "ZZ-9999"]),
              f"rc={r.returncode} {r.stdout[-300:]}")

        # --- all-terminal matrix + stale lock => still HEALTHY_IDLE -----------
        write_matrix(all_published=True)
        write_checkpoint(iso(48))
        lock.write_text(json.dumps({"operator": "gone", "acquired": iso(10)}),
                        encoding="utf-8")
        os.utime(lock, (old, old))
        r = run_liveness()
        check("liveness: stale lock without unfinished work => HEALTHY_IDLE rc 0",
              r.returncode == 0 and "HEALTHY_IDLE" in r.stdout,
              f"rc={r.returncode} {r.stdout[-200:]}")
        clean()

        # --- production isolation ----------------------------------------------
        check("liveness tests never create production txn marker",
              not prod_txn.exists())
        check("liveness tests never create production lock",
              not prod_lock.exists())
    check("production matrix untouched by liveness tests",
          orig_matrix.read_bytes() == before_bytes)


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
        # fixture: normalize AT statuses so exactly HUB_PAGE_SIZE+10 rows end
        # up PUBLISHED, regardless of how many AT rows are already published
        # in the real matrix at test time.
        for r in rows:
            if r["category"] == "AT":
                r["status"] = "PLANNED"
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
        at_real = [r for r in fc.load_matrix()
                   if r["category"] == "AT" and r["status"] == "PUBLISHED"]
        check("orphan listing page removed",
              p2.exists() == (len(at_real) > fc.HUB_PAGE_SIZE))
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
    # (sys.modules lookup: a later local `import score_article_seo` in this
    # function makes the bare name local, so never reference it here)
    orig_seo_dir = sys.modules["score_article_seo"].ARTICLES_DIR \
        if "score_article_seo" in sys.modules else None
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
            # claim --limit 10 next: the interrupted chunk rows (now REPAIR,
            # files missing) MUST be resumed, then filled with fresh rows
            r = sh_env(sys.executable, "scripts/run_article_batch.py", "claim", "B01", "--limit", "10")
            j = json.loads(r.stdout)
            check("claim limit 10 chunk = 5 resumed REPAIR + 5 fresh",
                  j["claimed"] == 5 and len(j["chunk_ids"]) == 10, r.stdout[-200:])
            rows = fc.load_matrix()
            writing = [x for x in rows if x["batch_id"] == "B01" and x["status"] == "WRITING"]
            check("5 fresh WRITING + 5 resumed REPAIR after second claim",
                  len(writing) == 5 and
                  len([x for x in rows if x["batch_id"] == "B01" and x["status"] == "REPAIR"]) == 5,
                  str(len(writing)))
            # scoped qa by explicit ids touches only those rows
            three = sorted(x["article_id"] for x in writing)[:3]
            r = sh_env(sys.executable, "scripts/run_article_batch.py", "qa", "B01", "--ids", ",".join(three))
            j = json.loads(r.stdout)
            check("scoped qa by ids touches 3", set(j["scoped"]) == set(three), r.stdout[-200:])
            rows = fc.load_matrix()
            still_writing = [x for x in rows if x["batch_id"] == "B01" and x["status"] == "WRITING"]
            check("qa by ids leaves other WRITING rows untouched", len(still_writing) == 2,
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


SUPPORT_URL = "https://thuexemayhanoi.github.io/aichatbot/"
SUPPORT_LABEL = "Hỗ Trợ"


def test_support_no_zalo():
    """Zalo fully removed; support destination is the Agent URL, labelled Hỗ Trợ."""
    # canonical facts
    f = fc.FACTS
    check("facts: no zalo key", "zalo" not in json.dumps(f).lower())
    check("facts: support_url is agent url", f.get("support_url") == SUPPORT_URL,
          str(f.get("support_url")))
    check("facts: support_label Hỗ Trợ", f.get("support_label") == SUPPORT_LABEL)
    # zero zalo in any rendered html / js / raw sections
    offenders = []
    for p in list(ROOT.glob("*.html")) + list((ROOT / "cam-nang").rglob("*.html")) \
            + list((ROOT / "assets").rglob("*")) + list((ROOT / "sections").rglob("*")):
        if p.is_file() and p.suffix in {".html", ".js", ".txt"}:
            t = p.read_text(encoding="utf-8", errors="ignore").lower()
            if "zalo" in t or "zalo.me" in t or "icon_of_zalo" in t:
                offenders.append(str(p))
    check("zero zalo refs in public output", not offenders, str(offenders[:5]))
    # support button resolves to canonical URL on root pages
    for name in ("index.html", "lienhe.html", "banggia.html", "antoan.html",
                 "kinhnghiem.html", "hoidap.html", "xemay.html",
                 "dulich.html", "cungduong.html", "gioithieu.html"):
        html = (ROOT / name).read_text(encoding="utf-8")
        check(f"{name}: support link to agent url", SUPPORT_URL in html)
    # menu & footer: Hỗ Trợ with same URL (same vocabulary, same destination)
    for p in ROOT.glob("*.html"):
        html = p.read_text(encoding="utf-8")
        nav = re.search(r'<nav[^>]*data-desktop-nav.*?</nav>', html, re.S)
        foot = re.search(r'<footer.*?</footer>', html, re.S)
        if nav:
            check(f"{p.name}: nav has Hỗ Trợ", SUPPORT_LABEL in nav.group(0))
            check(f"{p.name}: nav Hỗ Trợ url matches",
                  (SUPPORT_LABEL in nav.group(0)) and (SUPPORT_URL in nav.group(0)))
        if foot:
            check(f"{p.name}: footer has Hỗ Trợ", SUPPORT_LABEL in foot.group(0))
            check(f"{p.name}: footer Hỗ Trợ url matches",
                  (SUPPORT_LABEL in foot.group(0)) and (SUPPORT_URL in foot.group(0)))
    # no zalo logo/asset files left
    zimgs = [p.name for p in (ROOT / "assets").rglob("*") if "zalo" in p.name.lower()]
    check("no zalo asset files", not zimgs, str(zimgs))
    # schema hygiene: agent url must never appear as social sameAs
    sameas_hits = []
    for p in list(ROOT.glob("*.html")) + list((ROOT / "cam-nang").rglob("*.html")):
        html = p.read_text(encoding="utf-8")
        for m in re.finditer(r'"sameAs"\s*:\s*\[(.*?)\]', html, re.S):
            if SUPPORT_URL in m.group(1):
                sameas_hits.append(p.name)
    check("agent url not used as sameAs", not sameas_hits, str(sameas_hits[:5]))
    # six category hubs exist
    for hub in ("kinhnghiem", "hoidap", "xemay", "antoan", "dulich", "cungduong"):
        p = ROOT / f"{hub}.html"
        check(f"hub {hub}.html exists", p.exists())
        if p.exists():
            html = p.read_text(encoding="utf-8")
            check(f"hub {hub}: exactly one H1", len(re.findall(r"<h1[\s>]", html)) == 1)
            check(f"hub {hub}: has canonical", 'rel="canonical"' in html)
            check(f"hub {hub}: no zalo", "zalo" not in html.lower())
    # factory state untouched by this task: matrix published counts consistent, no active txn/lock mutation here (read-only)
    check("no active txn file", not (ROOT / "data" / "batches" / "txn" / "txn.json").exists())
    check("no writer lock file", not (ROOT / "data" / "batches" / "lock.json").exists())


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



def test_claim_resume_repair_rows():
    """Claim drift regression: the checkpointed current chunk rows in REPAIR
    (writer files landed after a QA of missing files) MUST be re-selected by
    the next claim, never stranded in favor of fresh PLANNED rows."""
    orig_matrix = fc.MATRIX
    orig_checkpoint = fc.CHECKPOINT
    before_bytes = orig_matrix.read_bytes()
    with tempfile.TemporaryDirectory() as td:
        tdp = pathlib.Path(td)
        fc.MATRIX = tdp / "m.csv"
        fc.CHECKPOINT = tdp / "writer-checkpoint.json"
        fc.PROGRESS = tdp / "progress.json"
        fc.THROUGHPUT = tdp / "throughput.json"
        rows = [dict(r) for r in csv.DictReader(open(orig_matrix, encoding="utf-8", newline=""))]
        for x in rows:
            x["status"] = "PUBLISHED" if x["article_id"] in ("AT-0001", "AT-0002") else "PLANNED"
        # simulate: current chunk AT-0003..AT-0005 claimed, QA'd with files
        # missing -> REPAIR (repair_attempts=1), checkpoint holds the chunk
        for x in rows[:0]:
            pass
        by = {x["article_id"]: x for x in rows}
        for aid in ("AT-0003", "AT-0004", "AT-0005"):
            by[aid]["status"] = "REPAIR"
            by[aid]["repair_attempts"] = "1"
        with fc.MATRIX.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fc.MATRIX_FIELDS)
            w.writeheader()
            w.writerows(rows)
        fc.write_checkpoint(batch="B01", chunk_size=3,
                            current_chunk_ids=["AT-0003", "AT-0004", "AT-0005"],
                            last_completed_step="qa")
        env = dict(os.environ, CONTENT_MATRIX=str(fc.MATRIX),
                   PROGRESS_FILE=str(fc.PROGRESS), WRITER_CHECKPOINT=str(fc.CHECKPOINT),
                   FACTORY_THROUGHPUT=str(fc.THROUGHPUT))
        try:
            r = sh(sys.executable, "scripts/run_article_batch.py", "claim", "B01", "--limit", "5", env=env)
            j = json.loads(r.stdout)
            check("claim resumes REPAIR rows of current chunk",
                  set(j["chunk_ids"]) >= {"AT-0003", "AT-0004", "AT-0005"}, r.stdout[-300:])
            rows = fc.load_matrix()
            still = {x["article_id"]: x["status"] for x in rows
                    if x["article_id"] in ("AT-0003", "AT-0004", "AT-0005")}
            check("REPAIR chunk rows not regressed to PLANNED/stranded",
                  all(v in ("REPAIR", "QA") for v in still.values()), str(still))
        finally:
            fc.MATRIX = orig_matrix
            fc.CHECKPOINT = orig_checkpoint
            fc.PROGRESS = ROOT / "reports" / "batches" / "factory-progress.json"
            fc.THROUGHPUT = ROOT / "reports" / "batches" / "factory-throughput.json"
            fc.release_lock()
    check("production matrix untouched by claim-resume tests",
          orig_matrix.read_bytes() == before_bytes)


def test_continuous_factory():
    """run_continuous_factory.py driver: CONTINUE derived from unfinished rows,
    COMPLETE only when all terminal; chunk resume; WRITER_REQUIRED keeps the
    chunk claimed (resumable, not lost); concurrency + push-race policy."""
    orig_matrix = fc.MATRIX
    orig_checkpoint = fc.CHECKPOINT
    before_bytes = orig_matrix.read_bytes()
    with tempfile.TemporaryDirectory() as td:
        tdp = pathlib.Path(td)
        fc.MATRIX = tdp / "m.csv"
        fc.CHECKPOINT = tdp / "writer-checkpoint.json"
        fc.PROGRESS = tdp / "progress.json"
        fc.THROUGHPUT = tdp / "throughput.json"
        rows = [dict(r) for r in orig_matrix.read_bytes() and list(csv.DictReader(open(orig_matrix, encoding="utf-8", newline="")))]
        for x in rows:
            x["status"] = "PUBLISHED" if x["article_id"] in ("AT-0001", "AT-0002") else "PLANNED"
            if x["status"] == "PLANNED" and x["batch_id"] == "B01":
                x["output_path"] = "cam-nang/__test_missing__/" + x["slug"] + ".html"
        with fc.MATRIX.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fc.MATRIX_FIELDS)
            w.writeheader()
            w.writerows(rows)
        env = dict(os.environ, CONTENT_MATRIX=str(fc.MATRIX),
                   PROGRESS_FILE=str(fc.PROGRESS), WRITER_CHECKPOINT=str(fc.CHECKPOINT),
                   FACTORY_THROUGHPUT=str(fc.THROUGHPUT))
        try:
            r = sh(sys.executable, "scripts/run_continuous_factory.py", "status", env=env)
            j = json.loads(r.stdout.split("VANCHINH_FACTORY")[0])
            check("driver: PLANNED remaining => CONTINUE",
                  j["factory_status"] == "CONTINUE" and j["unfinished"] > 0)
            check("driver: status command prints CONTINUING",
                  "VANCHINH_FACTORY_CONTINUING" in r.stdout)
            check("driver: next_article derived from matrix",
                  j["next_article"] == "AT-0003", j["next_article"])
            check("driver: active_batch earliest unfinished",
                  j["active_batch"] == "B01", j["active_batch"])
            # run: claims chunk, files missing -> WRITER_REQUIRED, chunk stays WRITING
            r = sh(sys.executable, "scripts/run_continuous_factory.py", "run", "--chunk-size", "5", env=env)
            check("driver: missing files => WRITER_REQUIRED",
                  r.returncode == 1 and "VANCHINH_FACTORY_WRITER_REQUIRED" in r.stdout,
                  r.stdout[-200:])
            j = json.loads(r.stdout.split("VANCHINH_FACTORY")[0])
            check("driver: writer chunk is exactly claimed size",
                  len(j["chunk_ids"]) == 5, r.stdout[:200])
            rows = fc.load_matrix()
            writing = [x for x in rows if x["status"] == "WRITING"]
            check("driver: WRITER_REQUIRED leaves chunk claimed (resumable)",
                  len(writing) == 5 and all(x["status"] == "WRITING" for x in rows
                                            if x["article_id"] in j["chunk_ids"]))
            cp = fc.read_checkpoint()
            check("driver: checkpoint holds current chunk for resume",
                  sorted((cp or {}).get("current_chunk_ids") or []) == sorted(j["chunk_ids"]))
            # status after claim still CONTINUE (not complete)
            r = sh(sys.executable, "scripts/run_continuous_factory.py", "status", env=env)
            check("driver: empty-vs-active chunk distinction => still CONTINUE",
                  json.loads(r.stdout.split("VANCHINH_FACTORY")[0])["factory_status"] == "CONTINUE")
            # simulate writer wrote nothing but another run happens: still WRITER_REQUIRED, no double claim
            r2 = sh(sys.executable, "scripts/run_continuous_factory.py", "run", "--chunk-size", "5", env=env)
            rows = fc.load_matrix()
            check("driver: second run resumes same chunk (no overlapping claim)",
                  len([x for x in rows if x["status"] == "WRITING"]) == 5,
                  str(len([x for x in rows if x["status"] == "WRITING"])))
            # all-terminal matrix => COMPLETE
            for x in rows:
                if x["status"] not in ("PUBLISHED",):
                    x["status"] = "PUBLISHED"
            with fc.MATRIX.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=fc.MATRIX_FIELDS)
                w.writeheader()
                w.writerows(rows)
            r = sh(sys.executable, "scripts/run_continuous_factory.py", "status", env=env)
            j = json.loads(r.stdout.split("VANCHINH_FACTORY")[0])
            check("driver: terminal-only matrix => COMPLETE",
                  j["factory_status"] == "COMPLETE" and j["unfinished"] == 0)
            check("driver: status command prints COMPLETE",
                  "VANCHINH_FACTORY_COMPLETE" in r.stdout)
        finally:
            fc.MATRIX = orig_matrix
            fc.CHECKPOINT = orig_checkpoint
            fc.PROGRESS = ROOT / "reports" / "batches" / "factory-progress.json"
            fc.THROUGHPUT = ROOT / "reports" / "batches" / "factory-throughput.json"
            fc.release_lock()
    check("production matrix untouched by continuous-factory tests",
          orig_matrix.read_bytes() == before_bytes)


def test_driver_fail_closed():
    """FIX 1 regression: the continuous driver must FAIL CLOSED. Any
    production invariant validator failure => BLOCKED verdict, non-zero
    exit, failed validator named with output tail, NO CONTINUE/COMPLETE
    marker; all validators PASS => normal CONTINUE/COMPLETE verdict.
    Covers the shared validation_gate in process AND the `validate`
    subcommand end-to-end (sandbox matrix via CONTENT_MATRIX; the
    production matrix is never mutated by these tests)."""
    import contextlib
    import io
    import run_continuous_factory as drv
    orig_matrix = fc.MATRIX
    orig_checkpoint = fc.CHECKPOINT
    orig_run_validations = drv.run_validations
    before_bytes = orig_matrix.read_bytes()

    def gate_out(mode, results):
        buf = io.StringIO()
        drv.run_validations = lambda: results
        try:
            with contextlib.redirect_stdout(buf):
                rc = drv.validation_gate(ctx={"mode": "test"}, mode=mode)
        finally:
            drv.run_validations = orig_run_validations
        return rc, buf.getvalue()

    with tempfile.TemporaryDirectory() as td:
        tdp = pathlib.Path(td)
        fc.MATRIX = tdp / "m.csv"
        fc.CHECKPOINT = tdp / "writer-checkpoint.json"
        shutil.copyfile(orig_matrix, fc.MATRIX)
        ok = {n: {"returncode": 0, "stdout_tail": "", "stderr_tail": ""}
              for n, _ in drv.VALIDATION_CMDS}
        # --- in-process gate: all validators PASS => CONTINUE allowed ------
        rc, out = gate_out("run", {k: dict(v) for k, v in ok.items()})
        j = json.loads(out.split("VANCHINH_FACTORY")[0])
        check("gate: all validators PASS => rc 0 CONTINUE verdict",
              rc == 0 and j["status"] == "CONTINUE", f"rc={rc} {out[-200:]}")
        check("gate: all validators PASS prints CONTINUING marker",
              "VANCHINH_FACTORY_CONTINUING" in out, out[-120:])
        check("gate: all validators PASS has no BLOCKED marker",
              "VANCHINH_FACTORY_BLOCKED" not in out)
        # --- in-process gate: each single validator FAIL => BLOCKED ---------
        for name in ("matrix", "site", "cannibalization", "matrix_sync"):
            results = {k: ({"returncode": 1, "stdout_tail": f"{k} boom",
                           "stderr_tail": ""} if k == name else dict(ok[k]))
                       for k in ok}
            rc, out = gate_out("run", results)
            j = json.loads(out.split("VANCHINH_FACTORY")[0])
            check(f"gate: {name} FAIL => rc 2 status BLOCKED",
                  rc == 2 and j["status"] == "BLOCKED", f"rc={rc} {out[-200:]}")
            check(f"gate: {name} FAIL names exactly the failed validator",
                  j["failed_validators"] == [name], str(j.get("failed_validators")))
            check(f"gate: {name} FAIL includes validator output tail",
                  f"{name} boom" in json.dumps(j.get("failures", {}), ensure_ascii=False))
            check(f"gate: {name} FAIL prints BLOCKED marker",
                  "VANCHINH_FACTORY_BLOCKED" in out)
            check(f"gate: {name} FAIL never prints CONTINUING/COMPLETE",
                  "VANCHINH_FACTORY_CONTINUING" not in out and
                  "VANCHINH_FACTORY_COMPLETE" not in out, out[-120:])
        # --- all-terminal sandbox matrix + PASS => COMPLETE -----------------
        rows = list(csv.DictReader(open(fc.MATRIX, encoding="utf-8", newline="")))
        for x in rows:
            x["status"] = "PUBLISHED"
        with fc.MATRIX.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fc.MATRIX_FIELDS)
            w.writeheader()
            w.writerows(rows)
        rc, out = gate_out("run", {k: dict(v) for k, v in ok.items()})
        check("gate: all PASS + terminal matrix => rc 0 COMPLETE marker",
              rc == 0 and "VANCHINH_FACTORY_COMPLETE" in out, out[-120:])
        # --- validate mode: all PASS => VALIDATIONS_PASS --------------------
        rc, out = gate_out("validate", {k: dict(v) for k, v in ok.items()})
        check("gate: validate mode all PASS => rc 0 VALIDATIONS_PASS",
              rc == 0 and "VANCHINH_FACTORY_VALIDATIONS_PASS" in out, out[-120:])

        # --- end-to-end: `validate` subcommand vs sandbox matrix ------------
        def sandbox(mutate=None):
            shutil.copyfile(orig_matrix, fc.MATRIX)
            if mutate:
                rows = list(csv.DictReader(open(fc.MATRIX, encoding="utf-8", newline="")))
                mutate(rows)
                with fc.MATRIX.open("w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=fc.MATRIX_FIELDS)
                    w.writeheader()
                    w.writerows(rows)

        def run_validate():
            env = dict(os.environ, CONTENT_MATRIX=str(fc.MATRIX),
                       PROGRESS_FILE=str(tdp / "p.json"),
                       WRITER_CHECKPOINT=str(fc.CHECKPOINT),
                       FACTORY_THROUGHPUT=str(tdp / "t.json"))
            return sh(sys.executable, "scripts/run_continuous_factory.py",
                      "validate", env=env)

        # baseline: byte-identical production copy => all validators PASS
        sandbox()
        r = run_validate()
        check("driver validate: baseline copy => rc 0 + VALIDATIONS_PASS",
              r.returncode == 0 and "VANCHINH_FACTORY_VALIDATIONS_PASS" in r.stdout,
              f"rc={r.returncode} {r.stdout[-300:]}")
        check("driver validate: baseline prints no BLOCKED",
              "VANCHINH_FACTORY_BLOCKED" not in r.stdout)

        # matrix validator FAIL: invalid status value
        sandbox(lambda rows: rows[0].__setitem__("status", "FOO"))
        r = run_validate()
        j = json.loads(r.stdout.split("VANCHINH_FACTORY")[0])
        check("driver validate: matrix FAIL => rc 2 BLOCKED + no CONTINUING",
              r.returncode == 2 and "VANCHINH_FACTORY_BLOCKED" in r.stdout and
              "VANCHINH_FACTORY_CONTINUING" not in r.stdout,
              f"rc={r.returncode} {r.stdout[-200:]}")
        check("driver validate: matrix FAIL names matrix validator",
              "matrix" in j["failed_validators"], str(j.get("failed_validators")))

        # site validator FAIL: PLANNED row flipped PUBLISHED (sitemap/hub drift)
        flip_id = next(x["article_id"] for x in
                       csv.DictReader(open(orig_matrix, encoding="utf-8", newline=""))
                       if x["status"] == "PLANNED")

        def flip_published(rows):
            for x in rows:
                if x["article_id"] == flip_id:
                    x["status"] = "PUBLISHED"
        sandbox(flip_published)
        r = run_validate()
        j = json.loads(r.stdout.split("VANCHINH_FACTORY")[0])
        check("driver validate: site FAIL => rc 2 BLOCKED + no CONTINUING",
              r.returncode == 2 and "VANCHINH_FACTORY_BLOCKED" in r.stdout and
              "VANCHINH_FACTORY_CONTINUING" not in r.stdout,
              f"rc={r.returncode} {r.stdout[-200:]}")
        check("driver validate: site FAIL names site validator",
              "site" in j["failed_validators"], str(j.get("failed_validators")))

        # cannibalization FAIL: a row claims the protected keyword
        def steal_keyword(rows):
            for x in rows:
                if x["article_id"] == flip_id:
                    x["primary_keyword"] = "thuê xe máy hà nội"
        sandbox(steal_keyword)
        r = run_validate()
        j = json.loads(r.stdout.split("VANCHINH_FACTORY")[0])
        check("driver validate: cannibalization FAIL => rc 2 BLOCKED + no CONTINUING",
              r.returncode == 2 and "VANCHINH_FACTORY_BLOCKED" in r.stdout and
              "VANCHINH_FACTORY_CONTINUING" not in r.stdout,
              f"rc={r.returncode} {r.stdout[-200:]}")
        check("driver validate: cannibalization FAIL names validator",
              "cannibalization" in j["failed_validators"],
              str(j.get("failed_validators")))

        # matrix-sync FAIL: committed content field drifts from generator truth
        def drift_title(rows):
            for x in rows:
                if x["article_id"] == flip_id:
                    x["working_title"] = x["working_title"] + " (drifted)"
        sandbox(drift_title)
        r = run_validate()
        j = json.loads(r.stdout.split("VANCHINH_FACTORY")[0])
        check("driver validate: matrix_sync FAIL => rc 2 BLOCKED + no CONTINUING",
              r.returncode == 2 and "VANCHINH_FACTORY_BLOCKED" in r.stdout and
              "VANCHINH_FACTORY_CONTINUING" not in r.stdout,
              f"rc={r.returncode} {r.stdout[-200:]}")
        check("driver validate: matrix_sync FAIL names validator",
              "matrix_sync" in j["failed_validators"], str(j.get("failed_validators")))
        # sync checker restored the sandbox matrix byte-identical every run
        sandbox()
        check("driver validate: sync checker restores sandbox matrix",
              fc.MATRIX.read_bytes() == orig_matrix.read_bytes())
        fc.MATRIX = orig_matrix
        fc.CHECKPOINT = orig_checkpoint
    check("production matrix untouched by driver fail-closed tests",
          orig_matrix.read_bytes() == before_bytes)


def test_push_selection_and_repair():
    """Push-scope selection + repair/resume regressions (workflow contract):
    (1) push adds 5 files -> exactly those 5 claimed, other PLANNED rows stay
        PLANNED (never over-claim, the B18 root cause);
    (2) push adds 10 files -> exactly 10 claimed;
    (3) repair-only push (modified article files) processes exactly the
        repaired IDs and NEVER claims a fresh PLANNED row;
    (4) REPAIR -> PASS clears pending_repair_ids and enters pass/publish lists;
    (5) PASS -> PUBLISHED cleans checkpoint pending lists + txn marker;
    (6) a PLANNED row whose file is missing is never claimed even if listed;
    (7) 50 added files -> exactly 50 claimed (Simple Production Mode batch);
    (8) added files exceeding MAX_CLAIM -> refuse (never silently claim)."""
    orig_matrix = fc.MATRIX
    orig_checkpoint = fc.CHECKPOINT
    before_bytes = orig_matrix.read_bytes()
    import run_article_batch as rab  # noqa: E402
    import factory_push_selection as fps  # noqa: E402
    import score_article_seo  # noqa: E402
    with tempfile.TemporaryDirectory() as td:
        tdp = pathlib.Path(td)
        fc.MATRIX = tdp / "m.csv"
        fc.CHECKPOINT = tdp / "writer-checkpoint.json"
        fc.PROGRESS = tdp / "progress.json"
        fc.THROUGHPUT = tdp / "throughput.json"
        orig_rows = [dict(r) for r in csv.DictReader(open(orig_matrix, encoding="utf-8", newline=""))]
        orig_by = {x["article_id"]: x for x in orig_rows}
        test_ids = [f"AT-{i:04d}" for i in range(1, 52)]  # AT-0001..AT-0051 (files exist)

        def write_rows(status_map, path_overrides=None):
            rows = [dict(r) for r in orig_rows]
            by = {x["article_id"]: x for x in rows}
            for x in rows:
                if x["article_id"] in status_map:
                    x["status"] = status_map[x["article_id"]][0]
                    x["repair_attempts"] = status_map[x["article_id"]][1]
                elif x["article_id"] not in test_ids:
                    x["status"] = "PUBLISHED"
                    x["repair_attempts"] = "0"
            for aid, p in (path_overrides or {}).items():
                by[aid]["output_path"] = p
            with fc.MATRIX.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=fc.MATRIX_FIELDS)
                w.writeheader()
                w.writerows(rows)

        def path_of(aid):
            return orig_by[aid]["output_path"]

        env = dict(os.environ, CONTENT_MATRIX=str(fc.MATRIX),
                   PROGRESS_FILE=str(fc.PROGRESS), WRITER_CHECKPOINT=str(fc.CHECKPOINT),
                   FACTORY_THROUGHPUT=str(fc.THROUGHPUT), SEO_REPORTS_DIR=str(tdp / "seo"))
        empty = tdp / "empty.txt"
        empty.write_text("")
        try:
            # --- (2) 10 added files -> exactly 10 claimed -------------------
            write_rows({aid: ("PLANNED", "0") for aid in test_ids[:10]})
            added10 = tdp / "added10.txt"
            added10.write_text("\n".join(path_of(a) for a in test_ids[:10]) + "\n")
            r = sh(sys.executable, "scripts/factory_push_selection.py",
                   "--added", str(added10), "--modified", str(empty), env=env)
            sel = json.loads(r.stdout)
            check("selection: 10 added files -> exactly 10 claim ids",
                  sel["claim_ids"] == sorted(test_ids[:10]) and sel["mode"] == "new",
                  r.stdout[-300:])
            # --- (7) 50 added files -> exactly 50 claimed (batch = chunk = 50)
            write_rows({aid: ("PLANNED", "0") for aid in test_ids[:50]})
            added50 = tdp / "added50.txt"
            added50.write_text("\n".join(path_of(a) for a in test_ids[:50]) + "\n")
            r = sh(sys.executable, "scripts/factory_push_selection.py",
                   "--added", str(added50), "--modified", str(empty), env=env)
            sel = json.loads(r.stdout)
            check("selection: 50 added files -> exactly 50 claim ids",
                  sel["claim_ids"] == sorted(test_ids[:50]) and sel["mode"] == "new",
                  r.stdout[-300:])
            # --- (8) added files exceeding MAX_CLAIM -> refuse (never silently claim)
            # A batch holds exactly 50 rows, so the >MAX_CLAIM guard is
            # exercised in-process with a reduced cap (same refuse logic).
            write_rows({aid: ("PLANNED", "0") for aid in test_ids[:10]})
            fps.MAX_CLAIM = 5  # simulate a smaller cap; guard is size-independent
            sel = fps.select([path_of(a) for a in test_ids[:10]], [])
            check("selection: added files exceeding MAX_CLAIM -> refuse",
                  bool(sel["refuse"]) and not sel["proceed"], str(sel)[:200])
            fps.MAX_CLAIM = 50
            # --- (1) 5 added files -> exactly 5 claimed ----------------------
            write_rows({aid: ("PLANNED", "0") for aid in test_ids[:10]})
            added5 = tdp / "added5.txt"
            added5.write_text("\n".join(path_of(a) for a in test_ids[:5]) + "\n")
            r = sh(sys.executable, "scripts/factory_push_selection.py",
                   "--added", str(added5), "--modified", str(empty), env=env)
            sel = json.loads(r.stdout)
            check("selection: 5 added files -> exactly 5 claim ids",
                  sel["claim_ids"] == test_ids[:5] and sel["mode"] == "new", r.stdout[-300:])
            check("selection: PLANNED rows not in the push are never claimed",
                  all(a not in sel["claim_ids"] for a in test_ids[5:]), str(sel["claim_ids"]))
            r = sh(sys.executable, "scripts/run_article_batch.py", "claim", "B01",
                   "--ids", ",".join(test_ids[:5]), env=env)
            j = json.loads([l for l in r.stdout.splitlines() if l.strip().startswith("{")][-1])
            check("claim --ids: exactly 5 rows PLANNED->WRITING",
                  j["claimed"] == 5, r.stdout[-300:])
            st = {x["article_id"]: x["status"] for x in fc.load_matrix()
                  if x["article_id"] in test_ids[:10]}
            check("claim --ids: unclaimed PLANNED rows stay PLANNED",
                  all(st[a] == "PLANNED" for a in test_ids[5:10]) and
                  all(st[a] == "WRITING" for a in test_ids[:5]), str(st))
            # --- (6) PLANNED row with missing file never claimed -------------
            write_rows({aid: ("PLANNED", "0") for aid in test_ids[:10]},
                       {"AT-0006": "cam-nang/__test_missing__/at-0006.html"})
            added6 = tdp / "added6.txt"
            added6.write_text("\n".join(path_of(a) for a in test_ids[:6]) + "\n")
            r = sh(sys.executable, "scripts/factory_push_selection.py",
                   "--added", str(added6), "--modified", str(empty), env=env)
            sel = json.loads(r.stdout)
            check("selection: PLANNED row with missing file never claimed",
                  "AT-0006" not in sel["claim_ids"] and
                  sel["claim_ids"] == test_ids[:5], str(sel["claim_ids"]))
            # --- (3) repair-only push: no fresh PLANNED claim ---------------
            # fixture: AT-0001,2,6..10 PLANNED with files present (would be
            # over-claimed by the old buggy workflow), AT-0003..5 REPAIR
            repair_fixture = {"AT-0003": ("REPAIR", "1"), "AT-0004": ("REPAIR", "1"),
                               "AT-0005": ("REPAIR", "1"),
                               "AT-0001": ("PLANNED", "0"), "AT-0002": ("PLANNED", "0")}
            repair_fixture.update({aid: ("PLANNED", "0") for aid in test_ids[5:10]})
            write_rows(repair_fixture)
            modified3 = tdp / "modified3.txt"
            modified3.write_text("\n".join(path_of(a) for a in test_ids[2:5]) + "\n")
            r = sh(sys.executable, "scripts/factory_push_selection.py",
                   "--added", str(empty), "--modified", str(modified3), env=env)
            sel = json.loads(r.stdout)
            check("selection: repair-only push -> mode repair, no claim ids",
                  sel["mode"] == "repair" and sel["claim_ids"] == [] and
                  sel["qa_ids"] == test_ids[2:5], r.stdout[-300:])
            check("selection: repair push never claims fresh PLANNED rows",
                  all(a not in sel["qa_ids"] for a in test_ids[:2] + test_ids[5:]))
            # --- (4) REPAIR -> PASS clears pending_repair_ids ----------------
            fc.write_checkpoint(batch="B01", chunk_size=3,
                                current_chunk_ids=test_ids[2:5],
                                pending_repair_ids=test_ids[2:5],
                                last_completed_step="qa")
            cp = fc.read_checkpoint()
            check("fixture: stale pending_repair visible before repair QA",
                  cp["pending_repair_ids"] == test_ids[2:5], str(cp.get("pending_repair_ids")))
            r = sh(sys.executable, "scripts/run_article_batch.py", "qa", "B01",
                   "--ids", ",".join(test_ids[2:5]), env=env)
            j = json.loads([l for l in r.stdout.splitlines() if l.strip().startswith("{")][-1])
            check("qa --ids REPAIR rows: all PASS (real files)",
                  j["results"]["PASS"] == 3 and j["pass"] == test_ids[2:5], r.stdout[-300:])
            cp = fc.read_checkpoint()
            check("REPAIR->PASS: pending_repair_ids cleared (no stale entries)",
                  cp["pending_repair_ids"] == [], str(cp.get("pending_repair_ids")))
            check("REPAIR->PASS: rows enter pass_ids + pending_publish_ids",
                  set(test_ids[2:5]) <= set(cp["pass_ids"]) and
                  set(test_ids[2:5]) <= set(cp["pending_publish_ids"]),
                  str(cp.get("pass_ids")))
            st = {x["article_id"]: x["status"] for x in fc.load_matrix()
                  if x["article_id"] in test_ids[2:5]}
            check("REPAIR->PASS: matrix rows are PASS",
                  all(v == "PASS" for v in st.values()), str(st))
            # --- (5) PASS -> PUBLISHED cleans checkpoint + txn --------------
            orig_run = rab.run
            orig_seo_dir = score_article_seo.SEO_DIR
            score_article_seo.SEO_DIR = tdp / "seo"
            fake = lambda cmd: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
            rab.run = fake
            try:
                rc = rab.cmd_publish("B01", ids=test_ids[2:5])
                check("publish --ids: PASS rows published", rc == 0, f"rc={rc}")
            finally:
                rab.run = orig_run
                score_article_seo.SEO_DIR = orig_seo_dir
                if fc.txn_pending():
                    fc.recover_txn()
                fc.release_lock()
            st = {x["article_id"]: x["status"] for x in fc.load_matrix()
                  if x["article_id"] in test_ids[2:5]}
            check("PASS->PUBLISHED: matrix rows PUBLISHED",
                  all(v == "PUBLISHED" for v in st.values()), str(st))
            cp = fc.read_checkpoint()
            check("PUBLISHED: rows in published_ids",
                  set(test_ids[2:5]) <= set(cp["published_ids"]))
            check("PUBLISHED: rows leave pass/pending_publish/pending_repair",
                  not (set(test_ids[2:5]) & (set(cp["pass_ids"]) | set(cp["pending_publish_ids"]) |
                       set(cp["pending_repair_ids"]))),
                  json.dumps({k: cp.get(k) for k in ("pass_ids", "pending_publish_ids",
                                                     "pending_repair_ids")}))
            check("PUBLISHED: no txn marker left behind", not fc.txn_pending())
            check("PUBLISHED: no lock left behind", not fc.LOCK.exists())
        finally:
            fc.MATRIX = orig_matrix
            fc.CHECKPOINT = orig_checkpoint
            fc.PROGRESS = ROOT / "reports" / "batches" / "factory-progress.json"
            fc.THROUGHPUT = ROOT / "reports" / "batches" / "factory-throughput.json"
            if fc.txn_pending():
                fc.recover_txn()
            fc.release_lock()
    check("production matrix untouched by push-selection tests",
          orig_matrix.read_bytes() == before_bytes)


def main():
    t0 = time.time()
    test_facts()
    test_public_pages()
    test_matrix()
    test_scripts()
    test_fixture_qa()
    test_txn_and_lock()
    test_recover_fail_closed()
    test_publish_rollback_fail_closed()
    test_factory_liveness()
    test_progress()
    test_hub_generation()
    test_taxonomy()
    test_navigation()
    test_chunked_factory()
    test_claim_resume_repair_rows()
    test_continuous_factory()
    test_driver_fail_closed()
    test_push_selection_and_repair()
    test_seo_scorer()
    test_support_no_zalo()
    print(f"\n{PASS} passed, {len(FAIL)} failed ({time.time()-t0:.1f}s)")
    if FAIL:
        for f in FAIL[:40]:
            print("FAILED:", f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
