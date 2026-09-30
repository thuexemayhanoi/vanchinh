# Văn Chính — Cho Thuê Xe Máy Hà Nội (thuexemayhanoi/vanchinh)

Public site: https://thuexemayhanoi.github.io/vanchinh/

**README này là HĐỒNG VẬN HÀNH (operating contract) cho cả con người lẫn AI agent.**
**Mọi lần chạy Mistral trong tương lai BẮT BUỘC đọc README.md TRƯỚC TIÊN**, sau đó đọc docs/config/matrix liên quan trước khi thay đổi bất kỳ thứ gì. README không chỉ là tài liệu — nó là hợp đồng vận hành của nhà máy nội dung tự trị.

---

## 1. Mục đích dự án

Site marketing + hub nội dung cho dịch vụ cho thuê xe máy "Văn Chính" tại Long Biên, Hà Nội, triển khai trên GitHub Pages (thuần tĩnh, không backend, không database). Kèm theo là "content factory" xác định (deterministic) để sản xuất 2.000 bài viết tiếng Việt theo lô (batch), có QA tự động, recovery và resume.

## 2. Public base URL (source of truth)

```
https://thuexemayhanoi.github.io/vanchinh/
```

- Mọi canonical, og:url, schema url/@id, sitemap, internal absolute URL PHẢI dùng base này.
- Domain `chothuexemayohanoi.github.io` là SAI — đã bị xóa khỏi toàn bộ repo, không được tái xuất hiện.

## 3. Business facts đã xác minh

Xem file nguồn sự thật: `config/business-facts.json`. Tóm tắt:

- Tên: Thuê xe máy Văn Chính
- Hotline: 0989.595.533. Hỗ trợ online: https://thuexemayhanoi.github.io/aichatbot/
- Email: vanchinhnguyen1702@gmail.com
- Địa chỉ: Số 24 Ngõ 5 Nguyễn Văn Cừ, Ngọc Lâm, Long Biên, Hà Nội (geo 21.0400942, 105.8664156)
- **Giờ mở cửa: 09:00–17:00 HÀNG NGÀY.** KHÔNG dùng "24/7", "9h–21h", "8h–17h" cho giờ mở cửa/hỗ trợ.
- Cọc: theo loại xe (xem config), KHÔNG phải "cọc 0đ".
- Giao xe tận nơi: có, nhưng KHÔNG cam kết "15 phút" hay miễn phí bán kính; thời gian/chi phí xác nhận khi đặt xe.
- Cứu hộ: hỗ trợ qua hotline trong giờ mở cửa, KHÔNG cam kết 24/7.
- Các claim "số 1", "hàng ngàn khách", "giao 24/7", "cọc 0đ" đã bị gỡ khỏi site vì không có bằng chứng.

Quy tắc: KHÔNG bịa fact kinh doanh. Claim không xác minh được → gỡ hoặc làm mềm, ghi chú `unverified` trong config.

## 4. Kiến trúc hiện tại

Site tĩnh đa trang, sinh bằng `tools/build_pages.py` (chạy stdlib Python, không cần build framework):

- 20 trang thương mại (index, gioithieu, banggia, lienhe, faq, 7 khu vực, xedien, 3 thời hạn thuê, thutuc, chinhsach, baomat, dieukhoan)
- 6 hub thông tin: kinhnghiem, antoan, xemay, dulich, cungduong, hoidap — phân nhóm trong menu/footer thành đúng 3 nhóm "Cẩm Nang" (xem §7)
- Chi tiết: `ARCHITECTURE.md`

## 5. Shared assets

- `assets/css/main.css` — toàn bộ CSS dùng chung (Tailwind CDN + custom, dark mode)
- `assets/js/tailwind-config.js` — config Tailwind
- `assets/js/main.js` — theme, sidebar, contact widget, footer accordion, calculator (guarded theo từng trang)
- `assets/js/assistant.js` — assistant ảo, đọc `config/business-facts.json` qua fetch; KHÔNG hard-code fact kinh doanh. DOMPurify + marked chỉ load trên index.
- KHÔNG load assistant trên trang không dùng assistant.

## 6. Commercial landing-page ownership

