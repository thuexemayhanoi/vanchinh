# Continuous Writer Contract — vòng lặp bắt buộc của external writer

Tài liệu này là nguồn chuẩn duy nhất cho cách một writer run (agent AI bên ngoài) PHẢI hoạt động liên tục. README §24 và AGENTS.md tham chiếu tài liệu này.

## Mô hình canonical (Simple Production Mode — TURBO WRITE-AHEAD QUEUE)

- Đơn vị QA/publish của factory = PAIR 2 bài. Writer dùng WRITE-AHEAD QUEUE: một push xếp hàng 2..10 bài mới, `factory-publish.yml` tự chia queue thành các pair 2 và tiêu thụ tuần tự (2 → QA/publish → 2 → QA/publish → …) trong CÙNG một production run. Push sớm cả queue tạo safe checkpoint trên main, chống mất tiến độ khi workspace reset.
- Batch (B01–B40, tổng 2.000) vẫn là đơn vị tổ chức của matrix; writer làm việc theo các ID liên tiếp trong batch active cho đến khi batch đó terminal.
- Push = TỐI ĐA 10 file bài MỚI một lần là hard invariant của workflow (push > 10 file mới → `factory-publish.yml` REFUSE; queue tối thiểu 2 bài).
- Multi-writer: tối đa 3 writer chạy song song, KHÔNG BAO GIỜ trùng ID, qua lease registry `scripts/writer_claim.py` (xem dưới).
- GitHub Actions (`factory-publish.yml`) là event-driven: queue đúng ID có file → từng pair: claim → scoped QA → publish → checkpoint → push derived state. Actions KHÔNG viết prose, KHÔNG gọi Mistral, KHÔNG schedule writer, KHÔNG tự tạo chunk kế tiếp.
- Sau publish thành công, trách nhiệm QUAY VỀ writer: fetch fresh main và viết queue kế tiếp NGAY nếu runtime còn.

## LOOP (bắt buộc mỗi writer run)

```
FETCH FRESH MAIN
→ RECOVER IF NEEDED (txn marker)
→ RESUME (hoàn tất dở: REPAIR/QA/PASS pending của active batch)
→ CLAIM (writer_claim.py lease 2..10 ID kế tiếp chưa bị ai lease)
→ WRITE 2..10 (file bài thật theo matrix + docs/ARTICLE-RULES.md)
→ LOCAL SCOPED QA từng bài (quality PASS + SEO >= 80, không hạ threshold, không critical)
→ PUSH QUEUE (file mới; safe checkpoint trên main)
→ WAIT factory-publish.yml + CI GREEN (factory tự tiêu thụ từng pair 2)
→ VERIFY (workflow green, Pages deploy, no lock/txn, queue report không fatal)
→ RELEASE lease đã publish (writer_claim.py release)
→ FETCH FRESH MAIN
→ QUEUE NEXT
→ REPEAT (không dừng sau mỗi queue)
```

## Không được dừng vì

- 2 bài vừa publish (một micro chunk vừa xong)
- một workflow vừa xanh
- một Pages deploy vừa xong
- một batch vừa terminal
- progress report vừa được sinh
- tests vừa xanh

Đó là checkpoint, KHÔNG phải điểm kết thúc.

## Chỉ được dừng khi

1. Toàn bộ 2.000 production row terminal hợp lệ (PUBLISHED/BLOCKED/FAIL theo contract), hoặc
2. runtime/ session/ tool limit buộc dừng — dừng tại điểm an toàn: workflow đã xong, fresh main đã fetch, không lock, không txn; và
3. blocker thật sự cần con người (lock của operator khác, txn mơ hồ, validation failure critical).

Dừng tạm do rate-limit/ lỗi connector tạm thời KHÔNG PHẢI quyền restart factory — retry sau.

## TURBO MULTI-WRITER — lease protocol (`scripts/writer_claim.py`)

Mục tiêu: 3 writer → mỗi writer buffer tối đa 10 bài → push → 1 factory queue → 2+2+2+2+2.

