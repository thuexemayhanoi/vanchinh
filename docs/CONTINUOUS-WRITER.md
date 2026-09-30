# Continuous Writer Contract — vòng lặp bắt buộc của external writer

Tài liệu này là nguồn chuẩn duy nhất cho cách một writer run (agent AI bên ngoài) PHẢI hoạt động liên tục. README §24 và AGENTS.md tham chiếu tài liệu này.

## Mô hình canonical (Simple Production Mode — MICRO CONTINUOUS LOOP)

- Chunk làm việc = 2 bài mỗi lượt writer (micro push). Production loop: WRITE 2 → SCOPED QA → PUSH 2 → WAIT CI GREEN → NEXT 2 → REPEAT. Lý do: push sớm từng cặp 2 bài tạo safe checkpoint trên main, chống mất tiến độ khi workspace reset; KHÔNG giữ nhiều bài chưa push trong workspace.
- Batch (B01–B40, tổng 2.000) vẫn là đơn vị tổ chức của matrix; writer làm việc theo các cặp 2 bài liên tiếp trong batch active cho đến khi batch đó terminal.
- Push = TỐI ĐA 50 file bài MỚI một lần vẫn là hard invariant của workflow (push > 50 file mới → `factory-publish.yml` REFUSE); micro loop chuẩn push đúng 2 file mới mỗi lần.
- GitHub Actions (`factory-publish.yml`) là event-driven: claim đúng ID có file → scoped QA → publish → push derived state. Actions KHÔNG viết prose, KHÔNG gọi Mistral, KHÔNG schedule writer, KHÔNG tự tạo chunk kế tiếp.
- Sau publish thành công, trách nhiệm QUAY VỀ writer: fetch fresh main và viết cặp 2 bài kế tiếp NGAY nếu runtime còn.

## LOOP (bắt buộc mỗi writer run)

```
FETCH FRESH MAIN
→ RECOVER IF NEEDED (txn marker)
→ RESUME (hoàn tất dở: REPAIR/QA/PASS pending của active batch)
→ WRITE 2 (file bài thật theo matrix + docs/ARTICLE-RULES.md)
→ LOCAL SCOPED QA (quality PASS + SEO >= 80, không hạ threshold, không critical)
→ PUSH 2 (file mới; safe checkpoint trên main)
→ WAIT factory-publish.yml + CI GREEN
→ VERIFY (workflow green, Pages deploy, no lock/txn)
→ FETCH FRESH MAIN
→ WRITE 2 NEXT
→ REPEAT (không dừng sau mỗi cặp 2 bài)
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

## Quy tắc an toàn mỗi vòng

- Mỗi cặp 2 bài: FETCH → RECOVER → RESUME → WRITE 2 → QA → PUSH 2 → VERIFY → lặp.
- Một writer/ operator duy nhất được mutate production; lock/ txn của operator khác → không cạnh tranh.
- `factory-publish.yml` tự push derived state → luôn fetch fresh main trước cặp kế; không push từ HEAD cũ; không force push.
- Batch active phải terminal trước khi sang batch khác; `next_batch` không phải quyền claim.
- MATRIX là source of truth; checkpoint là derived operational state.

## Verify (gates theo scope — Simple Production Mode)

VERIFY trong loop này là "workflow green + Pages deploy + no lock/txn" của đúng SHA vừa push.

- Change content-only (batch bài viết) → KHÔNG chạy 4-tier cho mỗi batch. Chỉ cần scoped QA từng bài (quality PASS + SEO >= 80, không critical), publish đúng PASS IDs, light matrix smoke trong factory-publish, CI xanh của đúng SHA.
- Change engine/ workflow/ recovery → TIER 1 + 2 + 3 + 4 bắt buộc trước khi coi là đã fix.
- KHÔNG chạy full-site audit sau mỗi batch. Full audit toàn site chạy MỘT LẦN khi đủ 2.000 bài, sau đó repair theo batch lỗi.
- KHÔNG BAO GIỜ tuyên bố "factory fixed" chỉ vì unit tests xanh.