Mỗi trang thương mại sở hữu MỘT intent chính — xem `config/seo-ownership.json` và `docs/SEO-OWNERSHIP.md`. Bài viết thông tin KHÔNG được cannibalize intent thương mại được bảo vệ.

## 7. Informational hub ownership & navigation taxonomy

6 hub cố định, mỗi bài viết thuộc đúng MỘT category:

| Mã | Hub | Folder bài viết |
|----|-----|------------------|
| KN | kinhnghiem.html | cam-nang/kinh-nghiem/ |
| AT | antoan.html | cam-nang/an-toan/ |
| XM | xemay.html | cam-nang/xe-may/ |
| DL | dulich.html | cam-nang/du-lich/ |
| CD | cungduong.html | cam-nang/cung-duong/ |
| HD | hoidap.html | cam-nang/hoi-dap/ |

Taxonomy có HAI tầng, không được trộn lẫn:

1. **UI navigation** (menu/footer): đúng 3 nhóm công khai "Cẩm Nang".
2. **Factory taxonomy**: đúng 6 category chuẩn ở trên. KHÔNG thu gọn Matrix về 3 category — 3 nhóm UI chỉ là cách nhóm hiển thị.

Mapping nhóm UI → category/hub (source of truth: `config/seo-ownership.json` → `navigation_groups`):

| Nhóm UI | Category | Hub |
|---------|----------|-----|
| Thuê xe & Hỏi đáp | KN, HD | kinhnghiem.html, hoidap.html |
| Xe máy & An toàn | XM, AT | xemay.html, antoan.html |
| Du lịch & Cung đường | DL, CD | dulich.html, cungduong.html |

Quy tắc taxonomy (bất diệt):

- Menu/footer chỉ link tới hub/nhóm; KHÔNG BAO GIỜ đặt link bài viết riêng lẻ (từ 2.000 bài) vào main menu hoặc footer.
- Hub list sinh từ Matrix theo trạng thái PUBLISHED (`scripts/generate_hub_lists.py`); hub không được drift khỏi Matrix.
- Phân trang deterministic: mỗi trang hub hiển thị tối đa `HUB_PAGE_SIZE = 50` link; các trang tiếp theo là listing page `<hub>-trang-<n>.html` sinh tự nhiên và được dọn khi mồ côi; sitemap bao gồm listing page đang tồn tại.
- Không tự thêm category top-level mới và không tự thêm nhóm UI mới — thay đổi taxonomy cần phê duyệt.
- Mọi run scheduled trong tương lai PHẢI bảo toàn taxonomy này; `validate_nav_taxonomy()` (Python) và `validate_content_matrix.mjs` chặn vi phạm mapping.

## 8. Performance rules (bất diệt)

- Không crawling nền, không animation nặng liên tục.
- Không load thư viện AI/assistant ở trang không dùng.
- Không inline CSS/JS khổng lồ lặp lại trong mỗi HTML.
- Giữ nguyên deployment GitHub Pages tĩnh, không backend, không database.
- Trước refactor: index 116.662B, gioithieu 92.746B. Sau: index ~82KB, gioithieu ~44KB.

## 9. SEO rules

- Mỗi trang: đúng MỘT H1, title unique, meta description unique, self-canonical đúng base + path, lang=vi.
- Canonical phải khớp path thật của trang; không trùng canonical.
- Không doorway page gần-trùng nhau; không broken link nội bộ.

## 10. Source-of-truth files

| File | Vai trò |
|------|---------|
| config/business-facts.json | Fact kinh doanh duy nhất |
| config/seo-ownership.json | Intent thương mại + hub |
| config/article-rubric.json | Rubric 100 điểm + critical failures |
| data/content-matrix.csv | 2.000 dòng — trạng thái mọi bài viết |
| reports/batches/factory-progress.json | Progress (derived từ matrix, không hard-code) |
| sitemap.xml | Chỉ chứa URL PUBLISHED/thương mại hợp lệ |

**Repository truth thắng trí nhớ hội thoại.** Khi nghi ngờ: đọc repo.

## 11. Article factory architecture

- WRITER: Mistral/agent bên ngoài viết file bài viết thật. Không API key, không template giả.
- Tooling deterministic (Python stdlib, Node fallback) chuẩn bị manifest/state và QA.
- Chi tiết: `docs/CONTENT-FACTORY.md`.

