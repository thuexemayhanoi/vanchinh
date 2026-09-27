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

Hành vi: đọc marker → kiểm từng planned write: đã nhất quán → giữ và hoàn tất các bước còn lại; chưa nhất quán → hoàn tác về pre-state (không publish dở). Chỉ xóa marker khi consistency PASS. Recover không bao giờ phát sinh publish nửa vời.

## Lock

`data/batches/lock.json` (operator, timestamp). Trước mutation:

1. Kiểm remote HEAD (fetch fresh main).
2. Kiểm pending txn → nếu có, recover trước.
3. Kiểm lock → nếu active, từ chối.
4. Kiểm active batch trong reports → hoàn tất tiến độ dở TRƯỚC.

Stale lock: chỉ khi expired theo thời gian, và phải set `FORCE_STALE_LOCK_RECOVERY=1`; ghi rõ lý do + kiểm chứng pid/owner vào reports trước khi thu hồi.

## Resume

- Trạng thái repo (matrix + reports + markers) là chuẩn, KHÔNG phải trí nhớ hội thoại.
- Run trước claim 50, xong 30 → hoàn tất 30 còn lại trước khi claim batch mới. Batch mới chỉ được claim khi batch trước đã terminal toàn bộ row (PUBLISHED, BLOCKED, FAIL).
- Không vứt partial work; không tự đếm lại từ đầu.

## Quy trình chuẩn sau gián đoạn

```bash
git fetch && đọc README §21 read order
python3 scripts/run_article_batch.py recover
python3 scripts/run_article_batch.py progress
python3 tests/run_tests.py   # phải xanh trước khi mutation mới
```
