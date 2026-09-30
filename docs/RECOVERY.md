# Recovery — Transaction, Lock, Resume

## Transaction publish

Publish là transaction nhiều file (article + matrix + hubs + sitemap + reports + factory-progress). GitHub Pages không có atomic multi-file commit cục bộ, nên dùng marker:

`data/batches/txn/txn.json` chứa: batch, planned writes, pre-state snapshot, step hiện tại.

Trình tự bắt buộc:

```
ghi marker → thực hiện writes → post-write consistency check → xóa marker
```

- Marker tồn tại → từ chối MỌI mutation khác (claim/publish/generate).
- Chỉ `recover` được chạy khi có marker.

## Recover

```bash
python3 scripts/run_article_batch.py recover
```

Hành vi FAIL-CLOSED (hợp đồng bắt buộc):

- Recovery chỉ được xóa marker khi xác minh được trạng thái DETERMINISTIC và consistency PASS:
  - verified rollback: mọi article trong plan vẫn ở pre-state (PASS) + file tồn tại → rollback hoàn tất, regen sitemap/hub xác minh OK → mới xóa marker.
  - verified completion: mọi article PUBLISHED + file tồn tại → regen + xác minh các derived output (sitemap, hubs, shells, progress) → mới xóa marker.
- Bất kỳ ambiguity/ conflict (file missing, matrix/file disagreement, partial publish, malformed marker/ plan, unknown plan id, PUBLISHED-without-file, rollback regen FAIL) → GIỮ NGUYÊN marker, exit non-zero, báo chính xác article/ state/ file conflict, yêu cầu operator xử lý. KHÔNG publish tiếp khi còn marker.
- Recover KHÔNG BAO GIỜ: tự đoán trạng thái đúng; xóa marker khi consistency chưa PASS; force-clear; reset repair count; reset/ ghi lại matrix.
- Publish rollback (sitemap/hub/shell regen fail) tuân cùng hợp đồng: chỉ xóa marker khi rollback regen xác minh PASS; ngược lại giữ marker + "rollback incomplete: run recover".

## Lock

`data/batches/lock.json` (operator, timestamp). Trước mutation:

1. Kiểm remote HEAD (fetch fresh main).
2. Kiểm pending txn → nếu có, recover trước.
3. Kiểm lock → nếu active, từ chối.
4. Kiểm active batch trong reports → hoàn tất tiến độ dở TRƯỚC.

Stale lock: chỉ khi expired theo thời gian, và phải set `FORCE_STALE_LOCK_RECOVERY=1`; ghi rõ lý do + kiểm chứng pid/owner vào reports trước khi thu hồi.

## Resume

- Trạng thái repo (matrix + reports + markers) là chuẩn, KHÔNG phải trí nhớ hội thoại.
- Run trước đã làm một chunk, xong một phần → hoàn tất phần còn lại của chunk/ batch đang chạy TRƯỚC, không claim work mới. Batch mới chỉ được claim khi batch trước đã terminal toàn bộ row (PUBLISHED, BLOCKED, FAIL).
- Không vứt partial work; không tự đếm lại từ đầu.
- Checkpoint pending lists (pending_qa_ids, pending_repair_ids, pass_ids, pending_publish_ids, written_ids) là DERIVED state: khi đọc, mỗi list được lọc theo trạng thái matrix hiện tại. Row REPAIR được sửa và QA PASS → rời pending_repair_ids, vào pass/pending_publish; row PUBLISHED → rời mọi pending list. Nếu checkpoint chứa ID không khớp trạng thái matrix, MATRIX thắng — không cần sửa tay checkpoint.
- Row REPAIR do workflow over-claim file chưa tồn tại (lỗi đã fix: claim mù theo limit): KHÔNG reset repair_attempts, KHÔNG rollback matrix; viết file bài cho đúng các ID đó rồi `qa <batch> --ids ...` → PASS → `publish <batch> --ids ...`.

## Quy trình chuẩn sau gián đoạn

```bash
git fetch && đọc README §21 read order
python3 scripts/run_article_batch.py recover
python3 scripts/run_article_batch.py progress
python3 tests/run_tests.py   # phải xanh trước khi mutation mới
```