## 12. Matrix state machine

```
PLANNED → WRITING → QA → PASS → PUBLISHED
                   QA → REVIEW → REPAIR → PASS
Terminal: FAIL, BLOCKED
```

- PASS chỉ khi mọi deterministic gate pass.
- PUBLISHED chỉ khi file bài viết + hub + sitemap + reports + matrix commit nhất quán (một transaction).
- Tối đa 3 lần REPAIR có ý nghĩa; vượt → BLOCKED. Bài FAIL không chặn bài PASS khác.

## 13. Writing standard

Xem `docs/ARTICLE-RULES.md` + `config/article-rubric.json`. Tóm tắt: 1.600–2.000 từ tiếng Việt hữu ích, 1 H1, self-canonical, Article JSON-LD + BreadcrumbList, 3–5 internal editorial link, link hub cha bắt buộc, tối đa 1 link thương mại, không claim kinh doanh bịa, source section khi requires_sources=true.

## 14. QA/scoring standard

Rubric 100 điểm: PASS 80–100 & không critical; REVIEW 70–79; FAIL ≤69 hoặc bất kỳ critical failure. Critical: canonical sai, path sai, bịa giá/chính sách, sai lệch nguồn pháp lý, cannibalization, corruption ký tự (TQ/Cyrillic), broken link, publish trạng thái không hợp lệ. Chi tiết weights trong `config/article-rubric.json`.

## 15. Source/legal verification rules

Với requires_sources=true KHÔNG pass chỉ vì có URL government. Phải kiểm chứng ngữ nghĩa: CLAIM → SUBJECT → VEHICLE/PERSON TYPE → CONDITION → VALUE/RULE → EFFECTIVE DATE → PRIMARY SOURCE. Ưu tiên nguồn chính thức VN. Sai lệch nghiêm trọng (bảng tốc độ ô tô dùng cho xe máy, luật hết hiệu lực, mức phạt bịa) → FAIL/REVIEW bắt buộc.

## 16. Publish transaction rules

Publish cập nhật nhiều file (article, matrix, hubs, sitemap, reports). Coi như transaction có marker `data/batches/txn/txn.json`: ghi marker → ghi file → kiểm consistency → chỉ xóa marker khi consistency PASS. Marker tồn tại → từ chối mutation mới; chạy `--recover` để hoàn tất/rollback an toàn.

## 17. Recovery rules

`python3 scripts/run_article_batch.py recover` đọc marker, hoàn tất các bước còn thiếu hoặc rollback, xóa marker khi nhất quán. Chi tiết: `docs/RECOVERY.md`.

## 18. Lock/concurrency rules

Run-lock tại `data/batches/lock.json` (operator, timestamp). Operator phải kiểm: remote HEAD, pending txn, active lock, active batch. Hai operator không được ghi/publish row chồng lấp. Stale lock chỉ được thu hồi khi expired, qua `FORCE_STALE_LOCK_RECOVERY=1`, và có ghi chú kiểm chứng rõ ràng.

## 19. Resume behavior (bắt buộc)

Mọi run KHÔNG được phụ thuộc trí nhớ hội thoại. Đầu mỗi run:

```
FETCH → READ README → READ MATRIX → READ REPORTS → CHECK LOCK → CHECK TXN → RESUME
```

Run trước đòi 50 nhưng xong 30 → run sau HOÀN TẤT 30 còn lại TRƯỚC, không claim lô mới, không vứt tiến độ dở.

## 20. GitHub Actions

