# Factory Publish Workflow (automated chunked publish)

`.github/workflows/factory-publish.yml` là cơ chế publish tự động, deterministic, KHÔNG dùng AI/API key/secrets bên trong GitHub Actions.

## Event-driven — KHÔNG phải scheduler

Workflow CHỈ được kích hoạt bởi push hợp lệ lên `main` thêm/ sửa file bài trong `cam-nang/`. Nó KHÔNG: viết prose, gọi Mistral, schedule writer, hay tự tạo chunk kế tiếp. Sau khi publish thành công, trách nhiệm QUAY VỀ external writer: writer phải fetch fresh main và viết ngay chunk ≤ 10 kế tiếp theo continuous-run contract (docs/CONTINUOUS-WRITER.md). Nếu session writer đã kết thúc, factory đứng yên ở trạng thái sạch — không thành phần nào trong repo tự tiếp tục sản xuất nội dung.

## Vai trò

- WRITER (run Mistral bên ngoài) cam kết file bài viết dưới `cam-nang/` lên nhánh `main` (sau khi CI của PR xanh).
- Workflow tự kích hoạt khi một push lên `main` thêm hoặc sửa file bài trong `cam-nang/`. Scope CHÍNH XÁC được derive bởi `scripts/factory_push_selection.py` từ `git diff --diff-filter=A/M HEAD~1 HEAD -- cam-nang/`:

  - NEW: push THÊM file bài → claim ĐÚNG các row PLANNED của active batch có output_path trong danh sách added VÀ file tồn tại (map output_path → article_id từ matrix). Max 10; push >10 file bài mới → REFUSE (writer phải chia push ≤10). Row PLANNED chưa có file KHÔNG BAO GIỜ bị claim (root cause B18: claim mù `--limit 10` đã biến 5 row chưa viết thành REPAIR score 0).
  - REPAIR: push SỬA file bài của row WRITING/QA/REVIEW/REPAIR/PASS → workflow QA + publish EXPLICIT đúng các ID đó (`qa --ids`, `publish --ids`), KHÔNG claim row PLANNED mới. Row PUBLISHED bị sửa (shell rebuild, UI work) không kích hoạt gì cả.
  - BACKLOG: push không chạm file bài nhưng PLANNED row đã có file trong repo (pipeline trước fail giữa chừng) → claim đúng các row đó (≤10, deterministic theo article_id).
  - SKIP: không có gì hợp lệ để xử lý (ví dụ push chỉ sửa tooling) → workflow kết thúc sạch.

1. Chốt lock/txn sạch trước khi mutate.
2. Xác định active batch deterministic: batch đầu tiên (theo thứ tự matrix) còn row chưa terminal (terminal: PUBLISHED, BLOCKED, FAIL). Không còn batch chưa hoàn tất -> bỏ qua publish.
3. NEW/BACKLOG: `claim <active> --ids <exact ids>`: đúng các row có file -> WRITING. REPAIR: không claim, chỉ `qa <active> --ids <repaired ids>` (qa --ids được phép re-score row WRITING/QA/REVIEW/REPAIR/PASS).
4. `publish <active> --ids <pass ids>`: grouped transactional publish — chỉ row quality PASS VÀ SEO >= 90, không critical; publish cập nhật matrix, hubs, sitemap, article shells, checkpoint, reports trong MỘT transaction có marker. Shell rebuild thất bại → rollback toàn bộ (row về PASS, marker xóa).
5. Chạy lại toàn bộ test suite + validate_site + validate_content_matrix TRƯỚC khi push (gate trước publish).
6. MỘT commit cho toàn bộ derived state của chunk; push; assert không sót lock/txn marker.

## Quy tắc an toàn

- Writer LUÔN viết đúng các row đã claim (theo thứ tự claim) và push đúng số file đã viết; workflow claim đúng đúng số file writer tạo — không over-claim, không under-claim.
- Bài quality FAIL/REVIEW/REPAIR không chặn bài PASS trong cùng chunk; publish chỉ đưa row PASS lên PUBLISHED.
- Nếu publish bị từ chối (không có row PASS hợp lệ), trạng thái qa/claim vẫn được commit để audit, workflow báo đỏ.
- Không bao giờ chạy workflow khi có pending txn/lock; dùng `recover` trước (xem docs/RECOVERY.md).
- MATRIX vẫn là source of truth; checkpoint chỉ là operational state (MATRIX > CHECKPOINT). Mọi pending list của checkpoint (`pending_qa_ids`, `pending_repair_ids`, `pass_ids`, `pending_publish_ids`, `written_ids`) được DERIVE từ trạng thái matrix hiện tại khi đọc: row REPAIR → PASS rời khỏi `pending_repair_ids`; row PUBLISHED rời khỏi mọi pending list. Không có stale ID.

## Tương tác state fields của matrix

`tools/generate_content_matrix.py` bảo toàn các state fields (`status, score, quality_status, repair_attempts, published_date, last_checked, notes`) khi tái sinh matrix, nên `check_matrix_sync.py` vẫn xanh sau khi sản xuất bắt đầu. Content fields vẫn byte-identical với generator.
