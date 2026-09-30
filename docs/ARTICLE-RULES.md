# Chuẩn viết bài (editorial standard)

Source of truth chấm điểm: `config/article-rubric.json`.

## Kích thước

- Dải mục tiêu: **1.600–2.000 từ** tiếng Việt hữu ích, không padding/filler.
- 1.200–1.599 hoặc 2.001–2.300 → REVIEW.
- < 1.200 hoặc > 2.300 → FAIL.

## Yếu tố bắt buộc mỗi bài production

- Đúng MỘT intent chính (primary_keyword trong matrix), KHÔNG xâm phạm intent thương mại được bảo vệ (config/seo-ownership.json).
- Đúng MỘT H1. Title unique, meta description unique.
- Self-canonical: `https://thuexemayhanoi.github.io/vanchinh/cam-nang/<folder>/<file>`.
- `lang="vi"`.
- Article JSON-LD + BreadcrumbList. Author + date metadata.
- Đường dẫn file đúng `output_path` trong matrix (URL ổn định, deterministic).
- 3–5 internal editorial links với anchor đa dạng, mô tả (không "click here").
- Bắt buộc link về parent hub đúng category.
- Tối đa 1 link đến trang thương mại (theo `commercial_link_target` của dòng matrix) trừ khi rubric cho phép khác.
- Không broken link; không đoạn văn trùng lặp; không ký tự lạ (Trung/Nga/không đọc được).
- Không fact kinh doanh bịa: giá, giờ mở cửa, chính sách cọc/giao/cứu hộ phải khớp `config/business-facts.json` (giờ mở cửa 09:00–17:00 hàng ngày).
- Khi `requires_sources=true`: có section nguồn + semantic source validation (xem dưới).

## Source / legal gate (requires_sources=true)

KHÔNG pass chỉ vì có URL government. Kiểm chứng chuỗi:

CLAIM → SUBJECT → VEHICLE TYPE/PERSON TYPE → CONDITION → VALUE/RULE → EFFECTIVE DATE/VERSION → PRIMARY SOURCE

Lỗi critical:

- Bảng tốc độ luật xe ô tô dùng cho claim xe máy.
- Hạng giấy phép đã hết hạn trình bày như hiện hành.
- Luật/văn bản hết hiệu lực trích dẫn không ngữ cảnh.
- Diễn giải IDP sai.
- Mức phạt bịa.
- Claim pháp lý hiện hành không trích nguồn.

Ưu tiên nguồn chính thức VN (thuvienphapluat, cơ quan ban hành). Sai lệch critical → FAIL/REVIEW bất kể điểm tổng.

## SEO score 0–100 (gate thứ hai, độc lập)

`scripts/score_article_seo.py` chấm deterministic, tổng 100:

- Technical 20 (canonical, lang, title, meta, 1 H1, indexable, content crawlable)
- Intent/on-page 25 (keyword trong title/intro/heading, trả lời trực tiếp, không cannibalize intent thương mại)
- Structure 20 (H2/H3, đoạn đọc được, độ sâu, không trùng lặp, kết luận)
- Internal linking 15 (parent hub, 3–5 editorial, <=1 commercial, anchor đa dạng, không broken)
- Structured data 10 (Article, BreadcrumbList, author, datePublished, mainEntityOfPage)
- AI/GEO readiness 10 (đoạn trả lời ngắn, fact nhất quán, list rõ ràng, không nhồi từ khóa)

Bands: PASS >= 80, REVIEW 70–79, FAIL < 70. Publish yêu cầu quality PASS VÀ SEO >= 80. Critical failure luôn override SEO score.

Writer được tự tối ưu (title, meta, intro, H2/H3, đoạn trùng/filler, internal links, anchor, schema, kết luận, đoạn trả lời trực tiếp, wording) nhưng KHÔNG BAO GIỜ bịa fact/giá/giờ mở cửa/chính sách/pháp lý/nguồn. requires_sources=true mà không kiểm chứng được → REVIEW/BLOCKED.

## Điểm và gates

- PASS: 80–100 và không critical.
- REVIEW: 70–79 và không critical → REPAIR rồi chấm lại (tối đa 3 lần → BLOCKED).
- FAIL: ≤ 69 hoặc bất kỳ critical nào.

Trọng số chi tiết trong `config/article-rubric.json`.

## Forbidden unsupported claims (cấm xuất hiện)

- "cọc 0đ" / "coc 0 dong"
- Cam kết "giao xe 15 phút" / "giao 24/7" / "hỗ trợ 24/7" / "cứu hộ 24/24"
- "số 1" (thị phần/thủ đô), "hàng ngàn khách hàng"
- Cam kết giao miễn phí theo bán kính, cam kết giảm giá, cam kết cứu hộ
- Giờ mở cửa khác 09:00–17:00 hàng ngày

Ngoại lệ ngữ cảnh: khi bàn về giới hạn tốc độ, quy định giao thông vận tải 24/7 của nhà nước, giờ tàu/vé tham quan… — KHÔNG đụng đến giờ mở cửa của Văn Chính.
## Article shell (lớp UI do tooling quản lý)

WRITER chỉ cam kết file bài BARE: `<head>` (title, meta description, robots, self-canonical, Article JSON-LD, BreadcrumbList JSON-LD) + `<main id="main">` chứa đúng MỘT `<article>` (breadcrumb nav, H1, body H2/H3, section "Nguồn" khi requires_sources). Không tự thêm chrome site (header/footer/sidebar/TOC/related/CTA) vào file bài — lớp đó là derived UI state.

`scripts/build_article_shell.py` (chạy trong publish transaction, idempotent, deterministic) bọc MỚI article PUBLISHED bằng chrome chuẩn site và thêm: heading ID deterministic (`sec-<slug>`, không dấu, dedupe), mục lục (desktop rail + mobile `<details>`), meta row (author, published_date, reading time tính từ chữ), sources box, dòng kiểm tra pháp lý (chỉ khi `last_checked` trong matrix truthy), back-link parent hub, 3 related card cùng category, CTA dùng `config/business-facts.json` (KHÔNG hard-code phone/hỗ trợ/giá/giờ).

Contract QA: content QA (link classification, word count, anchors, paragraphs, sources) chạy trong vùng `<article>` (`factory_common.article_region`) — shell chrome không bao giờ nhiễm vào điểm. Head/schema check chạy toàn file. Shell không đổi title/meta/canonical/JSON-LD (verbatim) và không đổi prose.

Không tự sửa tay file bài đã bọc shell: sửa "bare" không còn tồn tại sau publish — khi cần repair, sửa trong vùng `<article>` rồi chạy lại `build_article_shell.py` (idempotent).
