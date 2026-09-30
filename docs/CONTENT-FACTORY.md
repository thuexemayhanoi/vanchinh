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

- claim chỉ chuyển đúng N row PLANNED → WRITING (không claim cả 50). `claim --ids` claim đúng danh sách ID tường minh (workflow dùng chế độ này: claim đúng các row có file trong push, max 10).
- qa scoped: chỉ chấm chunk hiện tại (checkpoint) hoặc --ids tường minh; row không chạm giữ nguyên trạng thái. `qa --ids` được phép re-score row WRITING/QA/REVIEW/REPAIR/PASS (repair/resume: push sửa file bài của các row này); scoped mặc định chỉ chấm WRITING/QA/REPAIR.
- Row WRITING không có file trong chunk hiện tại → REPAIR/BLOCKED, không phá trạng thái batch khác. Row PLANNED chưa có file không bao giờ bị workflow claim (selection derive từ file thực tế trong push).
- PUBLISHED không bao giờ bị claim lại.
- INVARIANT batch hiện tại: batch đang chạy phải hoàn tất trước khi claim batch khác. `claim` từ chối mọi batch khác batch-chưa-terminal đầu tiên (terminal: PUBLISHED, BLOCKED, FAIL); `next_batch` trong progress report KHÔNG phải quyền claim.
- Checkpoint `data/batches/writer-checkpoint.json`: schema_version, batch, chunk_size, current_chunk_ids, written_ids, pending_qa_ids, pending_repair_ids, pass_ids, pending_publish_ids, published_ids, last_completed_step, updated_at. MATRIX > CHECKPOINT khi xung đột: mọi pending list được DERIVE từ trạng thái matrix khi đọc (REPAIR→PASS rời pending_repair_ids; PUBLISHED rời mọi pending list) — không tồn tại stale pending ID.
- Publish gate: quality PASS VÀ SEO >= 90 (`score_article_seo.py`), không critical. SEO 100 không cứu được quality FAIL hay critical.
- SEO reports: `reports/seo/articles/<article-id>.json` (score, sections, issues, recommendations) + `reports/seo/factory-seo-summary.json`.
- Throughput: `reports/batches/factory-throughput.json` (số liệu thật từ matrix + checkpoint).

## Vòng đời một batch (chunked continuous loop)

Batch = 50 bài, nhưng writer KHÔNG BAO GIỜ làm cả 50 row một lượt. Mỗi batch = chuỗi chunk ≤ 10 bài, lặp liên tục đến khi batch terminal (xem docs/CONTINUOUS-WRITER.md):

```bash
python3 scripts/run_article_batch.py progress          # xác định active batch (batch đầu tiên còn row chưa terminal)
# → writer chọn tối đa 10 row PLANNED kế tiếp (thứ tự deterministic), VIẾT file bài theo manifest + docs/ARTICLE-RULES.md
# → local scoped QA → PUSH chunk (≤ 10 file mới) → factory-publish.yml: claim đúng ID có file → qa → publish
python3 scripts/run_article_batch.py checkpoint          # xác nhận chunk đã reconcile
# → FETCH FRESH MAIN → chunk ≤ 10 kế tiếp → LẶP LẠI cho tới khi batch terminal → sang batch kế
python3 scripts/run_article_batch.py recover            # chỉ khi run bị gián đoạn giữa chừng
```

Không pre-claim 50 row, không viết cả batch trước khi push, không dừng chờ phê duyệt giữa các chunk, không dừng sau một chunk: sau khi factory-publish xanh, fetch fresh main và viết ngay chunk kế tiếp.

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

## 4-Tier Verification Contract

Hợp đồng bắt buộc (AGENTS.md tham chiếu mục này). "CI GREEN" KHÔNG đồng nghĩa production-safe nếu tier áp dụng cho change đó chưa PASS.

### TIER 1 — UNIT

