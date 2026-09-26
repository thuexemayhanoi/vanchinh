# SEO Ownership

Source of truth: `config/seo-ownership.json`.

## Nguyên tắc

1. Mỗi trang thương mại sở hữu MỘT primary intent. Không tạo doorway page gần-trùng.
2. Bài viết thông tin KHÔNG được nhắm primary_keyword trùng intent được bảo vệ (`check_cannibalization.py` chặn).
3. Bài viết tối đa 1 link thương mại, đến đúng `commercial_link_target` của category:
   - KN, XM → index.html
   - AT → banggia.html
   - DL → thuengay.html
   - CD → thuethang.html
   - HD → lienhe.html
4. Mỗi bài thuộc đúng MỘT category; parent hub link bắt buộc.

## Bảng sở hữu thương mại

| Trang | Intent chính |
|-------|--------------|
| index.html | cho thuê xe máy Hà Nội / thương hiệu Văn Chính |
| gioithieu.html | about/brand |
| banggia.html | giá thuê xe máy |
| lienhe.html | liên hệ |
| faq.html | hỏi đáp thuê xe máy |
| longbien.html | thuê xe máy Long Biên |
| gialam.html | thuê xe máy Gia Lâm |
| hoankiem.html | thuê xe máy Hoàn Kiếm |
| phoco.html | thuê xe máy Phố Cổ |
| badinh.html | thuê xe máy Ba Đình |
| tayho.html | thuê xe máy Tây Hồ |
| haibatrung.html | thuê xe máy Hai Bà Trưng |
| xedien.html | thuê xe điện Hà Nội |
| thuengay.html | thuê xe máy theo ngày |
| thuetuan.html | thuê xe máy theo tuần |
| thuethang.html | thuê xe máy theo tháng |
| thutuc.html | thủ tục thuê xe |
| chinhsach.html | chính sách |
| baomat.html | bảo mật |
| dieukhoan.html | điều khoản |

## Hub thông tin

kinhnghiem.html (KN), antoan.html (AT), xemay.html (XM), dulich.html (DL), cungduong.html (CD), hoidap.html (HD). Hub chỉ liệt kê bài PUBLISHED; không dồn body bài vào hub.

## Navigation taxonomy (3 nhóm UI / 6 category chuẩn)

UI công khai (menu + footer) hiển thị đúng 3 nhóm "Cẩm Nang"; factory giữ nguyên 6 category chuẩn. Source of truth: `navigation_groups` trong `config/seo-ownership.json`.

| Nhóm UI | Category | Hub |
|---------|----------|-----|
| Thuê xe & Hỏi đáp | KN, HD | kinhnghiem.html, hoidap.html |
| Xe máy & An toàn | XM, AT | xemay.html, antoan.html |
| Du lịch & Cung đường | DL, CD | dulich.html, cungduong.html |

Quy tắc:

- Menu/footer chỉ link tới hub/nhóm; không link bài viết riêng lẻ từ 2.000 bài vào nav/footer.
- Một category thuộc đúng MỘT nhóm; một hub thuộc đúng MỘT nhóm; không chồng lấn sở hữu category.
- Không thêm nhóm UI/category top-level mới không qua phê duyệt; các run scheduled phải bảo toàn mapping này (`validate_nav_taxonomy()` chặn vi phạm).

## Canonical

- Mọi trang: canonical = `https://thuexemayhanoi.github.io/vanchinh/` + path thật. Unique toàn site, khớp path.
- Cấm domain `chothuexemayohanoi.github.io`.