- `site-quality.yml` — validate HTML/link/canonical khi push.
- `article-quality.yml` — tests + matrix validation + article validator khi thay đổi matrix/article/config.
- `article-quality.yml` sweep validator: bài viết hiện có fail validate → job FAIL (exit code != 0 được đếm).
- `article-batch.yml` — workflow_dispatch, read-only dry-run (plan/progress).
- `factory-publish-verify.yml` — workflow_dispatch, read-only publish dry-run verification.
- `factory-publish.yml` — publish pipeline tự động khi push lên `main` thêm/sửa file bài trong `cam-nang/`. Scope CHÍNH XÁC do `scripts/factory_push_selection.py` derive từ `git diff`: push THÊM file bài → claim đúng các ID có file (PLANNED, max 50, row chưa có file không bao giờ bị claim; >50 file mới → REFUSE); push SỬA file bài của row WRITING/QA/REVIEW/REPAIR/PASS → QA + publish đúng các ID được sửa (repair mode), KHÔNG claim row PLANNED mới; PLANNED đã có file mà push không chạm → backlog mode (≤50, deterministic). PUBLISHED row không bao giờ bị claim lại. Simple Production Mode: happy path chỉ gồm scoped QA + publish + light matrix smoke; KHÔNG chạy full test suite/validate_site/full-site cannibalization/node parity sau mỗi batch.
- Publish (`run_article_batch.py publish`) từ chối khi taxonomy vi phạm: category không hợp lệ, sai parent hub, sai mapping nhóm, hoặc menu/footer có link bài viết trực tiếp.
- KHÔNG cron cho AI writing. Scheduler ngoài (Mistral) lo phần đó. Actions luôn deterministic và an toàn.

## 21. Agent read order (mỗi content run)

1. README.md
2. docs/CONTENT-FACTORY.md
3. docs/ARTICLE-RULES.md
4. docs/SEO-OWNERSHIP.md
5. config/business-facts.json
6. config/article-rubric.json
7. config/seo-ownership.json
8. reports/batches/factory-progress.json
9. active batch report (reports/batches/Bxx.json nếu có)
10. data/content-matrix.csv

Sau đó resume theo trạng thái repo (lock, txn, batch đang active).

## 21b. Navigation cha/con (UI contract)

- Desktop (lg+): header có desktop nav với đúng 3 parent dropdown (Thuê xe & Hỏi đáp / Xe máy & An toàn / Du lịch & Cung đường), mỗi parent mở dropdown 2 hub con. Mở bằng hover (pointer fine), click và keyboard/focus (aria-expanded, aria-controls, Escape).
- Mobile drawer: KHÔNG hover dropdown; 3 parent là accordion (details/summary, aria-expanded sync), tap target >= 44px, dùng được tại 320px, dark mode đúng.
- Nguồn dữ liệu: `config/seo-ownership.json → navigation_groups` sinh deterministic qua `tools/build_pages.py` (`_nav_groups_from_config()`); không hard-code 2 bản độc lập.
- Dropdown/menu/footer chỉ link tới HUB, không bao giờ link bài viết riêng lẻ; bài viết đến từ breadcrumb → parent hub.
- Factory taxonomy vẫn là 6 category (KN/AT/XM/DL/CD/HD); 3 nhóm chỉ là UI grouping.

## 21c. Content factory production mode (Simple Production Mode)

- Chunk làm việc = 2 bài (MICRO CONTINUOUS LOOP): writer viết và push 2 bài mới mỗi lượt rồi lặp liên tục; mỗi cặp 2 bài được push sớm làm safe checkpoint chống mất tiến độ khi workspace reset. 40 batch × 50 bài = 2.000 dòng matrix. Hard max workflow giữ nguyên: một push ≤ 50 file bài mới. Production loop: WRITE 2 → SCOPED QA → PUSH 2 → WAIT CI → NEXT 2 → REPEAT. Không over-engineer workflow; full audit toàn site chỉ chạy một lần khi đủ 2.000 bài.
- Lệnh: `claim B01 --limit 50` (claim đúng 50 row PLANNED→WRITING, thứ tự deterministic batch+article_id), `qa B01 [--ids ...|--limit N]` (scoped QA), `publish B01` (grouped publish PASS).
- Invariant batch hiện tại: batch đang chạy PHẢI hoàn tất trước khi claim batch khác. `claim` từ chối mọi batch ≠ batch chưa hoàn thành đầu tiên (theo thứ tự matrix). Trạng thái terminal cho phép chuyển batch: PUBLISHED, BLOCKED, FAIL. Hệ quả: không bao giờ nhảy sang B02 khi B01 còn row chưa terminal; `next_batch` trong progress report CHỈ là batch kế tiếp chưa có bài published, KHÔNG phải quyền claim.
- Publish yêu cầu: quality PASS VÀ SEO score >= 80 VÀ không critical.
- Checkpoint: `data/batches/writer-checkpoint.json` (operational state; MATRIX > CHECKPOINT khi conflict).
- Throughput: `reports/batches/factory-throughput.json` (số thật, không ước lượng).
- SEO score: `scripts/score_article_seo.py` (0–100, deterministic; PASS>=80, REVIEW 70–79, FAIL<70). Reports: `reports/seo/articles/<id>.json` + `reports/seo/factory-seo-summary.json`.
- Bulk scoring: `scripts/score_chunk.py --batch B01 --limit 50`.
- Vòng đời: WRITE → quality score → SEO score → REPAIR (max 3) → re-score → publish nếu cả hai gate PASS.

