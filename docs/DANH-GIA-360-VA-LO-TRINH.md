# AISEF — đánh giá 360° bản hiện tại và lộ trình lên bản sau

AISEF = **AI Software Engineering Framework**.

Ngày 2026-09-06. Bản đang có: **`aisef 0.2.0`** trên PyPI (đổi tên
`aisdlc` → `aisef`, sửa lỗi 31; kho GitHub nay là `nghinh/aisef`). Mọi con số dưới đây đọc từ
mã, từ bằng chứng trên đĩa, hoặc từ lần chạy thật — chỗ nào chưa đo thì viết là
chưa đo.

---

## 1. Kết luận trong một trang

**Đã làm được.** Framework đi được trọn vòng đời trên một dự án thật, và điều
đáng giá hơn cả tính năng là **cách nó biết mình đúng**: 16 mục cổng story mỗi
mục có ba phép đối chứng, 1 678 test đơn vị chạy trong ba phút không cần Docker,
hợp quy 10 phép trên client thật, 31 lỗi thật đều tìm bằng đo và đều có test đỏ
khi hoàn nguyên. Không có chỗ nào "chắc là chạy được".

**Chưa làm được.** Bằng chứng còn hẹp: **một** dự án dogfood, **một** epic được
nghiệm thu, **một** client hạng nhất, **không** phép đo hiệu quả nào so với
đường cơ sở (không có nhóm đối chứng "làm tay" hay "agent trần"). Ba năng lực
đã dựng nhưng chưa từng chạy thật: benchmark với client thật, vòng cải tiến
dưới luật mới, hợp quy chống-gian C11/C12.

**Rủi ro lớn nhất không phải kỹ thuật.** Nó là: framework này tốn ~14 đô la
lập kế hoạch và 2–8 đô la mỗi story, mà **chưa ai đo** nó tiết kiệm hay tiêu
thêm bao nhiêu so với cách làm khác. Bản 0.3.0 nên trả lời câu ấy trước khi
thêm bất kỳ tính năng nào.

---

## 2. Số liệu nền

| Hạng mục | Số |
|---|---|
| Mã framework | 21 739 dòng Python, không phụ thuộc ngoài thư viện chuẩn |
| Mã kiểm thử | 20 876 dòng · 1 678 test · 189 giây · không cần Docker |
| Test cần Docker thật | 88, bật bằng `AISEF_TEST_DOCKER=1` |
| Lệnh CLI | 28 |
| Mục cổng story | 16, **16/16** có đủ ba control (dương tính · âm tính · môi trường) |
| Guard | 8, nối vào 3 mốc vòng đời |
| Khoá cấu hình | 55 |
| Hợp quy client | 10 phép trên agent thật: Claude 10/10, OpenCode 9/10 |
| Hợp quy sandbox | 5 phép, Docker 5/5 |
| Kho benchmark | 18 task lỗi thật, 15/15 hợp lệ trong số đã đo |
| Lỗi thật đã ghi | 31, mỗi lỗi một dòng trong bảng phân loại 11 lớp nguyên nhân |
| Dogfood `par` | 3/3 story, 5,79 đô la |
| Dogfood `e9` | 23 story trong kế hoạch, EPIC-01 **7/7**, sổ hành vi 42 verified · 17 gap · 6 reopened, 6 vòng cải tiến, ~563 đô la |

---

## 3. Đánh giá theo tám mặt

### 3.1 Tính đúng của cổng — **mạnh**

Mỗi mục cổng có ba phép đối chứng đọc bằng AST, nên "cổng có chấm đúng không"
là câu trả lời được bằng lệnh chứ không bằng niềm tin. Sáu kết cục tách bạch
(`✅ ✗ ⚠ ○ ◇ –`) là quyết định thiết kế đắt nhưng đúng: phần lớn 31 lỗi thật
thuộc lớp "phân loại kết cục sai" hoặc "hai luật cho một sự thật".

Điểm yếu: cổng chấm **trên bằng chứng**, nên chất lượng cổng phụ thuộc chất
lượng bằng chứng. Ba mục quan trọng nhất (`rà soát`, `bảo mật`, và một nửa
`test có kiểm được story`) do model chấm — và phép thử C11 vừa cho thấy
**reviewer model bỏ lọt** đúng ca mà cổng máy bắt được. Đây là bằng chứng ủng
hộ kiến trúc hai lớp, đồng thời là cảnh báo: đừng bao giờ để model thay cổng máy.

### 3.2 Cách ly và an toàn — **khá, có một lỗ hổng đã khai**

Guard chặn *trước* khi tool chạy, đã chứng minh trên agent thật cho cả hai
client. Sandbox có hợp đồng bảo đảm và nêu tên thứ thiếu thay vì im lặng.

Ba việc còn hở, đều đã khai chứ không giấu:
- **S1**: agent chạy trong container chưa có cách ly credential → V1 để agent
  trên host, chỉ kiểm định trong container.
