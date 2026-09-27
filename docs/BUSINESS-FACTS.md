# Business Facts & Quy tắc xác minh

Source of truth: `config/business-facts.json`. Không bịa fact. Site và assistant phải đọc từ config này, không hard-code bản sao.

## Fact đã xác minh (verified_at: 2026-09-26, từ nội dung đã publish của chính site)

- business_name: Thuê xe máy Văn Chính
- public_site: https://thuexemayhanoi.github.io/vanchinh/
- phone: 0989.595.533 (hotline)
- support_url: https://thuexemayhanoi.github.io/aichatbot/ (Hỗ Trợ, agent online)
- email: vanchinhnguyen1702@gmail.com
- address: Số 24 Ngõ 5 Nguyễn Văn Cừ, Ngọc Lâm, Long Biên, Hà Nội
- coordinates: 21.0400942, 105.8664156
- **opening_hours: 09:00–17:00 HÀNG NGÀY (kể cả cuối tuần).** Giờ duy nhất hợp lệ trong toàn repo.
- prices: các mức theo loại xe/thời hạn công khai trên banggia.html — chỉ trích mức có trong config; không bịa giá.
- deposit_policy: cọc theo loại xe, hoàn trả khi trả xe đúng hiện trạng. KHÔNG phải "cọc 0đ".
- delivery_policy: có giao xe tận nơi; KHÔNG cam kết 15 phút, KHÔNG cam kết miễn phí bán kính — thời gian/chi phí xác nhận khi đặt xe.
- insurance_policy: xe có bảo vệ/duy trì theo kỳ; chi tiết xác nhận khi nhận xe (không cam kết bảo hiểm cá nhân cho khách).
- licence_policy: khách cần CCCD/hộ chiếu + giấy phép lái xe hợp lệ.
- rescue/support policy: hỗ trợ qua hotline trong giờ mở cửa 09:00–17:00. KHÔNG cam kết 24/7.

## Unverified — KHÔNG đưa thành fact công khai

- "Cơ sở 2 tại 76 Tạ Hiện" (ghi chú trong trang cũ, không kiểm chứng được → đã bỏ khỏi site).
- Mọi claim "số 1", "hàng ngàn khách", cam kết giảm giá.

## Quy tắc

1. Muốn thêm/sửa fact → phải có nguồn kiểm chứng (trang chính thức, tài liệu shop, xác nhận chủ). Ghi `verification_notes`.
2. Không thể kiểm chứng → gỡ hoặc làm mềm claim công khai; đánh dấu `unverified` trong audit. KHÔNG âm thầm nâng thành "fact".
3. Giờ mở cửa chỉ xuất hiện một dạng: 09:00–17:00 hàng ngày. Cấm 24/7, 9h–21h, 8h–17h cho Văn Chính (giờ tàu, giờ tham quan, quy định vận tải nhà nước 24/7 là ngoại lệ ngữ cảnh, không được sửa).
4. Assistant ảo đọc config qua fetch; fallback trung tính khi không tải được — không biến assistant thành nguồn sự thật song song.
