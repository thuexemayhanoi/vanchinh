# Content Factory — vận hành nhà máy 2.000 bài

## Tổng quan

Factory sản xuất 2.000 bài viết tiếng Việt theo lô, deterministic, resumable. WRITER là agent Mistral bên ngoài; tooling chỉ chuẩn bị manifest/state và QA. Không API key, không template giả, không bài spam.

## Matrix

`data/content-matrix.csv` — ĐÚNG 2.000 dòng production, 40 batch × 50 dòng.

Phân bổ category:

| Mã | Category | Số bài |
|----|----------|--------|
| KN | Kinh nghiệm | 350 |
| AT | An toàn | 300 |
| XM | Xe máy | 350 |
| DL | Du lịch | 400 |
| CD | Cung đường | 300 |
| HD | Hỏi đáp | 300 |

Mỗi dòng: article_id (KN-0001…), batch_id (B01–B40), category, status, primary/secondary keywords, search_intent, working_title, slug, output_path (`cam-nang/<folder>/<id>-<slug>.html`), parent_hub, requires_sources, source_policy, internal_link_targets, commercial_link_target, author, score, quality_status, repair_attempts, published_date, last_checked, notes.

Fixture (`tests/fixtures/`) nằm NGOÀI 2.000 dòng production — không bao giờ đếm vào.

Sinh lại matrix deterministic: `python3 tools/generate_content_matrix.py` (chỉ khi khởi tạo lại; không chạy khi đã có tiến độ production).

## State machine

```
PLANNED → WRITING → QA → PASS → PUBLISHED
QA → REVIEW → REPAIR → PASS   (tối đa 3 lần sửa)
Terminal: FAIL, BLOCKED
```

- PASS: mọi deterministic gate pass (score ≥ 90, không critical).
- PUBLISHED: sau khi file bài + hub + sitemap + reports + matrix commit nhất quán trong MỘT transaction.
- Bài FAIL/BLOCKED không chặn bài PASS khác trong cùng batch.

## Chunked writer mode (canonical)

Batch vẫn 50 bài; writer làm việc theo chunk pilot 5 → 10 bài:

```bash
python3 scripts/run_article_batch.py claim B01 --limit 5    # pilot chunk đầu
# writer viết 5 file; qa scoped; publish grouped; pilot xanh →
python3 scripts/run_article_batch.py claim B01 --limit 10   # chunk chuẩn (max 10)
python3 scripts/run_article_batch.py qa B01                 # scoped theo checkpoint current chunk
python3 scripts/run_article_batch.py publish B01            # grouped publish chunk hiện tại
python3 scripts/run_article_batch.py checkpoint             # xem trạng thái checkpoint
python3 scripts/run_article_batch.py throughput             # sinh factory-throughput.json
```

Quy tắc:

- claim chỉ chuyển đúng N row PLANNED → WRITING (không claim cả 50).
- qa scoped: chỉ chấm chunk hiện tại (checkpoint) hoặc --ids tường minh; row không chạm giữ nguyên trạng thái.
- Row WRITING không có file trong chunk hiện tại → REPAIR/BLOCKED, không phá trạng thái batch khác.
- PUBLISHED không bao giờ bị claim lại.
- INVARIANT batch hiện tại: batch đang chạy phải hoàn tất trước khi claim batch khác. `claim` từ chối mọi batch khác batch-chưa-terminal đầu tiên (terminal: PUBLISHED, BLOCKED, FAIL); `next_batch` trong progress report KHÔNG phải quyền claim.
- Checkpoint `data/batches/writer-checkpoint.json`: schema_version, batch, chunk_size, current_chunk_ids, written_ids, pending_qa_ids, pending_repair_ids, pass_ids, pending_publish_ids, published_ids, last_completed_step, updated_at. MATRIX > CHECKPOINT khi xung đột.
- Publish gate: quality PASS VÀ SEO >= 90 (`score_article_seo.py`), không critical. SEO 100 không cứu được quality FAIL hay critical.
- SEO reports: `reports/seo/articles/<article-id>.json` (score, sections, issues, recommendations) + `reports/seo/factory-seo-summary.json`.
- Throughput: `reports/batches/factory-throughput.json` (số liệu thật từ matrix + checkpoint).

## Vòng đời một batch (lệnh chuẩn)

Từ repo root, mỗi operator run:

