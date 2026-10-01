# Factory Publish Workflow (automated chunked publish — TURBO QUEUE)

`.github/workflows/factory-publish.yml` là cơ chế publish tự động, deterministic, KHÔNG dùng AI/API key/secrets bên trong GitHub Actions. Contract WRITE-AHEAD QUEUE: một writer push xếp hàng 2..10 bài, factory tự tiêu thụ thành các pair 2 tuần tự trong CÙNG một production run.

## Event-driven — KHÔNG phải scheduler

Workflow CHỈ được kích hoạt bởi push hợp lệ lên `main` thêm/ sửa file bài trong `cam-nang/`. Nó KHÔNG: viết prose, gọi Mistral, schedule writer, hay tự tạo chunk kế tiếp. File lease của writer (`data/batches/writer-claims.json`) nằm NGOÀI paths filter — push registry KHÔNG kích hoạt workflow. Sau khi publish thành công, trách nhiệm QUAY VỀ external writer. Nếu mọi writer session đã kết thúc, factory đứng yên ở trạng thái sạch.

## Vai trò

- WRITER (run Mistral bên ngoài, tối đa 3 chạy song song) cam kết file bài viết dưới `cam-nang/` lên nhánh `main`. Mỗi writer lease ID disjoint qua `scripts/writer_claim.py` trước khi viết (xem docs/CONTINUOUS-WRITER.md).
- Workflow tự kích hoạt khi một push lên `main` thêm hoặc sửa file bài trong `cam-nang/`. Scope CHÍNH XÁC được derive bởi `scripts/factory_push_selection.py` từ `git diff --diff-filter=A/M HEAD~1 HEAD -- cam-nang/` (capture TRƯỚC khi refresh truth), rồi REVALIDATE trên fresh main:
  - NEW: push THÊM file bài → queue ĐÚNG các row PLANNED của active batch có output_path trong danh sách added VÀ file tồn tại. 2..10 bài/push; push >10 file bài mới → REFUSE. Row PLANNED chưa có file KHÔNG BAO GIỜ bị claim (root cause B18: claim mù đã biến row chưa viết thành REPAIR score 0).
  - REPAIR: push SỬA file bài của row WRITING/QA/REVIEW/REPAIR/PASS → queue đúng các ID đó, KHÔNG claim row PLANNED mới. Row PUBLISHED bị sửa (shell rebuild, UI work) không kích hoạt gì cả.
  - BACKLOG: push không chạm file bài nhưng PLANNED row đã có file trong repo (pipeline trước fail giữa chừng) → queue đúng các row đó (≤10 đầu, deterministic theo matrix order).
  - SKIP: không có gì hợp lệ để xử lý (ví dụ push chỉ sửa tooling) → workflow kết thúc sạch.

## Pipeline trong một run (factory_queue.py)

1. Capture diff của push, fetch `origin main`, checkout lại truth (KHÔNG bao giờ force). Selection chạy trên matrix mới nhất — mọi ID được revalidate chống duplicate/ PUBLISHED/ sai batch trước khi mutation nào xảy ra.
2. Guard: không pending txn, không lock.
3. Chia queue thành các PAIR 2 bài deterministic theo thứ tự matrix; `scripts/factory_queue.py run` giữ MỘT lock cho cả run và tiêu thụ tuần tự từng pair:
   - pair → claim (mode new, đúng pair IDs) → scoped QA (quality + SEO từng bài) → publish transactional CHỈ row PASS (quality PASS VÀ SEO >= 80, không critical) → checkpoint → pair kế.
   - pair FAIL/REVIEW → RECOVERABLE: trạng thái được commit, pair lỗi được ghi rõ ID, run TIẾP TỤC pair sau. Pair fail KHÔNG BAO GIỜ rollback pair đã publish thành công.
   - pair lỗi vẫn giữ một lock chung cho cả run (publisher concurrency = 1).
4. Light matrix smoke TRƯỚC khi commit derived state: `validate_content_matrix.py` + `check_matrix_sync.py` (đỏ → KHÔNG commit derived state). KHÔNG chạy full test suite/validate_site/check_cannibalization/node parity trong hot loop (Simple Production Mode) — các gate nặng nằm ở CI và full audit một lần khi đủ 2.000 bài.
5. Queue summary in rõ published IDs và RECOVERABLE IDs (repair push kế tiếp).
6. MỘT commit cho toàn bộ derived state của run; push với retry fetch+rebase (tối đa 3 lần, KHÔNG force push); assert không sót lock/txn marker.

Run report: `reports/batches/factory-queue-last-run.json` được ghi lại sau MỖI pair (crash-resilient): queue, từng pair (claimed/pass/published/review/repair/blocked/status), published_total, recoverable_ids, fatal.

Exit codes của `factory_queue.py`: 0 = queue đã xử lý (published hoặc recoverable đều được commit); 1 = fatal, không mutation (txn pending, lock held, queue không hợp lệ).

## Quy tắc an toàn

- Writer LUÔN viết đúng các ID đã lease (writer_claim) và push đúng số file đã viết; workflow queue đúng đúng số file writer tạo — không over-claim, không under-claim.
- Bài quality FAIL/REVIEW/REPAIR không chặn bài PASS trong cùng pair hay pair sau; publish chỉ đưa row PASS lên PUBLISHED.
- Publish từ chối (không có row PASS hợp lệ trong pair) → trạng thái vẫn được commit để audit, pair được báo recoverable, run không đỏ vì recoverable.
- Không bao giờ chạy workflow khi có pending txn/lock; dùng `recover` trước (xem docs/RECOVERY.md).
- MATRIX vẫn là source of truth; checkpoint chỉ là operational state (MATRIX > CHECKPOINT). Mọi pending list được DERIVE từ trạng thái matrix khi đọc — không có stale ID.

## Tương tác state fields của matrix

`tools/generate_content_matrix.py` bảo toàn các state fields (`status, score, quality_status, repair_attempts, published_date, last_checked, notes`) khi tái sinh matrix, nên `check_matrix_sync.py` vẫn xanh sau khi sản xuất bắt đầu. Content fields vẫn byte-identical với generator.
