# AGENTS.md — Hợp đồng thực thi cho AI agent (vanchinh)

Hợp đồng ngắn gọn, bắt buộc với mọi AI agent làm việc trên repo này. Chi tiết vận hành: README.md và docs/. Khi mâu thuẫn: repository truth thắng mọi tài liệu; khi tài liệu mâu thuẫn nhau, README.md là chuẩn.

## Nguyên tắc tuyệt đối

- REPOSITORY TRUTH > MEMORY > OLD REPORTS. Không bao giờ tin trí nhớ hội thoại thay vì file trong repo.
- Không bao giờ restart factory, không reset matrix, không đếm lại từ đầu.
- Không bao giờ rewrite bài PUBLISHED nếu không có lỗi đã kiểm chứng kèm lý do repair rõ ràng.
- Không bao giờ tái sinh matrix destructive (chạy generator toàn bộ) khi đã có tiến độ production.
- Không bao giờ force push.
- Không bao giờ weaken QA, tắt test, bỏ matrix validation hay bypass PASS gate để lấy kết quả xanh.
- Test KHÔNG BAO GIỜ được mutate production state (matrix, checkpoint, lock, txn). Fixture phải dùng env `CONTENT_MATRIX` / `WRITER_CHECKPOINT` trỏ thư mục tạm.

## Batch / chunk

- Batch = 50 bài (B01–B40, tổng 2.000) là đơn vị tổ chức matrix; đơn vị QA/publish của factory = PAIR 2 bài, nhưng writer dùng WRITE-AHEAD QUEUE: một push xếp hàng 2..10 bài mới, factory (`factory_queue.py`) tự chia pair 2 và tiêu thụ tuần tự trong cùng một run. Hard invariant workflow: một push tối đa 10 file bài mới (`factory-publish.yml` refuse > 10). Multi-writer: tối đa 3 writer lease ID disjoint qua `scripts/writer_claim.py` (TTL 48h, max 10 ID/writer).
- INVARIANT: batch hiện tại chưa hoàn tất PHẢI hoàn tất trước. `claim` từ chối batch khác batch-chưa-hoàn-thành đầu tiên. KHÔNG bao giờ nhảy sang B02 khi B01 còn row chưa terminal. Terminal: PUBLISHED, BLOCKED, FAIL. `next_batch` trong progress report không phải quyền claim.
- Thứ tự deterministic: batch_id + article_id. PUBLISHED không bao giờ bị claim lại.

## Trước khi làm việc

1. Fetch fresh main, đọc README.md, docs/CONTENT-FACTORY.md, docs/ARTICLE-RULES.md, docs/SEO-OWNERSHIP.md.
2. Kiểm: `data/batches/txn/txn.json` (pending transaction), `data/batches/lock.json` (lock), `data/batches/writer-checkpoint.json`, `data/content-matrix.csv`, `reports/batches/factory-progress.json`, workflow đang chạy trên remote.
3. Marker txn tồn tại → chạy `python3 scripts/run_article_batch.py recover` TRƯỚC mọi mutation.

## Thứ tự ưu tiên khi resume

RECOVER → RESUME (hoàn tất dở của batch đang chạy) → REPAIR → QA → PUBLISH PASS → FETCH FRESH MAIN → NEXT CHUNK → REPEAT.

## Continuous writer loop (bắt buộc)

Mọi writer run TUÂN THEO vòng lặp liên tục trong docs/CONTINUOUS-WRITER.md:

FETCH FRESH MAIN → RECOVER IF NEEDED → RESUME (REPAIR/QA/PASS pending trước) → CLAIM (writer_claim.py lease) → WRITE 2..10 file bài (write-ahead queue) → LOCAL SCOPED QA từng bài (quality PASS + SEO ≥ 80, không critical) → PUSH QUEUE (file mới; safe checkpoint) → WAIT factory-publish (tiêu thụ từng pair 2 tuần tự) → VERIFY (CI/Pages, no lock/txn) → FETCH FRESH MAIN → QUEUE NEXT → REPEAT (không dừng sau mỗi queue).

- KHÔNG kết thúc run sau một queue thành công. Nếu không có blocker, bắt đầu NGAY queue kế tiếp.
- KHÔNG dừng chỉ vì một pair/queue vừa xong, một workflow/ Pages deploy/ batch xong, hay report được sinh — đó là checkpoint.
- Chỉ dừng khi: 2.000 row terminal hợp lệ, runtime/session buộc dừng tại điểm an toàn (không lock, không txn, fresh main), hoặc blocker thật cần con người.
- Giữ nguyên: pair 2 bài là đơn vị QA/publish; write-ahead queue 2..10 bài/push (10 là hard max); không force push; repository truth thắng; batch active phải terminal trước khi sang batch khác; pair fail là recoverable, KHÔNG rollback pair đã publish.

## Phân vai