- **V12 egress allowlist**: chưa làm; phiên agent ra mạng theo cấu hình client.
- Bộ skill ngoài (5 nguồn) chỉ được **quét một lần** bằng model tìm chỉ dẫn
  tiêm; chưa có kiểm định lặp lại theo lịch.

### 3.3 Bằng chứng và truy vết — **mạnh**

Sổ hành vi (verified/gap/reopened) chiếu lại từ evidence mỗi lần, chỉ mục cho
prompt, `aisef evidence <id>` tra đường đời một yêu cầu, `aisef issues` xuất
bảng. Báo cáo nghiệm thu ghi cả phạm vi nghiệm thu — nghĩa là "chưa làm" không
thể bị đọc nhầm thành "đã xong".

Điểm yếu: chưa có **chuỗi thời gian** (chi phí/hành vi theo tuần), chưa có bảng
điều khiển; và bằng chứng nằm rải trong `_bmad-output/` của từng dự án, chưa có
cách gộp nhiều dự án.

### 3.4 Chi phí — **đo được, chưa tối ưu, chưa có đối chứng**

Số thật: lập kế hoạch ~14 đô la; mockup 1,5–2,3 đô la mỗi màn; story 2–8 đô la
mỗi lượt; reviewer là phiên riêng nên **nhân đôi** chi phí mỗi story. Dogfood e9
tiêu ~563 đô la cho 10 story xong.

Chưa có: so sánh với đường cơ sở, phân tích đâu là phần đắt vô ích (ví dụ tỉ lệ
lượt trượt vì kế hoạch sai so với vì code sai), và cơ chế dừng sớm theo ngân
sách ở mức **dự án** (mới có ở mức vòng cải tiến).

### 3.5 Độ tin cậy khi vận hành — **trung bình**

Chạy được nhiều story song song với worktree riêng, dừng giữa chừng chạy lại
đúng chỗ. Nhưng: mọi thứ nằm trên **một máy**, không hàng đợi, không phục hồi
sau khi máy tắt giữa phiên agent; Docker trên macOS là nút cổ chai thật (6–18
giây một container, đã phải bỏ Docker khỏi test đơn vị); và phép kiểm đầu-cuối
nhạy tải máy đã một lần làm story trượt oan (đã có `--verify-only --repeat`).

### 3.6 Trải nghiệm người dùng — **vừa đủ, mới có hướng dẫn**

Trước hôm nay chưa có tài liệu hướng dẫn dùng; nay đã có sổ tay 18 phần. Vẫn
còn: 55 khoá cấu hình là nhiều cho người mới (đã có mặc định hợp lý và lệnh
`doctor` chỉ đúng chỗ sửa, nhưng chưa có `aisef init --stack react` sinh sẵn
lệnh test); thông báo lỗi tốt ở guard, còn ở pha lập kế hoạch thì vẫn dài.

### 3.7 Chất lượng nội tại — **mạnh so với tuổi đời**

Test/mã ≈ 0,96 dòng test trên một dòng mã; mỗi lỗi thật đều kèm test hồi quy;
tài liệu bị test kiểm (`test_meta` đọc mã rồi so với tài liệu). Rủi ro: tài liệu
tiếng Việt hạn chế người đóng góp ngoài; và 55 khoá cấu hình cộng 16 mục cổng là
bề mặt lớn để giữ tương thích về sau.

### 3.8 Vị thế so với công cụ ngoài — **khác biệt rõ, chưa chứng minh bằng số**

Đã đọc mã 10 dự án ngoài và hấp thụ 9 pattern (nop control, provider contract,
qualification, bench factory…). Khác biệt cốt lõi: **cổng máy chấm trên bằng
chứng có SHA** và **reviewer tách khỏi developer**. Chưa có: một lần chạy
benchmark chung để so pass@k với công cụ khác.

---

## 4. Việc còn tồn tại, xếp theo mức

| Mức | Việc | Vì sao còn |
|---|---|---|
| **Chặn tuyên bố năng lực** | Chạy benchmark với client thật (pass@1/pass@3 trên 18 task) | mỏ task đã có, chưa từng chạy |
| | Đo lại lợi ích vòng cải tiến theo luật nop control | ba vòng "+1" cũ không còn hợp lệ |
| | Hợp quy C11/C12 (agent cố gian, lỗi cài sẵn) | mới xong 2 ca thì hết hạn mức |
| **Chặn dùng rộng** | Cách ly credential cho agent trong container (S1) | chưa có cách không làm yếu cách ly |
| | Egress allowlist (V12) | chưa làm |
| | Hàng đợi/khôi phục khi máy tắt | thiết kế một máy, một tiến trình |
| **Chất lượng** | Coverage dogfood 84,16 % < ngưỡng 0,85 | là sự thật của corpus, không hạ ngưỡng |
| | `mutation`, `image-scan` chưa chạy được ở môi trường nghiệm thu | thiếu công cụ |
| | Hiệu chuẩn chiều "láng giềng VERIFIED" của cổng cỡ story | trọng số đang để 0 |
| **Mở rộng** | OpenCode lên hạng nhất | thiếu đầu ra máy đọc ổn định |
| | A/B bản đồ mã, A/B skill | hoãn vì tốn tiền, chưa quyết định tính đúng |
| | Nhiều epic/nhiều dự án trong một vòng cải tiến (R11) | chờ R3 có số |

