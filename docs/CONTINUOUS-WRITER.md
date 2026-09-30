# Continuous Writer Contract — vòng lặp bắt buộc của external writer

Tài liệu này là nguồn chuẩn duy nhất cho cách một writer run (agent AI bên ngoài) PHẢI hoạt động liên tục. README §24 và AGENTS.md tham chiếu tài liệu này.

## Mô hình canonical

- Batch = 50 bài (B01–B40, tổng 2.000).
- Writer chunk = TỐI ĐA 10 bài. Chunk chuẩn 10; chunk phần dư cuối batch < 10 được phép. Pilot 5 chỉ khi contract hiện hành yêu cầu tường minh.
- Push = TỐI ĐA 10 file bài MỚI một lần. Push > 10 file mới → `factory-publish.yml` REFUSE.
- KHÔNG BAO GIỜ pre-claim/ viết/ push cả 50 row batch một lượt.
- GitHub Actions (`factory-publish.yml`) là event-driven: claim đúng ID có file → QA → publish → push derived state. Actions KHÔNG viết prose, KHÔNG gọi Mistral, KHÔNG schedule writer, KHÔNG tự tạo chunk kế tiếp.
- Sau publish thành công, trách nhiệm QUAY VỀ writer: fetch fresh main và viết chunk kế tiếp ngay nếu runtime còn.

## LOOP (bắt buộc mỗi writer run)

```
FETCH FRESH MAIN
→ RECOVER IF NEEDED (txn marker)
→ RESUME (hoàn tất dở: REPAIR/QA/PASS pending của active batch)
→ WRITE <= 10 (file bài thật theo matrix + docs/ARTICLE-RULES.md)
→ LOCAL SCOPED QA (quality + SEO, không hạ threshold)
→ PUSH CHUNK (≤ 10 file mới)
→ WAIT factory-publish.yml
→ VERIFY (workflow green, Pages deploy, no lock/txn)
→ FETCH FRESH MAIN
→ NEXT <= 10
→ REPEAT
```

## Không được dừng vì

- 5 hoặc 10 bài vừa xong
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

- Mỗi chunk: FETCH → RECOVER → RESUME → WRITE → QA → PUSH → VERIFY → lặp.
- Một writer/ operator duy nhất được mutate production; lock/ txn của operator khác → không cạnh tranh.
- `factory-publish.yml` tự push derived state → luôn fetch fresh main trước chunk kế; không push từ HEAD cũ; không force push.
- Batch active phải terminal trước khi sang batch khác; `next_batch` không phải quyền claim.
- MATRIX là source of truth; checkpoint là derived operational state.

## Verify theo 4-Tier Verification Contract

VERIFY trong loop này là "workflow green + Pages deploy + no lock/txn" của đúng SHA vừa push — KHÔNG thay thế 4-Tier Verification Contract (AGENTS.md, docs/CONTENT-FACTORY.md §4-Tier):

- "CI GREEN" KHÔNG đồng nghĩa production-safe nếu tier áp dụng cho change đó chưa PASS.
- Change engine/ workflow/ recovery → TIER 1 + 2 + 3 + 4 bắt buộc trước khi coi là đã fix.
- Change content-only (bài viết) → tier theo scope; publish gate hiện hữu vẫn bắt buộc.
- KHÔNG BAO GIỜ tuyên bố "factory fixed" chỉ vì unit tests xanh.