- Unit/ regression/ state-machine tests, pure deterministic checks: `python3 tests/run_tests.py`.
- Bao phủ: state transitions, matrix integrity, txn/lock semantics, fail-closed recover (fault injection), fail-closed driver gate, push selection, SEO scorer, hub/sitemap invariants.
- Test KHÔNG BAO GIỜ mutate production state — fixture dùng `CONTENT_MATRIX` / `WRITER_CHECKPOINT` / `LOCK_FILE` / `TXN_FILE` / `PROGRESS_FILE` / `FACTORY_THROUGHPUT` trỏ temp dir.

### TIER 2 — INTEGRATION

- Claim → writer fixture → QA → PASS → publish sandbox E2E nhiều chu kỳ (trong `tests/run_tests.py`: chunked factory, claim-resume-repair, continuous driver).
- Writer-required resume (row WRITING không có file → REPAIR/BLOCKED, không phá batch khác), push selection (NEW/REPAIR/BACKLOG/SKIP từ git diff), repair flow (re-score row WRITING/QA/REVIEW/REPAIR/PASS), deterministic derived outputs (sitemap/hub/shell rebuild byte-identical).

### TIER 3 — PRODUCTION INVARIANT

- `scripts/validate_content_matrix.py` + `node scripts/validate_content_matrix.mjs` (2000 rows, 40×50, id/path unique, category hợp lệ).
- `scripts/check_matrix_sync.py` (matrix == generator output).
- `scripts/check_cannibalization.py` (không keyword xâm phạm intent bảo vệ).
- `scripts/validate_site.py` (1 H1, canonical unique + khớp path, không broken link/asset).
- Published file tồn tại đúng output_path; sitemap == PUBLISHED truth; hub lists == PUBLISHED truth theo category.
- KHÔNG txn (`data/batches/txn/txn.json`) / lock (`data/batches/lock.json`) sau publish thành công; không production state drift.
- Continuous driver (`scripts/run_continuous_factory.py`) fail-closed: bất kỳ validator FAIL → status BLOCKED, exit != 0, KHÔNG in marker CONTINUING. Subcommand: `run_continuous_factory.py validate`.

### TIER 4 — LONG-RUN / FAILURE RECOVERY / LIVENESS

- Soak: `python3 tests/factory_soak.py` — multi-chunk sandbox (temp fixture, KHÔNG dùng production matrix, KHÔNG publish bài thật): nhiều chu kỳ claim → writer fixture → QA → PASS → publish → verify, inject lỗi có kiểm soát (after begin_txn, after partial writes, sitemap fail, hub fail, stale lock, restart → recover, retry publish), assert mỗi chu kỳ: txn/lock sạch, checkpoint khớp matrix, không skip ID, không publish trùng, counter monotonic, sitemap/hub chỉ chứa PUBLISHED, không trang mồ côi, không leak draft/test, production tree byte-identical sau test.
- Recovery fail-closed (docs/RECOVERY.md): recover KHÔNG xóa marker khi chưa chứng minh được trạng thái deterministic.
- Liveness watchdog: `python3 scripts/factory_liveness.py` — READ-ONLY tuyệt đối (không recover, không xóa lock, không claim, không publish). Verdict: HEALTHY_IDLE / HEALTHY_ACTIVE (PASS), STALLED_ACTIVE / STALE_TXN / EXPIRED_OR_STALE_LOCK_WITH_UNFINISHED_WORK / CHECKPOINT_STALE (FAIL). Row PLANNED đơn thuần KHÔNG phải stall; writer nghỉ hợp lệ + không in-flight work = HEALTHY_IDLE. CI định kỳ: `.github/workflows/factory-liveness.yml` (contents: read, không push).

### Phạm vi bắt buộc

- Change engine/ workflow/ recovery/ scripts → TIER 1 + 2 + 3 + 4.
- Change content-only (bài viết) → tier phù hợp scope; publish gate hiện hữu vẫn bắt buộc.
- KHÔNG BAO GIỜ tuyên bố "factory fixed" chỉ vì unit tests xanh.

## Không trùng lặp liên site

Nội dung phải viết độc lập cho site Văn Chính. Cấm copy/spin từ `thuexemayhanoi/shop`. Tooling và kiến trúc có thể giống; nội dung thì không.