```bash
python3 scripts/run_article_batch.py progress          # xem trạng thái hiện tại
python3 scripts/run_article_batch.py plan B01          # manifest 50 dòng của B01
python3 scripts/run_article_batch.py claim B01         # lock + chuyển WRITING
# → Mistral viết 50 file bài theo manifest + docs/ARTICLE-RULES.md
python3 scripts/run_article_batch.py qa B01            # validate + score từng bài
python3 scripts/run_article_batch.py publish B01       # txn → matrix → sitemap → hubs → article shells → progress → xóa marker
python3 scripts/run_article_batch.py recover           # nếu run bị gián đoạn giữa chừng
```

Node fallback (Python không khả dụng): `node scripts/validate_content_matrix.mjs`, `node scripts/run_article_batch.mjs plan B01`, `node scripts/run_article_batch.mjs progress`.

## Transaction publish

Marker `data/batches/txn/txn.json` ghi pre-state + planned writes. Trình tự: ghi marker → ghi file → consistency check → xóa marker. Marker pending → mọi mutation khác bị từ chối; chỉ `recover` được chạy.

## Lock

`data/batches/lock.json` — một operator duy nhất được claim/publish tại một thời điểm. Stale lock chỉ được thu hồi sau khi expired và có `FORCE_STALE_LOCK_RECOVERY=1`.

## Reports

- `reports/batches/factory-progress.json` — sinh từ matrix bởi `scripts/run_article_batch.py progress` / `factory_common.write_progress()`. KHÔNG hard-code số liệu.
- `reports/batches/Bxx.json` — báo cáo từng batch, cumulative, chứa đủ mọi thành viên batch.
- `reports/audits/` — snapshot audit (xem audit foundation run).

## Hub generation

`scripts/generate_hub_lists.py` đọc matrix, liệt kê bài PUBLISHED của category vào hub tương ứng. Không để hub list drift khỏi matrix; hỗ trợ pagination khi hub dài. Không dồn body hàng trăm bài vào hub.

Quy tắc hub & phân trang (taxonomy contract):

- Hub chỉ liệt kê bài PUBLISHED của đúng MỘT category, thứ tự deterministic (batch_id, article_id).
- Mỗi trang hub tối đa `HUB_PAGE_SIZE = 50` link (`factory_common.HUB_PAGE_SIZE`).
- Vượt 50 bài → sinh listing page `<hub>-trang-<n>.html` (root-level, dùng chung chrome site, canonical riêng, có trong sitemap); trang hub có pagination nav.
- Bài bị rollback (recover) làm giảm số trang → listing page mồ côi bị XÓA tự động.
- Hub card dùng `<a>` card (category pill + title + date); container hub-list được thay nội dung bằng balanced-div replacement (`_replace_container`) vì grid card có `<div>` lồng.
- Pagination có ← Trước / số (aria-current) / Sau →, link crawlable, target ≥44px.
- Menu/footer chỉ chứa 3 nhóm UI (xem `docs/SEO-OWNERSHIP.md`); KHÔNG đặt link bài viết riêng lẻ vào menu/footer.

## Publish taxonomy gate

`run_article_batch.py publish` kiểm TRƯỚC khi mutation: mỗi bài thuộc đúng MỘT category hợp lệ, parent hub đúng, mapping nhóm `navigation_groups` hợp lệ (`fc.validate_nav_taxonomy()`). Vi phạm → từ chối publish, không đổi matrix. Sau publish, hub + sitemap + reports được regenerate trong cùng transaction.

## Article shell (derived UI layer)

Mỗi bài PUBLISHED được `scripts/build_article_shell.py` bọc bằng chrome chuẩn site (cùng design language với các trang chính): TOC tự sinh từ H2/H3, meta row, sources box, related cards, CTA từ business-facts. Shell là DERIVED state: chạy trong cùng publish transaction, idempotent (chạy 2 lần ra byte-identical), chỉ xử lý row PUBLISHED. Content QA scope trong vùng `<article>` nên shell không ảnh hưởng điểm QA. Xem docs/ARTICLE-RULES.md.

## Sitemap

`scripts/generate_sitemap.py` chỉ thêm URL bài ở trạng thái PUBLISHED. Không URL PLANNED/WRITING/QA/REVIEW/REPAIR/PASS-chưa-publish/broken. Base: `https://thuexemayhanoi.github.io/vanchinh/`.

## Không trùng lặp liên site

Nội dung phải viết độc lập cho site Văn Chính. Cấm copy/spin từ `thuexemayhanoi/shop`. Tooling và kiến trúc có thể giống; nội dung thì không.