---

## 5. Lộ trình đề xuất

Nguyên tắc xếp thứ tự: **đo trước, mở rộng sau**. Mỗi bản có một câu hỏi phải
trả lời được bằng số; không trả lời được thì không lên bản sau.

### 0.2.0 — một tên, một lệnh (đã phát hành 2026-09-06)

Đổi hết `aisdlc` → `aisef`; bí danh cũ còn chạy có cảnh báo tới 0.3.0; sửa lỗi
31 (hook của bản cài từ wheel trỏ đường dẫn không tồn tại nên guard im lặng
không chạy). **Xong:** suite 1 678 xanh, venv sạch cài → `setup` → `compile` →
guard chặn đúng.

### 0.3.0 — "framework này có đáng tiền không?" (1–2 tuần, ~150 đô la)

| Việc | Xong khi |
|---|---|
| Chạy benchmark 18 task với Claude, 3 lượt mỗi task | có pass@1/pass@3 và độ ổn định ≥ 80 %; số vào `docs/BENCHMARK.md` |
| Nhóm đối chứng: cùng 18 task chạy bằng agent **trần** (không cổng, không guard) | bảng so hai cột: tỉ lệ đạt, chi phí, số lỗi lọt |
| Đo lại vòng cải tiến theo luật mới trên e9 (2 vòng) | Δ ≥ 0 và mọi gap đóng bằng test mới mang mã |
| Hoàn tất hợp quy C11/C12 | bảng 12 phép, cột Claude không ô ✗ |
| Phân tích chi phí: tỉ lệ lượt trượt do kế hoạch vs do code | bảng theo story của e9 + `par` |

Kết quả mong đợi: một trang "framework bắt được gì mà agent trần bỏ lọt, giá
bao nhiêu". Đây là thứ quyết định mọi ưu tiên sau đó.

### 0.4.0 — dùng được ngoài máy của tác giả (2–3 tuần)

| Việc | Xong khi |
|---|---|
| Egress allowlist (V12) | phiên agent chỉ ra được host đã khai; có phép thử chặn thật |
| Khôi phục sau khi máy tắt giữa phiên | giết tiến trình giữa story rồi chạy lại: trạng thái đúng, không mất bằng chứng |
| `aisef init --stack <react|python|go>` | sinh sẵn `tools.test`, `verify.*`, `app.*` đúng cho stack; `doctor` xanh ngay |
| Bảng điều khiển đọc bằng chứng nhiều dự án | một lệnh in chi phí/tuần, hành vi ròng/đô la, gap tồn |
| Hạ số khoá bắt buộc phải khai xuống ≤ 5 | người mới chạy được `plan` mà không mở cấu hình |

### 0.5.0 — nhiều client, nhiều máy (3–4 tuần)

| Việc | Xong khi |
|---|---|
| OpenCode lên hạng nhất | hợp quy 12/12 ba lần liên tiếp; chi phí đọc được từ harness |
| Định tuyến model theo vai (developer/reviewer/designer) có số | A/B trên ≥ 10 story: chất lượng không giảm, chi phí giảm ≥ 20 % |
| Chạy phân tán: hàng đợi story trên nhiều máy | 2 máy chạy 1 epic, bằng chứng gộp đúng, không tranh worktree |
| Cách ly credential trong container (S1) | hợp quy sandbox 6/6, agent trong container không thấy khoá của host |

### 1.0 — cam kết ổn định (khi và chỉ khi)

- Ba dự án thật khác nhau đi hết vòng đời, ít nhất một dự án **không phải của
  tác giả**.
- Benchmark có đường cơ sở và ba lần đo cách nhau ≥ 2 tuần không tụt.
- Hợp đồng cổng và khoá cấu hình đóng băng: đổi là bản chính.
- Tài liệu tiếng Anh song song.

---

## 6. Ba việc nên làm ngay tuần này

1. **Phát hành 0.2.0** để tên gói và tên lệnh khớp nhau ngoài đời, không chỉ
   trong kho.
2. **Chạy benchmark 18 task** — đây là phép đo rẻ nhất còn thiếu, và nó chặn
   mọi tuyên bố năng lực.
3. **Chốt nhóm đối chứng agent trần** cho cùng bộ task; không có nó thì mọi con
   số về sau đều không so được với gì.

---

Tài liệu liên quan: `docs/RELEASE-CHECKLIST-v0.1.0.md` (điều kiện phát hành),
`docs/STATUS-2026-09-05.md` (§2.4 bảng 31 lỗi, §3 vấn đề tồn tại),
`docs/FAILURE-TAXONOMY.md` (11 lớp nguyên nhân), `docs/ADR-004-*`, `docs/ADR-005-*`
(số đo từng yêu cầu), `docs/HUONG-DAN-SU-DUNG.md` (dùng thế nào).
