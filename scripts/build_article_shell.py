#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_article_shell.py - wrap PUBLISHED articles in the canonical site chrome.

Deterministic, idempotent UI layer only. It NEVER touches:
  - article filenames, slugs, output paths, canonical URLs
  - title, meta description, JSON-LD (Article + BreadcrumbList) - copied verbatim
  - article prose, links, sources
It ADDS:
  - full site chrome (header/sidebar/footer/contact widget) - same visual language
  - deterministic heading IDs + generated TOC (desktop rail + mobile <details>)
  - metadata row (author, published date, reading time from the article itself)
  - legal freshness line (only when matrix last_checked is truthy)
  - sources box styling (wraps the writer's "Nguồn" section in an <aside>)
  - parent hub back-link, 3 deterministic related cards, canonical business CTA

Run: python3 scripts/build_article_shell.py
Only rows with status=PUBLISHED are processed. Running twice is byte-ident.
"""
import json
import pathlib
import re
import sys
import unicodedata

sys.path.insert(0, str(pathlib.Path(__file__).parent))
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "tools"))
import factory_common as fc  # noqa: E402
import build_pages as bp  # noqa: E402

SHELL_MARK = "<!-- vanchinh article shell v1 -->"
HUB_NAMES = {"KN": "Kinh nghiệm", "AT": "An toàn", "XM": "Xe máy",
             "DL": "Du lịch", "CD": "Cung đường", "HD": "Hỏi đáp"}


def _rel_attrs(html):
    """Prefix root-relative href/src for the 2-level-deep article directory."""
    def fix(m):
        attr, val = m.group(1), m.group(2)
        if val.startswith(("http://", "https://", "//", "tel:", "mailto:", "#", "data:", "../../")):
            return f'{attr}="{val}"'
        return f'{attr}="../../{val}"'
    return re.sub(r'(href|src)="([^"]+)"', fix, html)


def _slug(text):
    t = unicodedata.normalize("NFD", text)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t or "muc"


def _tag_text(tag):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", tag)).strip()


def _word_count(region_html):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", region_html, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return len(re.findall(r"[A-Za-zÀ-ỹ0-9]+", t))


def _extract_head(html):
    """Extract the SEO-critical pieces that must survive verbatim."""
    title = re.search(r"<title>([^<]+)</title>", html)
    desc = re.search(r'<meta name="description" content="([^"]+)"', html)
    canonical = re.search(r'<link rel="canonical" href="([^"]+)"[^>]*>', html)
    jsonld = re.findall(r'<script type="application/ld\+json">\s*.*?</script>', html, flags=re.S)
    robots = re.search(r'<meta name="robots" content="([^"]+)"', html)
    return {
        "title": title.group(1) if title else "",
        "desc": desc.group(1) if desc else "",
        "canonical": canonical.group(0) if canonical else "",
        "jsonld": "\n".join(jsonld),
        "robots": robots.group(1) if robots else "index, follow",
    }


def _inject_heading_ids(inner):
    """Deterministic, unique, diacritic-safe heading IDs. Idempotent."""
    used = {}
    heads = list(re.finditer(r"<(h[23])([^>]*)>(.*?)</\1>", inner, flags=re.S))
    out, last = [], 0
    for m in heads:
        tag, attrs, body = m.group(1), m.group(2), m.group(3)
        if re.search(r'\bid="[^"]+"', attrs):
            out.append(inner[last:m.start()])
            out.append(m.group(0))
            last = m.end()
            continue
        base = "sec-" + _slug(_tag_text(body))
        n = used.get(base, 0) + 1
        used[base] = n
        hid = base if n == 1 else f"{base}-{n}"
        out.append(inner[last:m.start()])
        out.append(f'<{tag}{attrs} id="{hid}">{body}</{tag}>')
        last = m.end()
    out.append(inner[last:])
    return "".join(out)


def _wrap_sources(inner):
    """Wrap the writer's final 'Nguồn' H2 section in a styled aside. Idempotent."""
    if '<aside class="sources-box"' in inner:
        return inner
    m = None
    for m in re.finditer(r"<h2[^>]*>\s*Nguồn\s*</h2>", inner):
        pass
    if not m:
        return inner
    fresh = '<aside class="sources-box" aria-label="Nguồn tham khảo">' + inner[m.start():] + "</aside>"
    return inner[:m.start()] + fresh


def _meta_row(row, region):
    if 'id="article-meta"' in region:
        return region
    minutes = max(1, round(_word_count(region) / 180))
    pub = row.get("published_date") or ""
    author = row.get("author") or ""
    bits = []
    if author:
        bits.append(f'<span class="font-semibold text-gray-700 dark:text-gray-200">{author}</span>')
    if pub:
        bits.append(f'<span class="text-gray-500 dark:text-gray-400">{_fmt_date(pub)}</span>')
    bits.append(f'<span class="text-gray-500 dark:text-gray-400">{minutes} phút đọc</span>')
    row_html = '<span class="meta-dot" aria-hidden="true">•</span>'.join(bits)
    meta = (f'\n<div id="article-meta" class="article-meta text-gray-500 dark:text-gray-400 mb-6 mt-3" role="group" aria-label="Thông tin bài viết">'
            f'{row_html}</div>')
    m = re.search(r"</h1>", region)
    if not m:
        return region
    return region[:m.end()] + meta + region[m.end():]


def _fmt_date(iso):
    months = ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"]
    y, mth, d = (iso.split("-") + ["", "", ""])[:3]
    if not (y and mth and d):
        return iso
    try:
        return f"{int(d):02d}/{int(mth):02d}/{y}"
    except ValueError:
        return iso


def _toc_entries(article_html):
    """TOC from article H2/H3, excluding the sources aside."""
    body = re.sub(r'<aside class="sources-box".*?</aside>', "", article_html, flags=re.S)
    entries = []
    for m in re.finditer(r"<(h[23])[^>]*id=\"([^\"]+)\"[^>]*>(.*?)</\1>", body, flags=re.S):
        level = 3 if m.group(1) == "h3" else 2
        text = _tag_text(m.group(3))
        if not text or text.lower() == "nguồn":
            continue
        entries.append((level, m.group(2), text))
    return entries


def _toc_html(entries, list_id):
    items = "\n".join(
        f'<a class="{"toc-level-3" if lvl == 3 else "toc-level-2"}" href="#{hid}">{text}</a>'
        for lvl, hid, text in entries)
    return f'<ol id="{list_id}" class="toc-list list-none space-y-0.5 border-l-2 pl-0 my-0">{items}</ol>'


def _related(row, published_sorted):
    same = [r for r in published_sorted
            if r["category"] == row["category"] and r["article_id"] != row["article_id"]]
    if not same:
        return ""
    idx = next((i for i, r in enumerate(same) if r["article_id"] == row["article_id"]), -1)
    order = same[idx + 1:] + same[:idx + 1] if idx >= 0 else same
    cards = []
    for r in order[:3]:
        date = (f'<span class="block text-xs text-gray-400 dark:text-gray-500 mt-1.5">{_fmt_date(r["published_date"])}'
                f'</span>') if r.get("published_date") else ""
        cards.append(
            f'<a class="related-card" href="{pathlib.Path(r["output_path"]).name}">'
            f'<span class="block text-xs font-semibold text-brand-600 dark:text-brand-400 mb-1">'
            f'{HUB_NAMES.get(r["category"], r["category"])}</span>'
            f'<span class="block text-sm font-bold text-gray-900 dark:text-white">{r["working_title"]}</span>'
            f'{date}</a>')
    if not cards:
        return ""
    cat_name = HUB_NAMES.get(row["category"], row["category"])
    return f'''
<section class="related-articles mt-12 max-w-3xl mx-auto px-0" aria-label="Đọc tiếp">
    <h2 class="text-lg font-bold text-gray-900 dark:text-white mb-4">Đọc tiếp</h2>
    <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">{"".join(cards)}</div>
</section>'''


def _back_to_hub(row):
    hub = fc.CATEGORIES[row["category"]]
    name = HUB_NAMES.get(row["category"], row["category"])
    return (f'\n<p class="hub-backlink mt-10 text-sm">'
            f'<a href="../../{hub}" class="inline-flex items-center gap-1.5 font-semibold text-brand-600 dark:text-brand-400 hover:underline">'
            f'<i aria-hidden="true" class="fas fa-arrow-left text-xs"></i> Xem thêm bài viết chuyên mục {name}</a></p>')


def _cta(row):
    target = row["commercial_link_target"]
    return f'''
<section class="article-cta mt-12 max-w-3xl mx-auto" aria-label="Liên hệ dịch vụ">
    <div class="glass-panel rounded-2xl p-6 md:p-8 text-center">
        <h2 class="text-xl md:text-2xl font-bold text-gray-900 dark:text-white mb-2">Cần thuê xe máy tại Hà Nội?</h2>
        <p class="text-gray-600 dark:text-gray-300 mb-5 text-sm">Xem bảng giá niêm yết hoặc liên hệ trực tiếp trong giờ mở cửa {fc.FACTS["opening_hours"]["display"]}.</p>
        <div class="flex flex-col sm:flex-row justify-center gap-3">
            <a href="tel:{fc.FACTS["phone_tel"]}" class="min-h-11 px-6 py-3 bg-brand-600 hover:bg-brand-700 text-white font-bold rounded-lg shadow-md transition-colors"><i aria-hidden="true" class="fas fa-phone mr-2"></i>{fc.FACTS["phone"]}</a>
            <a href="{fc.FACTS["zalo"]}" target="_blank" rel="noopener noreferrer" class="min-h-11 px-6 py-3 bg-white/70 dark:bg-gray-700/70 border border-gray-300/60 dark:border-gray-600/60 text-gray-800 dark:text-gray-100 font-bold rounded-lg hover:bg-white dark:hover:bg-gray-700 transition-colors"><i aria-hidden="true" class="fas fa-comment-dots mr-2 text-blue-500"></i>Chat Zalo</a>
            <a href="../../{target}" class="min-h-11 px-6 py-3 bg-white/70 dark:bg-gray-700/70 border border-gray-300/60 dark:border-gray-600/60 text-gray-800 dark:text-gray-100 font-bold rounded-lg hover:bg-white dark:hover:bg-gray-700 transition-colors"><i aria-hidden="true" class="fas fa-tags mr-2 text-brand-600 dark:text-brand-400"></i>Xem bảng giá</a>
        </div>
    </div>
</section>'''


def _freshness_line(row):
    lc = (row.get("last_checked") or "").strip()
    if not lc:
        return ""
    return (f'\n<p class="text-xs text-gray-500 dark:text-gray-400 mt-2 mb-2">'
            f'<i aria-hidden="true" class="fas fa-check-circle mr-1 text-green-600 dark:text-green-400"></i>'
            f'Thông tin được kiểm tra lần cuối: {_fmt_date(lc)}.</p>')


def _freshness_in_sources(article_html, row):
    if 'id="legal-freshness"' in article_html:
        return article_html
    line = _freshness_line(row)
    if not line:
        return article_html
    m = re.search(r'(<aside class="sources-box"[^>]*>.*?</h2>)', article_html, flags=re.S)
    if not m:
        return article_html
    line = line.replace("<p ", '<p id="legal-freshness" ', 1)
    return article_html[:m.end(1)] + line + article_html[m.end(1):]


def build_page(row, published_sorted, chrome):
    path = fc.ROOT / row["output_path"]
    html = path.read_text(encoding="utf-8")
    head = _extract_head(html)
    m = re.search(r"<article[^>]*>(.*)</article>", html, flags=re.S)
    if not m:
        print(f"ERROR: no <article> region in {path}")
        return None
    inner = m.group(1)
    inner = _meta_row(row, inner)
    inner = _inject_heading_ids(inner)
    inner = _wrap_sources(inner)
    inner = _freshness_in_sources(inner, row)
    article_html = f"<article class=\"article-prose max-w-none\">{inner}</article>"
    entries = _toc_entries(article_html)
    toc_desktop = _toc_html(entries, "toc-desktop-list")
    toc_mobile = _toc_html(entries, "toc-mobile-list")

    title = head["title"]
    page = f'''<!DOCTYPE html>
<html lang="vi" class="scroll-smooth">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{head['desc']}">
<meta name="robots" content="{head['robots']}">
{head['canonical']}
<meta property="og:type" content="article">
<meta property="og:site_name" content="Văn Chính - Cho Thuê Xe Máy Hà Nội">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{head['desc']}">
<meta property="og:locale" content="vi_VN">
<meta name="theme-color" content="#2563eb">
<link rel="icon" type="image/png" href="../../IMG_0999.png">
<script src="https://cdn.tailwindcss.com"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" crossorigin="anonymous">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@300;400;500;600;700;900&display=swap" rel="stylesheet">
<link rel="stylesheet" href="../../assets/css/main.css">
<script src="../../assets/js/tailwind-config.js"></script>
<script src="../../assets/js/main.js" defer></script>
<script src="../../assets/js/article.js" defer></script>
{head['jsonld']}
</head>
<body class="bg-gray-50 text-gray-800 dark:bg-gray-900 dark:text-gray-100 transition-colors duration-300 relative">
{SHELL_MARK}
<a href="#main" class="sr-only focus:not-sr-only p-2 absolute z-[9999] bg-white text-brand-600">Bỏ qua tới nội dung chính</a>
<div class="ambient-bg"></div>
{chrome['header']}
{chrome['widget']}
{chrome['sidebar']}
<div id="reading-progress" class="reading-progress" aria-hidden="true"></div>
<main id="main" class="pt-20">
    <div class="article-layout container mx-auto px-4 py-8 md:py-12 relative z-10">
        <div class="min-w-0">
            <details class="toc-mobile lg:hidden mb-6 rounded-xl border border-gray-200/80 dark:border-gray-700/80 bg-white/60 dark:bg-gray-800/60">
                <summary class="toc-toggle flex items-center justify-between px-4 py-3 cursor-pointer font-semibold text-gray-800 dark:text-gray-100 select-none" id="toc-mobile-btn" aria-controls="toc-mobile-list">
                    <span><i aria-hidden="true" class="fas fa-list-ul mr-2 text-brand-500"></i>Mục lục bài viết</span>
                    <svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M6 9l6 6 6-6"/></svg>
                </summary>
                <div class="px-4 pb-4">
                    <nav aria-label="Mục lục">{toc_mobile}</nav>
                </div>
            </details>
{article_html}
{_back_to_hub(row)}
{_related(row, published_sorted)}
{_cta(row)}
        </div>
        <aside class="toc-rail hidden lg:block" aria-label="Mục lục">
            <p class="toc-title text-gray-500 dark:text-gray-400 mb-3">Mục lục</p>
            <nav aria-label="Mục lục">{toc_desktop}</nav>
        </aside>
    </div>
</main>
{chrome['footer']}
</body>
</html>
'''
    return page


def main():
    rows = fc.load_matrix()
    published = sorted((r for r in rows if r["status"] == "PUBLISHED"),
                       key=lambda r: (r["batch_id"], r["article_id"]))
    chrome = {
        "header": _rel_attrs(bp.header()),
        "widget": _rel_attrs(bp.contact_widget()),
        "sidebar": _rel_attrs(bp.sidebar()),
        "footer": _rel_attrs(bp.footer()),
    }
    built, skipped, failed = 0, 0, 0
    for row in published:
        path = fc.ROOT / row["output_path"]
        if not path.exists():
            print(f"ERROR: published row without file: {row['article_id']}")
            failed += 1
            continue
        page = build_page(row, published, chrome)
        if page is None:
            failed += 1
            continue
        current = path.read_text(encoding="utf-8")
        if current == page:
            skipped += 1
            continue
        path.write_text(page, encoding="utf-8")
        built += 1
    print(json.dumps({"built": built, "unchanged": skipped, "failed": failed,
                      "total_published": len(published)}))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
