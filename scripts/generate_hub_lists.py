#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""generate_hub_lists.py - regenerate hub page article lists from Matrix truth.

Updates the `hub-list-<id>` container in each hub page with PUBLISHED articles
of that category (title + link). Never lists unpublished rows.
"""
import re
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import factory_common as fc

HUBS = {"kinhnghiem": "KN", "antoan": "AT", "xemay": "XM",
        "dulich": "DL", "cungduong": "CD", "hoidap": "HD"}


def main():
    rows = fc.load_matrix()
    for hub, cat in HUBS.items():
        page = fc.ROOT / f"{hub}.html"
        if not page.exists():
            print(f"WARN hub page missing: {page}")
            continue
        published = [r for r in rows if r["category"] == cat and r["status"] == "PUBLISHED"]
        items = "\n".join(
            f'<li class="mb-2"><a href="{r["output_path"]}" class="text-brand-600 dark:text-brand-400 font-semibold hover:underline">{r["working_title"]}</a></li>'
            for r in published)
        if published:
            inner = f'<ul class="space-y-1 list-disc pl-5">{items}</ul>'
        else:
            inner = ('<p><i aria-hidden="true" class="fas fa-info-circle mr-2 text-brand-500"></i>'
                     'Chưa có bài viết nào trong chuyên mục này. Danh sách sẽ được cập nhật tự động '
                     'khi các bài đạt chuẩn xuất bản.</p>')
        html = page.read_text(encoding="utf-8")
        html = re.sub(r'(<div id="hub-list-' + hub + r'"[^>]*>).*?(</div>)',
                      lambda m: m.group(1) + inner + m.group(2), html, flags=re.S)
        page.write_text(html, encoding="utf-8")
        print(f"hub {hub}: {len(published)} published listed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
