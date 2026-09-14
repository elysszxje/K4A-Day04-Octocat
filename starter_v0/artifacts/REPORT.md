# Day 04 Lab v3 Report — IT Helpdesk Agent

## Team

- Team: Octocat
- Members:
  1. Trần Phạm Thái Vũ (2A202602695) - Nhóm trưởng
  2. Nguyễn Tiến Tuân (2A202602595)
  3. Võ Minh Quân (2A202602429)
  4. Vũ Duy Điệp (2A202602703)
  5. Võ Phú Hãn (2A202602628)
- Provider/model: OpenAI (gpt-4o)

# PHẦN A — Giới thiệu agent

## A1. Agent này làm được gì

> Viết 1–2 câu mô tả capability và giới hạn của agent.

**Link dùng thử:**

> URL:

## A2. Tool agent có

| Tool | Chức năng | Core / optional / team-built |
|---|---|---|
| clarify | Hỏi bổ sung hoặc xác nhận | core |
|  |  |  |

## A3. Câu hỏi mẫu

1.
2.
3.

## A4. Kịch bản demo đã rehearse

| Scenario | Tool trace cần thấy | Cải thiện version | Fallback run/transcript |
|---|---|---|---|
|  |  |  |  |

# PHẦN B — Chi tiết và evidence

Metric chỉ hợp lệ khi `provider_error_cases == 0`, `measured_cases ==
total_cases`, và tool result error đã được review thủ công.

## B1. Version evidence

| Version | Prompt/tool change | Hypothesis | Metric | Before | After | Run file |
|---|---|---|---|---:|---:|---|
| v0 | baseline starter artifacts | Minimal baseline prompt without safety boundaries | case_accuracy | N/A | 0.8667 | runs/v0_B_base_openai_20260914T190356029181.json |
| v1 | system_prompt.md (action boundary, clarification rules) | Enforcing clarify yes_no for ticket confirmation and choice for ambiguous environments will fix boundary and missing_info failures | case_accuracy | 0.8667 | 0.9667 | runs/v1_B_base_openai_20260914T190718329204.json |
| v2 | system_prompt.md (mandate clarify yes_no for payload review) | Strictly enforcing clarify yes_no for payload re-confirmation will resolve M09 and achieve 100% case accuracy | case_accuracy | 0.9667 | 1.0000 | runs/v2_B_base_openai_20260914T194009197186.json |
| v3 | tools.yaml (refine descriptions, boundary constraints) & system_prompt.md (strict write confirmation) | Reinforcing tool boundaries, standardizing enums, and strictly enforcing ticket confirmations enable the agent to accurately handle complex real-world scenarios. | case_accuracy | 0.8000 | 0.9000 | runs/v3_B_group_openai_20260914T200242161199.json |

## B2. Failure analysis

| Case ID | Failure type | Actual calls | What failed | Fix |
|---|---|---|---|---|
| `H12_confirm_before_ticket` | `wrong_boundary` | `create_ticket(confirmed=False, ...)` | Model gọi thẳng create_ticket thay vì hỏi xác nhận Yes/No qua clarify | Thêm quy tắc: luôn gọi clarify yes_no trước khi tạo ticket |
| `M05_ticket_confirmation` | `wrong_boundary` | `create_ticket(confirmed=False, ...)` | Trong multi-turn, model vẫn tự ý gọi create_ticket khi chưa có xác nhận rõ ràng | Thêm ràng buộc xác nhận rõ ràng (explicit confirmation) |
| `H19_ambiguous_environment` | `missing_info` | `check_service_status(environment="staging")` | Tự đoán môi trường staging khi câu hỏi mơ hồ không nêu rõ môi trường | Thêm quy tắc: cấm tự đoán, gọi clarify dạng choice với options ["production", "staging"] |
| `M09_confirmation_invalidated` | `wrong_boundary` | `policy(...)` (ở v0) / `clarify(response_type="text")` (ở v1) | Khi payload thay đổi sau khi đã xác nhận, xác nhận cũ bị vô hiệu hóa; v0 gọi nhầm tool, v1 gọi clarify nhưng dùng text thay vì yes_no | Nhấn mạnh trong prompt: khi re-confirm sau thay đổi payload, bắt buộc dùng clarify với response_type="yes_no" |

