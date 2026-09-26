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

## Điểm và gates

- PASS: 90–100 và không critical.
- REVIEW: 80–89 và không critical → REPAIR rồi chấm lại (tối đa 3 lần → BLOCKED).
- FAIL: ≤ 79 hoặc bất kỳ critical nào.

Trọng số chi tiết trong `config/article-rubric.json`.

## Forbidden unsupported claims (cấm xuất hiện)

- "cọc 0đ" / "coc 0 dong"
- Cam kết "giao xe 15 phút" / "giao 24/7" / "hỗ trợ 24/7" / "cứu hộ 24/24"
- "số 1" (thị phần/thủ đô), "hàng ngàn khách hàng"
- Cam kết giao miễn phí theo bán kính, cam kết giảm giá, cam kết cứu hộ
- Giờ mở cửa khác 09:00–17:00 hàng ngày

Ngoại lệ ngữ cảnh: khi bàn về giới hạn tốc độ, quy định giao thông vận tải 24/7 của nhà nước, giờ tàu/vé tham quan… — KHÔNG đụng đến giờ mở cửa của Văn Chính.
