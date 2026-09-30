#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/factory_soak.py - Tier 4 multi-chunk soak + failure recovery (FIX 4).

Dedicated sandbox long-run test. It ABSOLUTELY NEVER uses the production
matrix, never publishes production articles, and never mutates production
checkpoint/lock/txn state: the whole repository tree is copied into a temp
fixture environment and every cycle runs against that fixture copy only
(all scripts resolve ROOT from their own location, so no env overrides are
even needed - fixture defaults are already isolated). The production
working copy is checksummed before and after and must be byte-identical.

Cycle (per iteration):
  claim -> writer fixture (file present/restore) -> QA -> PASS -> publish
  -> verify -> next chunk

Controlled fault injections across iterations:
  1. writer-required resume (chunk files missing -> WRITER_REQUIRED ->
     writer writes files -> driver resumes -> qa -> publish -> gate)
  2. transient hub generation failure (rollback completes inline, marker
     cleared, retry publish succeeds, no double publish)
  3. persistent sitemap generation failure (rollback incomplete -> txn
     marker KEPT -> recover verifies rollback -> retry publish succeeds)
  4. crash after begin_txn, before matrix write (recover -> verified
     rollback -> publish succeeds)
  5. crash after partial writes, after matrix save (recover -> verified
     completion: derived outputs regenerated, marker cleared, exactly-once)
  6. stale writer lock (liveness FAIL, claim refused, audited stale-lock
     recovery, publish succeeds) + invariant validation failure (driver
     validate BLOCKED, no CONTINUING marker; restored -> gate PASS)

Per-iteration assertions: transaction clean after successful recovery or
commit, lock clean, checkpoint matches matrix, no skipped ids, no
duplicate publish, published counter monotonic, sitemap contains exactly
PUBLISHED articles, hub lists contain exactly PUBLISHED articles of the
right category, no orphan listing pages, no draft/test leak, retry never
double-publishes, deterministic rebuild does not drift.