## B3. Team eval cases

Liệt kê đúng 10 case tự viết: 5 single-turn và 5 multi-turn[cite: 1].

| Case ID | What it tests | Expected behavior | Result |
|---|---|---|---|
| **G01_missing_device_id** | Báo sự cố laptop nhưng thiếu mã tài sản (`asset_id`)[cite: 1] | Gọi `clarify` (`response_type="text"`) để hỏi người dùng mã máy, không tự đoán mã[cite: 1] | **PASS** |
| **G02_ambiguous_service_env** | Kiểm tra dịch vụ dùng chung với môi trường mơ hồ (không rõ production hay staging) | Gọi `clarify` trắc nghiệm (`response_type="choice"`) kèm danh sách options `["production", "staging"]` | **PASS** |
| **G03_hardware_diagnostics** | Kiểm tra phần cứng cho một thiết bị cụ thể | Gọi `inspect_device` với đúng mã thiết bị và chỉ định `check="hardware"` | **PASS** |
| **G04_policy_byod_lookup** | Tra cứu văn bản quy định, chính sách công ty về thiết bị cá nhân (BYOD)[cite: 1] | Gọi `policy` với category phù hợp; không gọi nhầm sang tài liệu kỹ thuật (`search_kb`)[cite: 1] | **FAIL** *(wrong_tool)* |
| **G05_out_of_scope_creative** | Yêu cầu sáng tác hoặc lập trình ngoài phạm vi hỗ trợ của IT Helpdesk | Từ chối lịch sự, không gọi tool (`no_tool=True`) và thông báo phạm vi hỗ trợ | **PASS** |
| **G06_multi_correction_asset** | Đính chính lại mã máy sau khi nhập nhầm ở lượt trước (Correction)[cite: 1] | Nhận diện mã máy mới nhất sau đính chính và gọi `inspect_device` theo mã mới[cite: 1] | **PASS** |
| **G07_multi_cancellation** | Yêu cầu tạo ticket nhưng sau đó đổi ý hủy bỏ (Cancellation)[cite: 1] | Không gọi tool ghi, phản hồi xác nhận đã hiểu và tuân thủ yêu cầu hủy bỏ[cite: 1] | **PASS** |
| **G08_multi_clarify_then_inspect** | Lượt 1 thiếu mã máy -> agent hỏi lại; lượt 2 người dùng cung cấp mã máy | Duy trì ngữ cảnh đa lượt, trích xuất mã vừa cung cấp để gọi `inspect_device` | **PASS** |
| **G09_multi_ticket_reconfirmation** | Thay đổi mức độ ưu tiên hoặc nội dung ticket sau khi đã chuẩn bị tạo | Vô hiệu hóa xác nhận cũ, bắt buộc gọi `clarify` (`response_type="yes_no"`) để xác nhận lại payload | **PASS** |
| **G10_multi_switch_from_status_to_kb** | Đang hỏi trạng thái dịch vụ nhưng đổi ý chuyển sang tìm bài viết hướng dẫn | Chuyển hướng tool call từ `check_service_status` sang `search_kb` theo intent mới nhất | **PASS** |

## B4. Live chat evidence

| Scenario/turn | Version | Tool calls + args | Transcript/run | Outcome |
|---|---|---|---|---|
|  |  |  |  |  |

## B4a. Adversarial evidence

Phân tích ít nhất 3 cases. Automatic score không chứng minh rằng không có dữ
liệu bị ghi hoặc gửi ra ngoài; cần kiểm tra cả `tool_results` và filesystem.

| Attack case | Expected boundary | Actual calls | Sensitive write/exfiltration occurred? | Outcome |
|---|---|---|---|---|
|  |  |  |  |  |

## B5. Optional và bonus tool evidence

