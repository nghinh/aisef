# R1–R14 — bằng chứng cho từng yêu cầu

Mỗi dòng chỉ tới **thứ kiểm được**: một lớp test chạy được, hoặc một
artifact có thật trong kho. Không dòng nào là lời khẳng định suông.

Dạng *tests/test_…py::TenLop* là một lớp test; chạy một dòng bất kỳ bằng:

```bash
python3 -m unittest tests.test_plan.TestStopsAtGates -v
```

Một test trong `tests/test_requirements_evidence.py` đọc chính file này và
bắt lỗi nếu có dòng trỏ tới lớp test không còn tồn tại — bảng này không mục
rữa được.

| # | Yêu cầu | Bằng chứng | Ghi chú |
|---|---|---|---|
| R1 | Đầu vào là một file `docs/requirements.md` | `tests/test_cli.py::TestDoctor` · `tests/test_detect_stack.py::TestDetect` | `doctor` trượt khi thiếu file; stack dò từ chính file đó |
| R2 | Bộ prompt chuẩn hoá | `tests/test_prompts.py::TestCatalog` · `tests/test_prompts.py::TestPromptContent` | prompt có phiên bản, biến rỗng là lỗi, nội dung bắt buộc được kiểm |
| R3 | Setup nạp skill vào dự án | `tests/test_install.py::TestApply` · `tests/test_security_filter.py::TestAgainstRealCorpus` | 142 skill cài thật; kho 818 skill bảo mật lọc còn phần phòng thủ |
| R4 | BMAD sinh tài liệu, mỗi story một file | `tests/test_plan.py::TestStopsAtGates` · `tests/test_story_split.py::TestSplit` | chuỗi pha dừng đúng cổng; 12 story từ `epics.md` thật, mỗi story một file |
| R5 | Mockup HTML cho mọi màn hình | `tests/test_mockup.py::TestExtractContract` · `tests/test_mockup.py::TestGate` | dựng bằng chromium thật; thiếu màn hình thì cổng chặn |
| R6 | Coding agent map với mockup | `tests/test_mockup_map.py::TestLoadHalf` · `tests/test_mockup_map.py::TestVerifyHalf` | nạp đúng một lát cắt; mở route thật rồi đối chiếu |
| R7 | Đủ 6 nhóm harness | `tests/test_prompts.py` (1) · `tests/test_tools.py` (2) · `tests/test_sandbox.py::TestIsolation` (3) · `tests/test_run.py::TestOrchestration` (4) · `tests/test_guardrails.py` (5) · `tests/test_observe.py` (6) | mỗi nhóm một bộ test riêng; sandbox chạy trên docker thật |
| R8 | Deep review · test · bảo mật | `tests/test_implement.py::TestRetry` · `tests/test_qa.py::TestRunningChecks` · `tests/test_qa.py::TestUnconfiguredIsNotPassing` | rà soát phiên mới; 10 loại kiểm định; "chưa cấu hình" ≠ "đạt" |
| R9 | DevSecOps | `tests/test_deploy.py::TestCiWorkflow` · `tests/test_deploy.py::TestPreDeployGate` | CI sinh bằng code; cổng cuối chấm từ trạng thái thật |
| R10 | Bốn bề mặt Claude/OpenCode | `tests/test_clients.py::TestCapabilityDeclaration` · `tests/test_compile.py::TestOpenCodePlugin` | năng lực **khai** chứ không giả định. OpenCode nâng lên chặn-tại-nguồn ngày 2026-09-05 sau khi có phép thử trên agent thật; STORY-02-01 của dự án `par` do agent OpenCode hiện thực trọn vẹn, qua cổng, merge vào main |
| R11 | Chuẩn hoá, chuyên nghiệp | `tests/test_constitution.py` · `docs/SOLUTION.md` · `docs/EXECUTION-PLAN.md` | hiến pháp sinh giống nhau cho mọi client; quyết định có nơi tra |
| R12 | Chất lượng chứng minh được | `tests/test_gate.py` · `tests/test_gate_qualification.py` · `tests/test_report.py::TestTraceability` | cổng story 15 mục (`gate.CHECK_NAMES`) đọc từ bằng chứng, mỗi mục có 3 control (positive · negative · env, ADR-005 V9); báo cáo nêu thẳng FR chưa phủ |
| R13 | Người duyệt từng bước | `tests/test_approvals.py` · `tests/test_plan.py::TestStopsAtGates` | phê duyệt gắn với băm nội dung; sửa tầng trên làm tầng dưới `stale` |
| R14 | Epic tuần tự, story song song | `tests/test_scheduler.py` · `tests/test_run.py::TestOrchestration` | cùng đợt chỉ khi hết phụ thuộc **và** phạm vi ghi rời nhau |