Run: python3 tests/factory_soak.py
"""
import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
CHUNK = 5
N_ITERATIONS = 6
SOAK_IDS = [f"AT-{i:04d}" for i in range(1, N_ITERATIONS * CHUNK + 1)]  # AT-0001..0030

PASS, FAIL = 0, []


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"ok   {name}")
    else:
        FAIL.append(f"{name} {detail}")
        print(f"FAIL {name} {detail}")


def tree_hashes(root):
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def sh(cwd, *args, env=None):
    return subprocess.run([sys.executable, *args], capture_output=True,
                          text=True, cwd=str(cwd), env=env)


def load_fixture_fc(fixture):
    spec = importlib.util.spec_from_file_location(
        "fc_fixture", fixture / "scripts" / "factory_common.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_matrix(fixture):
    with (fixture / "data" / "content-matrix.csv").open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_matrix(fixture, rows, fcf):
    with (fixture / "data" / "content-matrix.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fcf.MATRIX_FIELDS)
        w.writeheader()
        w.writerows(rows)


def fixture_env(extra=None):
    env = dict(os.environ)
    env.pop("FORCE_STALE_LOCK_RECOVERY", None)
    env.update(extra or {})
    return env


class Soak:
    def __init__(self, fixture):
        self.fixture = fixture
        self.fcf = load_fixture_fc(fixture)
        self.published_baseline = None
        # ids completed by the crash-completion path (recover finishes the
        # publish): the checkpoint is DERIVED state and may legitimately lag
        # here (matrix wins); containment is asserted for all other ids.
        self.crash_completed = set()

    # --- fixture state helpers -------------------------------------------
    def rows(self):
        return read_matrix(self.fixture)

    def by_id(self):
        return {r["article_id"]: r for r in self.rows()}

    def published_count(self):
        return len([r for r in self.rows() if r["status"] == "PUBLISHED"])

    def statuses(self, ids):
        by = self.by_id()
        return {i: by[i]["status"] for i in ids}

    def marker_path(self):
        return self.fixture / "data" / "batches" / "txn" / "txn.json"

    def lock_path(self):
        return self.fixture / "data" / "batches" / "lock.json"

    def checkpoint(self):
        """Contract view of the checkpoint: pending lists are DERIVED state,
        filtered against current matrix statuses on read (matrix wins)."""
        try:
            return self.fcf.read_checkpoint()
        except Exception:
            return None

    def raw_checkpoint(self):
        p = self.fixture / "data" / "batches" / "writer-checkpoint.json"
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None

    def sitemap_paths(self):
        xml = (self.fixture / "sitemap.xml").read_text(encoding="utf-8")
        locs = re.findall(r"<loc>(.*?)</loc>", xml)
        base = self.fcf.BASE
        rels = []
        for loc in locs:
            if not loc.startswith(base):
                rels.append(None)
            elif loc == base:
                rels.append("")
            else:
                rels.append(loc[len(base):])
        return rels

    # --- commands ---------------------------------------------------------
    def cmd(self, *args, env=None):
        return sh(self.fixture, "scripts/run_article_batch.py", *args,
                  env=fixture_env(env))

    def driver(self, *args, env=None):
        return sh(self.fixture, "scripts/run_continuous_factory.py", *args,
                  env=fixture_env(env))

    def liveness(self, env=None):
        return sh(self.fixture, "scripts/factory_liveness.py",
                  env=fixture_env(env))

    def claim(self, ids, env=None):
        return self.cmd("claim", "B01", "--ids", ",".join(ids), env=env)

    def qa(self, ids, env=None):
        return self.cmd("qa", "B01", "--ids", ",".join(ids), env=env)

    def publish(self, ids=None, env=None):
        args = ["publish", "B01"]
        if ids:
            args += ["--ids", ",".join(ids)]
        return self.cmd(*args, env=env)

    def recover(self, env=None):
        return self.cmd("recover", env=env)

    def write_marker(self, ids):
        by = self.by_id()
        plan = {"articles": [{"article_id": i, "output_path": by[i]["output_path"],
                              "target_status": "PUBLISHED"} for i in ids],
                "updates": ["content-matrix", "hubs", "sitemap.xml",
                            "article-shells", "reports"]}
        p = self.marker_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"plan": plan, "state": "IN_PROGRESS",
                                 "started": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                          time.gmtime())},
                                ensure_ascii=False, indent=2),
                     encoding="utf-8")

    # --- verification ------------------------------------------------------
    def verify_cycle(self, done_ids, expected_published):
        fcf = self.fcf
        by = self.by_id()
        # transaction + lock clean
        check(f"soak: txn marker clean after cycle {done_ids[-1]}",
              not self.marker_path().exists())
        check(f"soak: writer lock clean after cycle {done_ids[-1]}",
              not self.lock_path().exists())
        # chunk fully published, no skipped/stranded ids
        st = self.statuses(done_ids)
        check(f"soak: chunk {done_ids[0]}..{done_ids[-1]} all PUBLISHED",
              set(st.values()) == {"PUBLISHED"}, str(st))
        # published counter monotonic + exact
        pub_now = self.published_count()
        check(f"soak: published counter exact after {done_ids[-1]}",
              pub_now == expected_published, f"{pub_now} != {expected_published}")
        # checkpoint matches matrix
        cp = self.checkpoint() or {}
        published_ids = set(cp.get("published_ids") or [])
        must_be_in_cp = [i for i in done_ids if i not in self.crash_completed]
        check(f"soak: checkpoint published_ids contain {done_ids[0]}..{done_ids[-1]}",
              set(must_be_in_cp) <= published_ids)
        stranded = [i for i in done_ids if i in set(cp.get("pending_qa_ids") or [])
                    | set(cp.get("pending_repair_ids") or [])
                    | set(cp.get("pass_ids") or [])
                    | set(cp.get("pending_publish_ids") or [])]
        check(f"soak: no stranded pending entries for {done_ids[0]}..{done_ids[-1]}",
              not stranded, str(stranded))
        # sitemap == PUBLISHED truth (exactly once, no non-published, no missing target)
        rels = self.sitemap_paths()
        art = [r for r in rels if r and r.startswith("cam-nang/")]
        pub_paths = sorted(r["output_path"] for r in by.values()
                           if r["status"] == "PUBLISHED")
        check(f"soak: sitemap article set == PUBLISHED set ({done_ids[-1]})",
              sorted(art) == pub_paths,
              f"sitemap={len(art)} matrix={len(pub_paths)}")
        dupes = {p for p in art if art.count(p) > 1}
        check(f"soak: no duplicate sitemap entries ({done_ids[-1]})", not dupes, str(dupes))
        unpublished = [r["output_path"] for r in by.values()
                       if r["status"] != "PUBLISHED" and r["output_path"] in art]
        check(f"soak: sitemap never contains non-published ({done_ids[-1]})",
              not unpublished, str(unpublished[:5]))
        missing_target = [r for r in rels
                          if r is not None and not (self.fixture / r).exists()]
        check(f"soak: every sitemap target file exists ({done_ids[-1]})",
              not missing_target, str(missing_target[:5]))
        # hub lists == PUBLISHED truth per category, no orphans
        size = fcf.HUB_PAGE_SIZE
        for cat, hub in sorted(fcf.CATEGORIES.items()):
            hub_stem = hub[:-len(".html")]
            pub_cat = sorted((r for r in by.values()
                              if r["category"] == cat and r["status"] == "PUBLISHED"),
                             key=lambda r: (r["batch_id"], r["article_id"]))
            expected_pages = set()
            for pg in range(2, max(2, math.ceil(len(pub_cat) / size) + 1)):
                expected_pages.add(f"{hub_stem}-trang-{pg}.html")
            listing_files = {p.name for p in self.fixture.glob(f"{hub_stem}-trang-*.html")}
            check(f"soak: no orphan listing pages for {hub_stem} ({done_ids[-1]})",
                  listing_files == expected_pages,
                  f"extra={sorted(listing_files - expected_pages)} "
                  f"missing={sorted(expected_pages - listing_files)}")
            links = []
            html = (self.fixture / hub).read_text(encoding="utf-8")
            links += re.findall(r'href="(cam-nang/[^"]+)"', html)
            for page_name in sorted(expected_pages):
                html = (self.fixture / page_name).read_text(encoding="utf-8")
                links += re.findall(r'href="(cam-nang/[^"]+)"', html)
            expected_links = [r["output_path"] for r in pub_cat]
            check(f"soak: {hub_stem} lists exactly PUBLISHED {cat} articles "
                  f"({done_ids[-1]})",
                  links == expected_links,
                  f"got={len(links)} expected={len(expected_links)}")
        # no draft/test leak anywhere in the fixture tree
        leaks = [str(p) for p in self.fixture.rglob("*")
                 if p.is_file() and ("__test" in p.name or "__missing" in p.name
                                     or "__soak" in str(p.relative_to(self.fixture)))]
        check(f"soak: no draft/test leak ({done_ids[-1]})", not leaks, str(leaks[:5]))

    def verify_exactly_once(self, done_ids):
        rels = self.sitemap_paths()
        art = [r for r in rels if r and r.startswith("cam-nang/")]
        by = self.by_id()
        for i in done_ids:
            p = by[i]["output_path"]
            check(f"soak: {i} published exactly once", art.count(p) == 1)


def install_stub(fixture, script, mode_env, once_flag):
    """Rename the real generator to *_impl.py and install a wrapper that
    fails according to SOAK_STUB mode env (controlled fault injection)."""
    real = fixture / "scripts" / script
    impl = fixture / "scripts" / script.replace(".py", "_impl.py")
    shutil.move(str(real), str(impl))
    wrapper = f'''#!/usr/bin/env python3
import os, sys, pathlib, runpy
_mode = os.environ.get("{mode_env}", "")
if _mode == "always":
    sys.exit(1)
if _mode == "once" and not pathlib.Path("{once_flag}").exists():
    pathlib.Path("{once_flag}").write_text("1")
    sys.exit(1)
_target = str(pathlib.Path(__file__).resolve().parent / "{impl.name}")
sys.argv[0] = _target
runpy.run_path(_target, run_name="__main__")
'''
    real.write_text(wrapper, encoding="utf-8")
    return real, impl


def restore_stub(fixture, script):
    impl = fixture / "scripts" / script.replace(".py", "_impl.py")
    real = fixture / "scripts" / script
    shutil.move(str(impl), str(real))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    args = ap.parse_args()
    t0 = time.time()
    prod_before = tree_hashes(ROOT)
    prod_matrix_before = (ROOT / "data" / "content-matrix.csv").read_bytes()

    with tempfile.TemporaryDirectory(prefix="vanchinh-soak-") as td:
        fixture = pathlib.Path(td) / "fixture"
        print(f"copying repository tree into fixture sandbox ...")
        shutil.copytree(ROOT, fixture)
        s = Soak(fixture)
        fcf = s.fcf

        # fixture matrix: reset the soak rows to PLANNED (writer starting fresh)
        rows = s.rows()
        by = {r["article_id"]: r for r in rows}
        for aid in SOAK_IDS:
            by[aid]["status"] = "PLANNED"
            by[aid]["score"] = ""
            by[aid]["quality_status"] = ""
            by[aid]["repair_attempts"] = "0"
            by[aid]["published_date"] = ""
        write_matrix(fixture, rows, fcf)
        s.published_baseline = len([r for r in rows if r["status"] == "PUBLISHED"])
        expected = s.published_baseline
        # pristine writer copies of the soak article files (writer fixture)
        writer_cache = pathlib.Path(td) / "writer-cache"
        writer_cache.mkdir()
        for aid in SOAK_IDS:
            src = fixture / by[aid]["output_path"]
            shutil.copyfile(str(src), str(writer_cache / aid))

        check("soak: fixture baseline published count",
              expected == 1000, str(expected))
        # bring fixture derived outputs in sync with the fixture matrix
        # (the reset removed 30 articles from the published set)
        sh(fixture, "scripts/generate_sitemap.py")
        sh(fixture, "scripts/generate_hub_lists.py")

        done = []
        prev_pub = expected

        # ---------------- iteration 1: writer-required resume ---------------
        ids = SOAK_IDS[0:CHUNK]
        r = s.claim(ids)
        check("soak1: claim ok", r.returncode == 0, r.stdout[-200:])
        st = s.statuses(ids)
        check("soak1: chunk claimed WRITING", set(st.values()) == {"WRITING"}, str(st))
        # writer "crash": the article files are missing -> WRITER_REQUIRED
        for aid in ids:
            (fixture / by[aid]["output_path"]).unlink()
        r = s.driver("run", "--chunk-size", str(CHUNK))
        check("soak1: missing files => WRITER_REQUIRED rc 1",
              r.returncode == 1 and "VANCHINH_FACTORY_WRITER_REQUIRED" in r.stdout,
              f"rc={r.returncode} {r.stdout[-200:]}")
        check("soak1: chunk stays claimed (resumable)",
              set(s.statuses(ids).values()) == {"WRITING"})
        # writer fixture writes the files back -> driver resumes -> publish -> gate
        for aid in ids:
            shutil.copyfile(str(writer_cache / aid), str(fixture / by[aid]["output_path"]))
        r = s.driver("run", "--chunk-size", str(CHUNK))
        check("soak1: resume => publish + validations => CONTINUING rc 0",
              r.returncode == 0 and "VANCHINH_FACTORY_CONTINUING" in r.stdout,
              f"rc={r.returncode} {r.stdout[-300:]}")
        expected += CHUNK
        done += ids
        s.verify_cycle(done, expected)
        check("soak1: published counter monotonic",
              s.published_count() >= prev_pub)
        prev_pub = s.published_count()

        # ---------------- iteration 2: transient hub failure -----------------
        ids = SOAK_IDS[CHUNK:2 * CHUNK]
        install_stub(fixture, "generate_hub_lists.py", "SOAK_HUB_FAIL",
                     str(pathlib.Path(td) / "soak_hub_once.flag"))
        r = s.claim(ids)
        check("soak2: claim ok", r.returncode == 0, r.stdout[-200:])
        r = s.qa(ids)
        check("soak2: qa PASS", r.returncode == 0 and
              set(s.statuses(ids).values()) == {"PASS"}, r.stdout[-200:])
        r = s.publish(ids, env={"SOAK_HUB_FAIL": "once"})
        check("soak2: hub failure => publish rolled back rc 1",
              r.returncode == 1 and "rolled back" in r.stdout,
              f"rc={r.returncode} {r.stdout[-200:]}")
        check("soak2: rollback clears txn marker inline",
              not s.marker_path().exists())
        check("soak2: rollback restores PASS",
              set(s.statuses(ids).values()) == {"PASS"})
        r = s.publish(ids)
        check("soak2: retry publish succeeds (no double publish)",
              r.returncode == 0, f"rc={r.returncode} {r.stdout[-200:]}")
        restore_stub(fixture, "generate_hub_lists.py")
        expected += CHUNK
        done += ids
        s.verify_cycle(done, expected)
        check("soak2: published counter monotonic",
              s.published_count() >= prev_pub)
        prev_pub = s.published_count()

        # ---------------- iteration 3: persistent sitemap failure -------------
        ids = SOAK_IDS[2 * CHUNK:3 * CHUNK]
        install_stub(fixture, "generate_sitemap.py", "SOAK_SITEMAP_FAIL",
                     str(pathlib.Path(td) / "soak_sitemap_once.flag"))
        r = s.claim(ids)
        check("soak3: claim ok", r.returncode == 0, r.stdout[-200:])
        r = s.qa(ids)
        check("soak3: qa PASS", r.returncode == 0, r.stdout[-200:])
        r = s.publish(ids, env={"SOAK_SITEMAP_FAIL": "always"})
        check("soak3: persistent sitemap failure => rollback incomplete rc 1",
              r.returncode == 1 and "rollback incomplete" in r.stdout,
              f"rc={r.returncode} {r.stdout[-200:]}")
        check("soak3: rollback incomplete KEEPS txn marker", s.marker_path().exists())
        check("soak3: rows rolled back to PASS",
              set(s.statuses(ids).values()) == {"PASS"})
        r = s.recover()
        check("soak3: recover verifies rollback and clears marker",
              r.returncode == 0 and not s.marker_path().exists() and
              "verified rollback" in r.stdout,
              f"rc={r.returncode} {r.stdout[-200:]}")
        r = s.publish(ids)
        check("soak3: retry publish succeeds", r.returncode == 0,
              f"rc={r.returncode} {r.stdout[-200:]}")
        restore_stub(fixture, "generate_sitemap.py")
        expected += CHUNK
        done += ids
        s.verify_cycle(done, expected)
        check("soak3: published counter monotonic",
              s.published_count() >= prev_pub)
        prev_pub = s.published_count()

        # ---------------- iteration 4: crash after begin_txn ------------------
        ids = SOAK_IDS[3 * CHUNK:4 * CHUNK]
        r = s.claim(ids)
        check("soak4: claim ok", r.returncode == 0, r.stdout[-200:])
        r = s.qa(ids)
        check("soak4: qa PASS", r.returncode == 0, r.stdout[-200:])
        # simulate crash right after begin_txn (matrix not yet written)
        s.write_marker(ids)
        check("soak4: crash left txn marker", s.marker_path().exists())
        r = s.recover()
        check("soak4: recover verifies rollback (pre-write crash)",
              r.returncode == 0 and not s.marker_path().exists() and
              "verified rollback" in r.stdout,
              f"rc={r.returncode} {r.stdout[-200:]}")
        check("soak4: rows still PASS (no publish half-done)",
              set(s.statuses(ids).values()) == {"PASS"})
        r = s.publish(ids)
        check("soak4: publish succeeds after recovery",
              r.returncode == 0, f"rc={r.returncode} {r.stdout[-200:]}")
        expected += CHUNK
        done += ids
        s.verify_cycle(done, expected)
        check("soak4: published counter monotonic",
              s.published_count() >= prev_pub)
        prev_pub = s.published_count()

        # ---------------- iteration 5: crash after partial writes --------------
        ids = SOAK_IDS[4 * CHUNK:5 * CHUNK]
        r = s.claim(ids)
        check("soak5: claim ok", r.returncode == 0, r.stdout[-200:])
        r = s.qa(ids)
        check("soak5: qa PASS", r.returncode == 0, r.stdout[-200:])
        # simulate crash after save_matrix but before derived regeneration
        rows = s.rows()
        byf = {x["article_id"]: x for x in rows}
        for aid in ids:
            byf[aid]["status"] = "PUBLISHED"
            byf[aid]["published_date"] = time.strftime("%Y-%m-%d", time.gmtime())
        write_matrix(fixture, rows, fcf)
        s.write_marker(ids)
        check("soak5: partial-write crash left marker", s.marker_path().exists())
        r = s.recover()
        check("soak5: recover verifies completion (derived outputs regenerated)",
              r.returncode == 0 and not s.marker_path().exists() and
              "verified completion" in r.stdout,
              f"rc={r.returncode} {r.stdout[-300:]}")
        check("soak5: rows PUBLISHED exactly once (no double publish)",
              set(s.statuses(ids).values()) == {"PUBLISHED"})
        s.crash_completed.update(ids)
        expected += CHUNK
        done += ids
        s.verify_cycle(done, expected)
        check("soak5: published counter monotonic",
              s.published_count() >= prev_pub)
        prev_pub = s.published_count()

        # ---------------- iteration 6: stale lock + validation fault -----------
        ids = SOAK_IDS[5 * CHUNK:6 * CHUNK]
        lock = s.lock_path()
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text(json.dumps({"operator": "soak-gone",
                                    "acquired": "2026-09-01T00:00:00Z"}),
                        encoding="utf-8")
        old = time.time() - 10 * 3600
        os.utime(lock, (old, old))
        r = s.liveness(env={"LIVENESS_STALL_HOURS": "6",
                            "LIVENESS_LOCK_STALE_HOURS": "6"})
        check("soak6: liveness detects stale lock with unfinished work",
              r.returncode == 1 and
              "EXPIRED_OR_STALE_LOCK_WITH_UNFINISHED_WORK" in r.stdout,
              f"rc={r.returncode} {r.stdout[-200:]}")
        r = s.claim(ids)
        check("soak6: claim refused under stale lock",
              r.returncode != 0, f"rc={r.returncode} {r.stdout[-200:]}")
        r = s.claim(ids, env={"FORCE_STALE_LOCK_RECOVERY": "1"})
        check("soak6: audited stale-lock recovery lets claim proceed",
              r.returncode == 0, f"rc={r.returncode} {r.stdout[-200:]}")
        check("soak6: claim released the lock after stale recovery",
              not s.lock_path().exists())
        r = s.qa(ids)
        check("soak6: qa PASS", r.returncode == 0, r.stdout[-200:])
        # invariant validation fault: matrix corrupted -> gate must BLOCK
        rows = s.rows()
        byf = {x["article_id"]: x for x in rows}
        saved_status = byf["AT-0001"]["status"]
        byf["AT-0001"]["status"] = "FOO"
        write_matrix(fixture, rows, fcf)
        r = s.driver("validate")
        check("soak6: validation fault => BLOCKED rc 2, no CONTINUING",
              r.returncode == 2 and "VANCHINH_FACTORY_BLOCKED" in r.stdout and
              "VANCHINH_FACTORY_CONTINUING" not in r.stdout,
              f"rc={r.returncode} {r.stdout[-200:]}")
        rows = s.rows()
        byf = {x["article_id"]: x for x in rows}
        byf["AT-0001"]["status"] = saved_status
        write_matrix(fixture, rows, fcf)
        r = s.driver("validate")
        check("soak6: restored matrix => validations PASS",
              r.returncode == 0 and "VANCHINH_FACTORY_VALIDATIONS_PASS" in r.stdout,
              f"rc={r.returncode} {r.stdout[-200:]}")
        r = s.publish(ids)
        check("soak6: publish succeeds", r.returncode == 0,
              f"rc={r.returncode} {r.stdout[-200:]}")
        expected += CHUNK
        done += ids
        s.verify_cycle(done, expected)
        check("soak6: published counter monotonic",
              s.published_count() >= prev_pub)

        # ---------------- end-of-soak invariants ------------------------------
        check("soak: expected chunks == completed chunks",
              len(done) == N_ITERATIONS * CHUNK, str(len(done)))
        s.verify_exactly_once(done)
        check("soak: published counter exact at end",
              s.published_count() == s.published_baseline + len(SOAK_IDS),
              f"{s.published_count()} != {s.published_baseline + len(SOAK_IDS)}")
        check("soak: no stale txn at end", not s.marker_path().exists())
        check("soak: no stale lock at end", not s.lock_path().exists())
        stranded = [i for i, stt in s.statuses(SOAK_IDS).items()
                    if stt != "PUBLISHED"]
        check("soak: no stranded PASS/WRITING from harness failure",
              not stranded, str(stranded))
        # raw checkpoint file must also be clean after the last write_checkpoint
        raw = s.raw_checkpoint() or {}
        raw_stranded = [i for i in SOAK_IDS
                        if i in set(raw.get("pending_qa_ids") or [])
                        | set(raw.get("pending_repair_ids") or [])
                        | set(raw.get("pass_ids") or [])
                        | set(raw.get("pending_publish_ids") or [])]
        check("soak: raw checkpoint pending lists clean at end",
              not raw_stranded, str(raw_stranded))
        check("soak: raw checkpoint current chunk clean at end",
              not (raw.get("current_chunk_ids") or []), str(raw.get("current_chunk_ids")))
        # deterministic rebuild: regenerate derived outputs twice, byte-identical
        sitemap_before = (fixture / "sitemap.xml").read_bytes()
        hub_before = {h: (fixture / h).read_bytes()
                       for h in fcf.CATEGORIES.values()}
        for _ in range(2):
            sh(fixture, "scripts/generate_sitemap.py")
            sh(fixture, "scripts/generate_hub_lists.py")
        check("soak: sitemap deterministic rebuild (no drift)",
              (fixture / "sitemap.xml").read_bytes() == sitemap_before)
        check("soak: hub pages deterministic rebuild (no drift)",
              all((fixture / h).read_bytes() == hub_before[h]
                  for h in fcf.CATEGORIES.values()))
        # fixture liveness at end: healthy idle
        r = s.liveness()
        check("soak: fixture liveness HEALTHY at end",
              r.returncode == 0 and "HEALTHY_IDLE" in r.stdout,
              f"rc={r.returncode} {r.stdout[-200:]}")

    # ---------------- production isolation ------------------------------------
    prod_after = tree_hashes(ROOT)
    check("soak: production tree byte-identical before/after",
          prod_before == prod_after,
          f"changed={sorted(set(prod_before) ^ set(prod_after))[:5]}")
    check("soak: production matrix byte-identical",
          (ROOT / "data" / "content-matrix.csv").read_bytes() == prod_matrix_before)
    check("soak: production lock never created",
          not (ROOT / "data" / "batches" / "lock.json").exists())
    check("soak: production txn never created",
          not (ROOT / "data" / "batches" / "txn" / "txn.json").exists())

    print(f"\n{PASS} passed, {len(FAIL)} failed ({time.time()-t0:.1f}s)")
    if FAIL:
        for f in FAIL[:40]:
            print("FAILED:", f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