## 21d. Blog/article UX shell (derived UI layer)

- WRITER cam kết file bài BARE (head + đúng một `<article>`); `scripts/build_article_shell.py` bọc MỘI bài PUBLISHED bằng chrome chuẩn site — cùng design language với các trang chính (glass header, sidebar, footer, contact widget, Tailwind CDN, dark mode). Shell là derived state: idempotent (chạy 2 lần byte-identical), deterministic, chạy trong publish transaction.
- Shell thêm: heading ID deterministic (`sec-<slug>`), mục lục tự sinh từ H2/H3 (desktop sticky rail 240px + mobile `<details>` collapsed, aria-controls, target ≥44px), meta row (author, ngày đăng, reading time), reading-progress bar (tắt với prefers-reduced-motion), sources box ("Nguồn" + dòng kiểm tra pháp lý chỉ khi `last_checked` truthy), back-link parent hub, 3 related card cùng category (deterministic, wrap-around), CTA resolve từ `config/business-facts.json` (không hard-code phone/hỗ trợ/giá).
- SEO contract giữ nguyên: title, meta description, canonical, Article JSON-LD, BreadcrumbList JSON-LD, prose KHÔNG đổi (verbatim). 0 URL/canonical thay đổi.
- Content QA (link classification, word count, anchors, paragraphs, sources) chạy trong vùng `<article>` (`factory_common.article_region()`); head/schema check chạy toàn file. Shell không ảnh hưởng điểm QA — đây là scoping chính đáng, không weaken QA.
- Hub category: card grid 1/2/3 cột (mobile/tablet/desktop), card `<a>` chứa category pill + title + ngày; pagination ← Trước / số (aria-current) / Sau →, crawlable, tối đa 50 link/trang giữ nguyên.
- Workflow gate: chỉ file bài MỚI THÊM (`--diff-filter=A`) trong cam-nang/ mới kích hoạt claim chunk; sửa bài (shell rebuild/UI/repair) không bao giờ trigger chunk mới.
- Chi tiết: docs/ARTICLE-RULES.md (§Article shell), docs/CONTENT-FACTORY.md (§Article shell), reports/audits/blog-ux-matrix.md.

## 22. Exact test commands

Từ repo root:

```bash
python3 tests/run_tests.py                 # full suite (>3.000 checks)
python3 scripts/validate_site.py           # HTML/link/canonical/hours/domain
python3 scripts/validate_content_matrix.py # matrix integrity
node scripts/validate_content_matrix.mjs   # Node fallback
python3 scripts/check_cannibalization.py   # intent ownership
```

Yêu cầu: Python 3 stdlib; Node 18+ cho fallback. Không dependency ngoài.

## 23. Hard rules

- Không bịa fact/giá/chính sách/pháp lý. Không claim SUCCESS/FIXED/PUBLISHED khi chưa kiểm chứng.
- Giờ mở cửa luôn là 09:00–17:00 hàng ngày.
- Base URL luôn là https://thuexemayhanoi.github.io/vanchinh/.
- Bài viết = file HTML riêng dưới cam-nang/, KHÔNG nhồi vào index.html.
- Không copy/spin nội dung từ repo `thuexemayhanoi/shop`.
- Không push khi test đỏ. Sau push: verify remote HEAD.
- Không tắt test để lấy kết quả xanh.

## 24. External writer behavior (continuous-run contract)

