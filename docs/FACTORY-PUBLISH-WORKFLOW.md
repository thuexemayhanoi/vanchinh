# Factory Publish Workflow (automated chunked publish)

`.github/workflows/factory-publish.yml` là cơ chế publish tự động, deterministic, KHÔNG dùng AI/API key/secrets bên trong GitHub Actions.

## Vai trò

- WRITER (run Mistral bên ngoài) cam kết file bài viết mới dưới `cam-nang/` lên nhánh `main` (sau khi CI của PR xanh).
- Workflow tự kích hoạt khi một push lên `main` có file mới trong `cam-nang/`, và chạy toàn bộ tooling chuẩn:

1. Bỏ qua nếu push không có file bài viết mới (tránh vòng lặp với commit publish của chính workflow).
2. Chốt lock/txn sạch trước khi mutate.
3. Chunk size: 5 bài cho pilot (khi 0 bài PUBLISHED), 10 bài cho các chunk sau (theo hợp đồng README §21c).
4. Xác định active batch deterministic: batch đầu tiên (theo thứ tự matrix) còn row chưa terminal (terminal: PUBLISHED, BLOCKED, FAIL). Không còn batch chưa hoàn tất -> bỏ qua publish. Batch KHÔNG còn hard-code B01.
5. `claim <active> --limit N`: đúng N row PLANNED -> WRITING, deterministic theo batch_id + article_id (claim từ chối nếu yêu cầu batch khác batch chưa hoàn tất đầu tiên).
6. `qa <active>`: scoped QA — quality score (rubric 100) + SEO score (0-100) của đúng chunk.
7. `publish <active>`: grouped transactional publish — chỉ row quality PASS VÀ SEO >= 90, không critical; publish cập nhật matrix, hubs, sitemap, checkpoint, reports trong MỘT transaction có marker.
8. Chạy lại toàn bộ test suite + validate_site + validate_content_matrix TRƯỚC khi push (gate trước publish).
9. MỘT commit cho toàn bộ derived state của chunk; push; assert không sót lock/txn marker.

## Quy tắc an toàn

- Writer LUÔN viết đúng thứ tự row kế tiếp của batch (theo thứ tự claim) để claim chọn đúng bài có file.
- Bài quality FAIL/REVIEW/REPAIR không chặn bài PASS trong cùng chunk; publish chỉ đưa row PASS lên PUBLISHED.
- Nếu publish bị từ chối (không có row PASS hợp lệ), trạng thái qa/claim vẫn được commit để audit, workflow báo đỏ.
- Không bao giờ chạy workflow khi có pending txn/lock; dùng `recover` trước (xem docs/RECOVERY.md).
- MATRIX vẫn là source of truth; checkpoint chỉ là operational state (MATRIX > CHECKPOINT).

## Tương tác state fields của matrix

`tools/generate_content_matrix.py` bảo toàn các state fields (`status, score, quality_status, repair_attempts, published_date, last_checked, notes`) khi tái sinh matrix, nên `check_matrix_sync.py` vẫn xanh sau khi sản xuất bắt đầu. Content fields vẫn byte-identical với generator.
