# Kiến trúc site tĩnh Văn Chính

## Tổng quan

GitHub Pages project site, thuần tĩnh, không backend/database/build framework. Site đa trang được sinh bằng `tools/build_pages.py` (Python stdlib) từ các section nguồn trong `sections/` — chạy lại tool tái tạo tất cả trang một cách deterministic.

## Cấu trúc trang

26 trang HTML:

- **Trang chủ/khách hàng**: index.html (homepage, không chứa toàn site)
- **Thương mại**: gioithieu, banggia, lienhe, faq, thutuc, chinhsach, baomat, dieukhoan
- **Khu vực**: longbien, gialam, hoankiem, phoco, badinh, tayho, haibatrung, xedien
- **Thời hạn thuê**: thuengay, thuetuan, thuethang
- **Hub thông tin**: kinhnghiem, antoan, xemay, dulich, cungduong, hoidap (mỗi hub liệt kê bài PUBLISHED của category đó, sinh bằng `scripts/generate_hub_lists.py`)

Bài viết tương lai: file HTML riêng dưới `cam-nang/<folder-category>/<id>-<slug>.html`.

## Assets dùng chung

| File | Nội dung |
|------|----------|
| assets/css/main.css | Toàn bộ CSS custom + Tailwind directive (CDN script) |
| assets/js/tailwind-config.js | tailwind.config inline |
| assets/js/main.js | Theme toggle, sidebar, quick-contact widget, footer accordion, giá/thời gian calculator — mỗi block tự guard theo sự tồn tại của DOM node |
| assets/js/assistant.js | Assistant ảo; fetch config/business-facts.json; fallback trung tính khi thiếu config. Không hard-code fact kinh doanh. DOMPurify + marked chỉ load ở index.html |

Trang không dùng assistant không nạp assistant + thư viện sanitize.

## Quy ước HTML

- Một H1 duy nhất mỗi trang (sinh bằng `page_h1()` trong build tool).
- Head: charset, viewport, title unique, meta description unique, canonical `https://thuexemayhanoi.github.io/vanchinh/<path>`, og:url cùng canonical.
- lang="vi". JSON-LD: LocalBusiness (index/khu vực/giới thiệu/bảng giá/liên hệ) + BreadcrumbList khi phù hợp.
- Giờ mở cửa trong schema: `09:00`–`17:00` cả 7 ngày trong tuần.
- Link nội bộ tương đối cùng cấp (index dùng `href="gioithieu.html"`, bài viết dùng `../../`).

## Tái tạo site

```bash
python3 tools/build_pages.py          # sinh 26 trang từ sections/
python3 scripts/generate_hub_lists.py # cập nhật danh sách bài trong hub
python3 scripts/generate_sitemap.py   # sinh sitemap.xml
python3 scripts/validate_site.py      # kiểm tra sau khi sinh
```

## Sitemap / robots

- sitemap.xml: chỉ trang thương mại + hub hiện hữu + bài PUBLISHED. Base đúng `/vanchinh/`.
- robots.txt: cho phép nội dung công khai, chặn thư mục nội bộ (data/, config/, scripts/, tools/, tests/, reports/, sections/), trỏ đúng sitemap.