Writer là agent AI bên ngoài (Mistral run), KHÔNG phải GitHub Actions. Lịch chạy writer (nguồn bên ngoài, ví dụ Mistral scheduler, UTC+7) NẰM NGOÀI repo: repo không chứa scheduler AI, không API key, và GitHub Actions không bao giờ tự viết prose hay tự tạo chunk kế tiếp. Nếu session writer kết thúc, factory đứng yên ở trạng thái sạch cho tới khi một writer run mới được khởi động. Vì vậy MỌI writer run phải tuân theo continuous-run contract trong [docs/CONTINUOUS-WRITER.md](docs/CONTINUOUS-WRITER.md):

1. Fetch fresh main, đọc theo read order §21.
2. Kiểm lock/txn; nếu marker pending → recover trước.
3. Hoàn tất REPAIR/QA/PASS pending của batch active TRƯỚC khi làm work mới.
4. Viết 2 file bài mới (micro chunk chuẩn; phần dư cuối < 2 được phép), local scoped QA, push đúng cặp đó. Một push = một micro chunk 2 bài (≤ 50 file mới là hard max workflow).
5. Chờ `factory-publish.yml` chạy xong → verify CI/ Pages → fetch fresh main → LẶP LẠI NGAY cặp 2 bài kế tiếp. Batch active phải terminal trước khi sang batch khác.

Writer KHÔNG được dừng chỉ vì một cặp 2 bài vừa publish, một workflow xong, một Pages deploy xong, một batch xong, hay report được sinh ra — đó là checkpoint, không phải điểm kết thúc. Chỉ dừng khi: (a) toàn bộ 2.000 row terminal hợp lệ, (b) runtime/session buộc dừng tại điểm an toàn (không lock, không txn, fresh main), hoặc (c) blocker thật cần con người.

## 25. Recovery sau lỗi runtime/tool

Nếu run bị gián đoạn: trạng thái repo (matrix + reports + txn marker) là chuẩn. Chạy lại theo read order; dùng `recover` để xử lý marker; không vứt partial work. Bắt đầu bằng: `python3 scripts/run_article_batch.py recover && python3 tests/run_tests.py`.

---

## Bảng điều hướng tài liệu

- [ARCHITECTURE.md](ARCHITECTURE.md) — kiến trúc site tĩnh
- [docs/CONTENT-FACTORY.md](docs/CONTENT-FACTORY.md) — vận hành factory, lệnh batch
- [docs/ARTICLE-RULES.md](docs/ARTICLE-RULES.md) — chuẩn viết bài
- [docs/SEO-OWNERSHIP.md](docs/SEO-OWNERSHIP.md) — sở hữu intent thương mại
- [docs/BUSINESS-FACTS.md](docs/BUSINESS-FACTS.md) — fact kinh doanh + quy tắc xác minh
- [docs/RECOVERY.md](docs/RECOVERY.md) — transaction/lock/resume
- [docs/AUDIT-CHECKLIST.md](docs/AUDIT-CHECKLIST.md) — checklist audit trước push
- [reports/audits/audit-2026-09-26.md](reports/audits/audit-2026-09-26.md) — audit foundation run- [docs/BUSINESS-FACTS.md](docs/BUSINESS-FACTS.md) — fact kinh doanh
- [docs/RECOVERY.md](docs/RECOVERY.md) — transaction, lock, resume
- [docs/CONTINUOUS-WRITER.md](docs/CONTINUOUS-WRITER.md) — continuous-run contract cho external writer (micro loop 2 bài/lượt, không dừng sau mỗi cặp 2 bài)
- [docs/FACTORY-PUBLISH-WORKFLOW.md](docs/FACTORY-PUBLISH-WORKFLOW.md) — publish tự động
- [docs/AUDIT-CHECKLIST.md](docs/AUDIT-CHECKLIST.md) — checklist audit
- [AGENTS.md](AGENTS.md) — hợp đồng thực thi cho AI agent

## 26. Tiến độ hiện tại

KHÔNG hard-code số liệu tiến độ vào tài liệu. Số liệu authoritative luôn nằm ở `reports/batches/factory-progress.json` (sinh từ matrix) và `data/content-matrix.csv`. Lấy snapshot bằng:

```bash
python3 scripts/run_article_batch.py progress
python3 scripts/run_article_batch.py plan B01
```