- AI bên ngoài (Mistral run) viết prose — file bài viết HTML thật dưới `cam-nang/`, theo docs/ARTICLE-RULES.md và rubric.
- Tooling deterministic trong repo (GitHub Actions, scripts Python/Node) validate và publish. Không AI trong Actions, không API key.
- Publish yêu cầu: quality PASS VÀ SEO >= 80, không critical. Fail là fail.

## Nếu bị gián đoạn

- Giữ nguyên mọi partial work hợp lệ; trạng thái repo là điểm resume duy nhất.
- Ghi checkpoint/progress bằng lệnh repo (không tự chế state file).
- Run kế tiếp bắt đầu bằng read order README §21, không đọc lại lịch sử chat để suy trạng thái.

## Blog UI / article shell

- File bài = bare article (head + đúng một `<article>`); chrome site/TOC/related/CTA là derived state của `scripts/build_article_shell.py`. Sửa UI blog = sửa shell builder/CSS/hub generator, KHÔNG sửa tay từng file bài.
- Push THÊM file bài mới → `factory-publish.yml` queue ĐÚNG các ID có file (row PLANNED của active batch, file tồn tại, 2..10/push; >10 file mới trong một push → refuse). Row PLANNED chưa có file KHÔNG BAO GIỜ bị claim.
- Push SỬA file bài của row WRITING/QA/REVIEW/REPAIR/PASS → workflow QA + publish đúng các ID đó (repair mode), KHÔNG claim row PLANNED mới. Push sửa row PUBLISHED (shell rebuild, UI work) KHÔNG kích hoạt gì cả.
- Scope của workflow do `scripts/factory_push_selection.py` derive từ `git diff` — deterministic, không AI/API key.
- Shell không được đổi URL/canonical/JSON-LD/prose; CTA phải resolve từ business-facts, không hard-code.

## 4-Tier Verification Contract

"CI GREEN" KHÔNG đồng nghĩa production-safe. Chỉ được coi production-safe khi TOÀN BỘ tier áp dụng cho change đó PASS. Chi tiết từng tier: docs/CONTENT-FACTORY.md §4-Tier.

- TIER 1 — UNIT: `python3 tests/run_tests.py` (unit/regression/state-machine, pure deterministic). Test KHÔNG BAO GIỜ mutate production state.
- TIER 2 — INTEGRATION: claim → QA → publish sandbox E2E; writer-required resume; push selection; repair flow; deterministic derived outputs (sitemap/hub/shell byte-identical khi rebuild).
- TIER 3 — PRODUCTION INVARIANT: matrix validation (py + node), matrix sync, site validation, cannibalization, published file tồn tại, sitemap == PUBLISHED truth, hub == PUBLISHED truth, KHÔNG txn/lock sau publish thành công, không production state drift. Driver continuous: `run_continuous_factory.py validate` fail-closed.
- TIER 4 — LONG-RUN / FAILURE RECOVERY / LIVENESS: `python3 tests/factory_soak.py` (multi-chunk soak + fault injection + restart/recover, sandbox fixture); `python3 scripts/factory_liveness.py` (watchdog READ-ONLY: HEALTHY_IDLE/HEALTHY_ACTIVE/STALLED_ACTIVE/STALE_TXN/STALE_LOCK/CHECKPOINT_STALE).

Phạm vi bắt buộc:

- Change engine/ workflow/ recovery → TIER 1 + 2 + 3 + 4 bắt buộc.
- Change content-only (bài viết) → KHÔNG yêu cầu 4-tier cho mỗi batch: chỉ cần scoped QA (quality PASS + SEO >= 80, không critical) + publish gate + light matrix smoke trong factory-publish. Full-site audit toàn site chỉ chạy MỘT LẦN khi đủ 2.000 bài, sau đó repair theo batch lỗi.
- KHÔNG BAO GIỜ tuyên bố "factory fixed" chỉ vì unit tests xanh.

## Sau mọi thay đổi (gates theo scope — Simple Production Mode)

- Change engine/ workflow/ scripts/ docs vận hành → full gates: `python3 tests/run_tests.py`, `scripts/validate_site.py`, `scripts/validate_content_matrix.py`, `node scripts/validate_content_matrix.mjs`, `scripts/check_matrix_sync.py`, `scripts/check_cannibalization.py`.
- Change content-only (batch bài viết) → KHÔNG chạy full-site audit sau mỗi batch. Chỉ cần: scoped QA từng bài (quality PASS + SEO >= 80, không critical), publish đúng PASS IDs, light matrix smoke (validate_content_matrix + check_matrix_sync trong factory-publish), CI xanh của đúng SHA. Full-site audit (quality/SEO/duplicate/cannibalization/links/sitemap/schema toàn site) chạy MỘT LẦN khi đạt 2.000 bài, rồi repair theo batch.
- Không push khi test đỏ. Sau push: verify remote HEAD và CI của đúng SHA mới.
- Không claim SUCCESS/FIXED/PUBLISHED khi chưa kiểm chứng độc lập.
