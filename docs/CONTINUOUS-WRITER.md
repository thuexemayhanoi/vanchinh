# Continuous Writer Contract — vòng lặp bắt buộc của external writer

Tài liệu này là nguồn chuẩn duy nhất cho cách một writer run (agent AI bên ngoài) PHẢI hoạt động liên tục. README §24 và AGENTS.md tham chiếu tài liệu này.

## Mô hình canonical (Simple Production Mode)

- Batch = chunk = 50 bài (B01–B40, tổng 2.000). Production loop: WRITE 50 → LIGHT QA → PUBLISH → NEXT 50 → REPEAT.
- Push = TỐI ĐA 50 file bài MỚI một lần (một push = một batch; phần dư cuối < 50 được phép). Push > 50 file mới → `factory-publish.yml` REFUSE.
- GitHub Actions (`factory-publish.yml`) là event-driven: claim đúng ID có file → scoped QA → publish → push derived state. Actions KHÔNG viết prose, KHÔNG gọi Mistral, KHÔNG schedule writer, KHÔNG tự tạo batch kế tiếp.
- Sau publish thành công, trách nhiệm QUAY VỀ writer: fetch fresh main và viết batch kế tiếp ngay nếu runtime còn.

## LOOP (bắt buộc mỗi writer run)

```
FETCH FRESH MAIN
→ RECOVER IF NEEDED (txn marker)
→ RESUME (hoàn tất dở: REPAIR/QA/PASS pending của active batch)
→ WRITE <= 50 (file bài thật theo matrix + docs/ARTICLE-RULES.md)
→ LOCAL SCOPED QA (quality + SEO >= 80, không hạ threshold)
→ PUSH BATCH (≤ 50 file mới)
→ WAIT factory-publish.yml
→ VERIFY (workflow green, Pages deploy, no lock/txn)
→ FETCH FRESH MAIN
→ NEXT <= 50
→ REPEAT
```

## Không được dừng vì

- 50 bài vừa publish
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

- Mỗi batch: FETCH → RECOVER → RESUME → WRITE → QA → PUSH → VERIFY → lặp.
- Một writer/ operator duy nhất được mutate production; lock/ txn của operator khác → không cạnh tranh.
- `factory-publish.yml` tự push derived state → luôn fetch fresh main trước chunk kế; không push từ HEAD cũ; không force push.
- Batch active phải terminal trước khi sang batch khác; `next_batch` không phải quyền claim.
- MATRIX là source of truth; checkpoint là derived operational state.

## Verify (gates theo scope — Simple Production Mode)

VERIFY trong loop này là "workflow green + Pages deploy + no lock/txn" của đúng SHA vừa push.

- Change content-only (batch bài viết) → KHÔNG chạy 4-tier cho mỗi batch. Chỉ cần scoped QA từng bài (quality PASS + SEO >= 80, không critical), publish đúng PASS IDs, light matrix smoke trong factory-publish, CI xanh của đúng SHA.
- Change engine/ workflow/ recovery → TIER 1 + 2 + 3 + 4 bắt buộc trước khi coi là đã fix.
- KHÔNG chạy full-site audit sau mỗi batch. Full audit toàn site chạy MỘT LẦN khi đủ 2.000 bài, sau đó repair theo batch lỗi.
- KHÔNG BAO GIỜ tuyên bố "factory fixed" chỉ vì unit tests xanh.
