# Audit Checklist (trước push)

Chạy từ repo root. Mọi mục critical phải PASS trước khi push.

## 1. Fact / domain / hours

- [ ] `grep -r "chothuexemayohanoi" --include="*.html"` → 0 kết quả
- [ ] `grep -ri "24/7\|24/24\|9h-21h\|9h–21h\|8h-17h\|8h–17h\|09:00-21:00\|08:00-17:00" *.html assets/` → không có giờ mở cửa sai của Văn Chính (ngoại lệ ngữ cảnh vận tải/nhà nước phải được soát)
- [ ] `grep -ri "cọc 0đ\|coc 0 dong\|giao 15 phút\|hàng ngàn\|so 1" *.html` → 0 claim không hỗ trợ
- [ ] config/business-facts.json: opening_hours = 09:00–17:00 daily

## 2. Site quality

- [ ] `python3 scripts/validate_site.py` → errors=0 (26+ trang: 1 H1, title, description, canonical unique + khớp path, không broken local link/asset)

## 2b. Navigation taxonomy

- [ ] Đúng 3 nhóm UI "Cẩm Nang" trong sidebar + footer của MỌI trang; mapping KN/HD — XM/AT — DL/CD đúng
- [ ] Menu/footer KHÔNG chứa link bài viết (`href="cam-nang/"`) hay link listing page
- [ ] 6 hub chuẩn tồn tại; hub list khớp Matrix PUBLISHED; listing page `<hub>-trang-*.html` không mồ côi
- [ ] Không category/hub top-level mới ngoài 6 category chuẩn

## 3. Factory

- [ ] `python3 scripts/validate_content_matrix.py` → 2000 rows, 40×50, id/path unique, category hợp lệ
- [ ] `node scripts/validate_content_matrix.mjs` → exit 0
- [ ] `python3 scripts/check_cannibalization.py` → không keyword xâm phạm intent bảo vệ
- [ ] Không txn marker pending (`data/batches/txn/txn.json` không tồn tại ngoài lúc publish)
- [ ] Không lock active
- [ ] reports/batches/factory-progress.json khớp matrix (derived, không hard-code)

## 4. Test suite

- [ ] `python3 tests/run_tests.py` → 0 failed

## 5. Sitemap / robots

- [ ] sitemap.xml: chỉ PUBLISHED + trang hiện hữu, đúng base `/vanchinh/`, không duplicate
- [ ] robots.txt trỏ đúng sitemap, không chặn nội dung công khai

## 6. Sau push

- [ ] Verify remote HEAD (SHA + message khớp local commit)
- [ ] Verify Pages deployment: mở https://thuexemayhanoi.github.io/vanchinh/ và một trang con, kiểm canonical + giờ 09:00–17:00 hiển thị đúng
