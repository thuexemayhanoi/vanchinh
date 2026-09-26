#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_matrix_sync.py - the committed matrix must equal the deterministic
output of tools/generate_content_matrix.py under the current config.

Safe to run locally: the production matrix is backed up and restored on exit.
On mismatch, prints up to 20 field-level diffs and exits 1.
"""
import csv
import io
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MATRIX = ROOT / "data" / "content-matrix.csv"


def main():
    before = MATRIX.read_bytes()
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "generate_content_matrix.py")],
                       capture_output=True, text=True, cwd=str(ROOT))
    if r.returncode != 0:
        MATRIX.write_bytes(before)
        print("generator failed:", r.stdout, r.stderr)
        return 1
    after = MATRIX.read_bytes()
    if before == after:
        print("matrix in sync with deterministic generator output")
        return 0
    # restore production matrix, then report the differences
    MATRIX.write_bytes(before)
    old = list(csv.DictReader(io.StringIO(before.decode("utf-8"))))
    new = list(csv.DictReader(io.StringIO(after.decode("utf-8"))))
    print(f"MATRIX OUT OF SYNC: committed {len(before)} bytes vs generator {len(after)} bytes")
    diffs = 0
    for i in range(max(len(old), len(new))):
        a = old[i] if i < len(old) else {}
        b = new[i] if i < len(new) else {}
        if a == b:
            continue
        aid = (a or b).get("article_id", "?")
        changed = [k for k in b if a.get(k) != b.get(k)] if b else list(a.keys())
        for k in changed[:5]:
            msg = f"{aid} {k}: committed={a.get(k, '')[:60]!r} generator={b.get(k, '')[:60]!r}"
            print("  " + msg)
            safe = msg.replace("%", "%25").replace("\r", " ").replace("\n", " ").replace('"', "'")
            print(f"::error file=data/content-matrix.csv,title=Matrix out of sync::{safe}")
        diffs += 1
        if diffs >= 20:
            print("  ... (further diffs suppressed)")
            break
    return 1


if __name__ == "__main__":
    sys.exit(main())