- Lease registry: `data/batches/writer-claims.json` (env `WRITER_CLAIMS`). Writer commit + push registry này; path nằm ngoài paths filter của `factory-publish.yml` nên KHÔNG kích hoạt production run.
- `python3 scripts/writer_claim.py claim --writer W1 [--count N|--ids A,B]`: lease N row PLANNED của ACTIVE batch (batch chưa terminal đầu tiên theo thứ tự matrix) — KHÔNG BAO GIỜ claim batch tương lai. Trừ các ID đang bị lease sống của writer khác. Cap 10 ID sống/writer; tối đa 3 writer; TTL 48h.
- `python3 scripts/writer_claim.py release --writer W1 --ids A,B`: bỏ lease (chạy sau khi factory publish xong ID đó, hoặc khi bỏ bài).
- `python3 scripts/writer_claim.py show`: trạng thái registry + các ID PLANNED còn tự do (tự prune trước khi báo cáo).
- `python3 scripts/writer_claim.py prune`: rà soát hiệu lực lease NGAY BÂY GIỜ theo đúng thứ tự: (a) lease hết TTL bị drop; (b) ID không còn là row PLANNED của active batch (batch khác / đã publish / blocked) bị drop; (c) writer hết ID hợp lệ bị xóa; (d) registry vượt 3 writer → giữ 3 claim mới nhất. Prune cũng tự chạy trong mọi lệnh claim/release/show/merge (self-heal, persist khi có thay đổi).
- `python3 scripts/writer_claim.py merge --file registry.json`: gộp registry từ remote vào local khi push registry thua race (non-fast-forward). ID incoming phải là PLANNED của active batch — ID lạ/batch khác bị từ chối. Xung đột ID: claimed_at sớm hơn thắng (thứ bậc phụ: tên writer nhỏ hơn); writer thua giữ các ID còn lại và claim bù sau. KHÔNG BAO GIỜ force push registry.
- Giao thức push race: fetch fresh main → `merge` registry remote → claim lại phần còn tự do → push lại. Ép push registry bị từ chối là vi phạm contract.
- Một writer push tối đa 10 file bài mới (queue contract); queue bị từ chối (refuse) thì sửa theo lý do refuse rồi push lại, KHÔNG chia nhỏ bằng cách sửa workflow.
- Bài trong buffer không còn khớp repository truth (ID đã PUBLISHED / đổi batch / repair) → revalidate từ matrix mới trước khi push; tuyệt đối không ép push.
- Factory REFUSE vì batch đổi hoặc lease stale → release lease sai batch (`prune`), fetch fresh main, claim lại từ active batch MỚI; KHÔNG viết batch tương lai chờ factory. Queue 2..10 và nhịp factory 2+2+2+2+2 giữ nguyên.

## Quy tắc an toàn mỗi vòng

- Mỗi queue: FETCH → RECOVER → RESUME → CLAIM → WRITE 2..10 → QA → PUSH QUEUE → VERIFY → RELEASE → lặp.
- Tối đa 3 writer song song; ID phân phối qua lease registry, KHÔNG BAO GIỜ viết ID do writer khác giữ lease.
- `factory-publish.yml` tự push derived state → luôn fetch fresh main trước cặp kế; không push từ HEAD cũ; không force push.
- Batch active phải terminal trước khi sang batch khác; `next_batch` không phải quyền claim.
- MATRIX là source of truth; checkpoint là derived operational state.

## Verify (gates theo scope — Simple Production Mode)

VERIFY trong loop này là "workflow green + Pages deploy + no lock/txn" của đúng SHA vừa push.

- Change content-only (batch bài viết) → KHÔNG chạy 4-tier cho mỗi batch. Chỉ cần scoped QA từng bài (quality PASS + SEO >= 80, không critical), publish đúng PASS IDs, light matrix smoke trong factory-publish, CI xanh của đúng SHA.
- Change engine/ workflow/ recovery → TIER 1 + 2 + 3 + 4 bắt buộc trước khi coi là đã fix.
- KHÔNG chạy full-site audit sau mỗi batch. Full audit toàn site chạy MỘT LẦN khi đủ 2.000 bài, sau đó repair theo batch lỗi.
- KHÔNG BAO GIỜ tuyên bố "factory fixed" chỉ vì unit tests xanh.