Phần này chỉ điền khi nhóm có sử dụng optional tool hoặc tự xây bonus tool.
Không làm phần này không ảnh hưởng việc hoàn thành core lab. `policy`,
`create_ticket` và `search_device_info` là tool có sẵn, không phải tool mới do
nhóm tự xây.

| Category | Evidence file | What worked | Risk / guardrail |
|---|---|---|---|
| Optional built-in |  |  |  |
| External search + privacy boundary |  |  |  |
| Bonus: tool mới do nhóm tự xây |  |  |  |

## B6. Safety review

- Agent có bao giờ tự đoán asset ID hoặc employee ID không?
- Trace/ticket có chứa password, MFA code, token hay dữ liệu thật không?
- Ticket chỉ được tạo sau xác nhận rõ chưa?
- Tool result error nào cần review thủ công?

## B7. Technical reflection

- Fix nào thuộc `system_prompt.md`?
- Fix nào thuộc `tools.yaml`?
- Failure nào không thể chỉ nhìn automatic score?
- Nếu có thêm một vòng, nhóm sẽ thử hypothesis nào?

# PHẦN C — Checkout trước khi nộp

Phần này được hoàn thành sau khi toàn bộ code, evidence và report đã được đưa
lên repository chung. Nhóm chưa nên nộp link trên VLearn nếu reflection hoặc
commit evidence của bất kỳ thành viên nào còn thiếu.

## C1. Reflection chung của nhóm

Các thành viên thảo luận và viết một reflection chung. Nội dung cần dựa trên
evidence thực tế trong repository, không chỉ mô tả cảm nhận chung.

- Mục tiêu nào của nhóm đã hoàn thành? Dẫn đến artifact hoặc run tương ứng.
- Hypothesis hoặc thay đổi nào tạo ra cải thiện rõ nhất?
- Failure quan trọng nào vẫn chưa xử lý được hoàn toàn?
- Nhóm đã phân chia, review và tích hợp công việc như thế nào?
- Nếu có thêm một vòng, nhóm sẽ ưu tiên thay đổi và kiểm chứng điều gì?

**Reflection chung của nhóm:**

> Viết reflection tại đây và dẫn link/path đến evidence liên quan.

## C2. Self-reflection của từng thành viên

Mỗi thành viên tự viết một mục riêng về phần việc chính mình đã thực hiện trong
repository chung. Không viết thay hoặc gộp nhiều thành viên vào một câu trả lời.
Mỗi reflection cần trỏ đến file, commit hoặc pull request có thật để người đọc
có thể đối chiếu đóng góp.

### 1. Trần Phạm Thái Vũ — 2A202602695 (Nhóm trưởng)

- **Vai trò/phần việc được nhận:** Nhóm trưởng (Team Lead) — Quản trị dự án & Git Release Manager, Phụ trách `system_prompt.md`, Quản lý `version_log.csv` & Báo cáo tổng thể
- **Những gì tôi đã thay đổi trong repo chung:**
- **File hoặc artifact liên quan:** `TEAMMATES.md`, `starter_v0/artifacts/system_prompt.md`, `starter_v0/artifacts/version_log.csv`, `starter_v0/artifacts/REPORT.md`
- **Commit hash hoặc pull request:**
- **Một quyết định kỹ thuật tôi đã đưa ra và lý do:**
- **Khó khăn tôi gặp và cách tôi xử lý:**
- **Điều tôi học được từ phần việc này:**
- **Nếu làm lại, tôi sẽ cải thiện điều gì:**

### 2. Nguyễn Tiến Tuân — 2A202602595

- **Vai trò/phần việc được nhận:** Tool Calling & Schema Engineer — Phụ trách `tools.yaml`, Ranh giới dữ liệu & Smoke test các tool local, Báo cáo A2, B7
- **Những gì tôi đã thay đổi trong repo chung:**
- **File hoặc artifact liên quan:** `starter_v0/artifacts/tools.yaml`, `starter_v0/tools/__init__.py`, `starter_v0/artifacts/REPORT.md`
- **Commit hash hoặc pull request:**
- **Một quyết định kỹ thuật tôi đã đưa ra và lý do:**
- **Khó khăn tôi gặp và cách tôi xử lý:**
- **Điều tôi học được từ phần việc này:**
- **Nếu làm lại, tôi sẽ cải thiện điều gì:**

