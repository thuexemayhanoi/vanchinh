#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""generate_hub_lists.py - regenerate hub page article lists from Matrix truth.

Rules (taxonomy contract):
- Each canonical hub lists ONLY PUBLISHED articles of its own category.
- Listing is deterministic (sorted by batch_id, article_id) and paginated:
  the hub page shows the first fc.HUB_PAGE_SIZE links; further links live on
  generated listing pages `<hub>-trang-<n>.html` (page 2, 3, ...).
- Orphan listing pages (no longer needed after status changes/recovery) are
  removed so hub content never drifts from Matrix truth.
- Never renders article links in the sidebar menu or footer.
"""
import re
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import factory_common as fc

HUBS = {"kinhnghiem": "KN", "antoan": "AT", "xemay": "XM",
        "dulich": "DL", "cungduong": "CD", "hoidap": "HD"}

sys.path.insert(0, str(fc.ROOT / "tools"))


def _list_html(published, page, total_pages, hub_id):
    items = "\n".join(
        f'<li class="mb-2"><a href="{r["output_path"]}" class="text-brand-600 dark:text-brand-400 font-semibold hover:underline">{r["working_title"]}</a></li>'
        for r in published)
    pag = ""
    if total_pages > 1:
        links = []
        for p in range(1, total_pages + 1):
            href = f"{hub_id}.html" if p == 1 else fc.listing_page(hub_id, p)
            cls = "font-bold underline" if p == page else "hover:underline"
            links.append(f'<a href="{href}" class="{cls} text-brand-600 dark:text-brand-400">{p}</a>')
        pag = ('<nav class="mt-6 space-x-3" aria-label="Trang danh mục">'
               + " ".join(links) + "</nav>")
    if published:
        return f'<ul class="space-y-1 list-disc pl-5">{items}</ul>{pag}'
    return ('<p><i aria-hidden="true" class="fas fa-info-circle mr-2 text-brand-500"></i>'
            'Chưa có bài viết nào trong chuyên mục này. Danh sách sẽ được cập nhật tự động '
            'khi các bài đạt chuẩn xuất bản.</p>')


def _render_listing_page(hub_id, hub_name, desc, page, total_pages, inner):
    """Full listing page (page >= 2) built with the shared site chrome."""
    import build_pages as bp
    filename = fc.listing_page(hub_id, page)
    body = (bp.page_h1(f"Cẩm Nang {hub_name} - Trang {page} - Văn Chính",
                       f"Danh sách bài viết chuyên mục {hub_name} (trang {page}/{total_pages}).",
                       "fas fa-book-open")
            + bp.content_block(f'<p>{desc}</p><div class="my-6">{inner}</div>'))
    html = bp.render_page(
        filename,
        title=f"Cẩm Nang {hub_name} - Trang {page} - Thuê Xe Máy Hà Nội - Văn Chính",
        description=f"Danh sách bài viết chuyên mục {hub_name} của Văn Chính - trang {page}/{total_pages}.",
        content=body,
        extra_jsonld=[bp.breadcrumb(f"Cẩm Nang {hub_name}", f"{hub_id}.html"),
                      bp.breadcrumb(f"Cẩm Nang {hub_name} - Trang {page}", filename)],
    )
    return filename, html


def main():
    problems = fc.validate_nav_taxonomy()
    for p in problems:
        print(f"ERROR taxonomy: {p}")
    if problems:
        return 1
    rows = fc.load_matrix()
    for hub, cat in HUBS.items():
        page_path = fc.ROOT / f"{hub}.html"
        if not page_path.exists():
            print(f"WARN hub page missing: {page_path}")
            continue
        published = sorted(
            (r for r in rows if r["category"] == cat and r["status"] == "PUBLISHED"),
            key=lambda r: (r["batch_id"], r["article_id"]))
        size = fc.HUB_PAGE_SIZE
        total_pages = max(1, -(-len(published) // size))
        # page 1 -> hub page container
        chunk = published[:size]
        inner = _list_html(chunk, 1, total_pages, hub)
        html = page_path.read_text(encoding="utf-8")
        html = re.sub(r'(<div id="hub-list-' + hub + r'"[^>]*>).*?(</div>)',
                      lambda m: m.group(1) + inner + m.group(2), html, flags=re.S)
        page_path.write_text(html, encoding="utf-8")
        # pages 2..N -> generated listing pages
        for p in range(2, total_pages + 1):
            chunk = published[(p - 1) * size:p * size]
            inner_p = _list_html(chunk, p, total_pages, hub)
            name, html_p = _render_listing_page(hub, HUB_NAMES[hub], HUB_DESCS[hub], p, total_pages, inner_p)
            (fc.ROOT / name).write_text(html_p, encoding="utf-8")
            print(f"listing page {name}: {len(chunk)} articles")
        # orphan cleanup: remove listing pages beyond current total_pages
        for f in fc.ROOT.glob(f"{hub}-trang-*.html"):
            try:
                n = int(f.stem.split("-trang-")[1])
            except ValueError:
                continue
            if n < 2 or n > total_pages:
                f.unlink()
                print(f"removed orphan listing page {f.name}")
        print(f"hub {hub}: {len(published)} published, {total_pages} listing page(s)")
    return 0


HUB_NAMES = {"kinhnghiem": "Kinh Nghiệm", "antoan": "An Toàn", "xemay": "Xe Máy",
             "dulich": "Du Lịch", "cungduong": "Cung Đường", "hoidap": "Hỏi Đáp"}
HUB_DESCS = {
    "kinhnghiem": "Kinh nghiệm thuê xe máy tại Hà Nội.",
    "antoan": "An toàn khi đi xe máy.",
    "xemay": "Tìm hiểu về xe máy.",
    "dulich": "Du lịch Hà Nội bằng xe máy.",
    "cungduong": "Các cung đường phượt từ Hà Nội.",
    "hoidap": "Hỏi đáp về thuê xe máy.",
}


if __name__ == "__main__":
    sys.exit(main())