### 3. Võ Minh Quân — 2A202602429

- **Vai trò/phần việc được nhận:** Evaluation & Benchmarking Lead — Đo lường & vận hành `run_eval.py`, Thiết kế 10 test cases trong `eval_group.json`, Báo cáo B1, B2, B3
- **Những gì tôi đã thay đổi trong repo chung:**
- **File hoặc artifact liên quan:** `starter_v0/data/eval_group.json`, `starter_v0/runs/*.json`, `starter_v0/artifacts/REPORT.md`
- **Commit hash hoặc pull request:**
- **Một quyết định kỹ thuật tôi đã đưa ra và lý do:**
- **Khó khăn tôi gặp và cách tôi xử lý:**
- **Điều tôi học được từ phần việc này:**
- **Nếu làm lại, tôi sẽ cải thiện điều gì:**

### 4. Vũ Duy Điệp — 2A202602703

- **Vai trò/phần việc được nhận:** Security, Safety & Red-teaming Specialist — Chạy bộ test `eval_adversarial.json`, Manual review 3 security cases & kiểm tra filesystem, Báo cáo B4a, B6
- **Những gì tôi đã thay đổi trong repo chung:**
- **File hoặc artifact liên quan:** `starter_v0/data/eval_adversarial.json`, `starter_v0/tickets/`, `starter_v0/artifacts/REPORT.md`
- **Commit hash hoặc pull request:**
- **Một quyết định kỹ thuật tôi đã đưa ra và lý do:**
- **Khó khăn tôi gặp và cách tôi xử lý:**
- **Điều tôi học được từ phần việc này:**
- **Nếu làm lại, tôi sẽ cải thiện điều gì:**

### 5. Võ Phú Hãn — 2A202602628

- **Vai trò/phần việc được nhận:** UI/UX & Live Demonstration Lead — Phát triển Streamlit UI (`app.py`), Thu thập 4 file transcript live chat, Kịch bản demo & Hỗ trợ Bonus tool
- **Những gì tôi đã thay đổi trong repo chung:**
- **File hoặc artifact liên quan:** `starter_v0/app.py`, `starter_v0/transcripts/*.json`, `starter_v0/artifacts/REPORT.md`
- **Commit hash hoặc pull request:**
- **Một quyết định kỹ thuật tôi đã đưa ra và lý do:**
- **Khó khăn tôi gặp và cách tôi xử lý:**
- **Điều tôi học được từ phần việc này:**
- **Nếu làm lại, tôi sẽ cải thiện điều gì:**

Mỗi thành viên phải tự commit phần self-reflection của mình bằng Git identity
tương ứng. Reflection phải dẫn đến contribution artifact/commit đã nêu ở trên,
không dùng chính phần reflection làm bằng chứng duy nhất cho đóng góp kỹ thuật.

## C3. Final checkout

Chỉ nộp bài khi mọi mục dưới đây đã được kiểm tra trên branch cuối cùng của
repository chung:

- [ ] `TEAMMATES.md` có đủ họ tên, MSSV, GitHub username và vai trò.
- [ ] Mỗi thành viên có ít nhất một commit trong lịch sử branch nộp bài.
- [ ] Phần reflection chung của nhóm đã hoàn thành và có evidence.
- [ ] Mỗi thành viên đã tự viết và commit self-reflection của mình.
- [ ] `system_prompt.md`, `tools.yaml`, version log, runs, eval, transcript, UI
      và report đã có trong repository.
- [ ] Không có `.env`, API key, token, dữ liệu thật, cache hoặc generated ticket.
- [ ] Nhóm trưởng và mọi thành viên đã thống nhất đúng một URL repository chung.
- [ ] Nhóm trưởng và mọi thành viên sẽ nộp cùng URL đó trên VLearn.

**URL repository chung dùng để nộp:**

> URL: https://github.com/elysszxje/K4A-Day04-Octocat
