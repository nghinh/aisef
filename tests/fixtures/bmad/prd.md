---
title: Sổ tay ghi chú
status: final
created: 2026-09-04
updated: 2026-09-04
---

# PRD: Sổ tay ghi chú
*Tên tạm — cần xác nhận.*

## 0. Mục đích tài liệu

Tài liệu này dành cho PM, và cho các workflow phía sau (UX, kiến trúc, epic/story) dùng làm nguồn duy nhất về *cái gì* sản phẩm phải làm được. Cấu trúc: thuật ngữ khoá ở §3 và được dùng nguyên văn ở mọi nơi; tính năng nhóm ở §4 với các Yêu cầu chức năng (FR) đánh số toàn cục; giả định gắn thẻ `[ASSUMPTION]` tại chỗ và gom lại ở §12. Tài liệu mô tả **năng lực**, không mô tả cách hiện thực — mọi lựa chọn kỹ thuật (cơ chế lưu trữ, chiến lược đánh chỉ mục, giao thức đồng bộ) nằm ở `addendum.md` cạnh file này. Nguồn đầu vào duy nhất là `docs/requirements.md`; chưa có tài liệu UX hay nghiên cứu người dùng nào tồn tại.

## 1. Tầm nhìn

Sổ tay ghi chú là một ứng dụng web ghi chú cá nhân, tối giản, hoạt động đầy đủ khi không có mạng. Người dùng mở nó ra và viết được ngay — không đăng ký, không onboarding, không chờ tải dữ liệu từ server. Ghi chú nằm trên chính thiết bị của họ.

Giá trị cốt lõi nằm ở hai đầu của một vòng lặp: **ghi nhanh** và **tìm lại được**. Phần lớn ứng dụng ghi chú làm tốt vế đầu rồi để vế sau mục ruỗng — ghi chú tích tụ thành một đống không tra cứu nổi, và người dùng lặng lẽ bỏ dùng. Sản phẩm này coi tốc độ tìm kiếm là một yêu cầu ngang hàng với tốc độ ghi: tìm toàn văn trên 10.000 ghi chú phải trả kết quả nhanh đến mức người dùng gõ tới đâu thấy kết quả tới đó.

Tính tối giản ở đây là một cam kết về phạm vi, không phải một phong cách thị giác: sản phẩm cố tình không trở thành công cụ soạn thảo giàu định dạng, không trở thành hệ thống quản lý tri thức, không trở thành nền tảng cộng tác. Nó là quyển sổ tay — mở ra, viết vào, lật lại tìm được.

## 2. Người dùng mục tiêu

### 2.1 Jobs To Be Done

- **Chức năng:** ghi lại một ý nghĩ trước khi nó bay mất — trong vài giây, ở bất kỳ đâu, kể cả khi không có mạng.
- **Chức năng:** tìm lại một mẩu thông tin đã ghi từ nhiều tháng trước mà chỉ còn nhớ mang máng một hai từ trong đó.
- **Chức năng:** gom các ghi chú rời rạc theo chủ đề hoặc dự án mà không phải dựng cây thư mục.
- **Ngữ cảnh:** dùng chính chiếc điện thoại đang cầm trên tay, trên trình duyệt, không phải cài thêm ứng dụng.
- **Cảm xúc:** yên tâm rằng ghi chú là của mình và nằm ở chỗ mình kiểm soát — không đánh đổi dữ liệu cá nhân lấy một tài khoản.

### 2.2 Không phải người dùng (v1)

- Nhóm làm việc chung cần chia sẻ, bình luận hay phân quyền trên cùng một ghi chú.
- Người dùng cần soạn thảo giàu định dạng (bảng, ảnh nhúng, sơ đồ) hoặc xuất bản nội dung ra ngoài.
- Người dùng doanh nghiệp cần quản trị tập trung, kiểm toán hay chính sách lưu trữ.

### 2.3 Hành trình người dùng chính

*Đánh số UJ-1..UJ-4. Các FR ở §4 tham chiếu ngược lại bằng ID.*

- **UJ-1. Lan ghi lại một ý tưởng trên xe buýt, không có sóng.**
  > Lan, làm nội dung tự do, đang trên xe buýt ở đoạn đường hầm mất sóng. Một ý cho bài viết bật ra trong đầu. Cô mở tab đã ghim sẵn trên trình duyệt điện thoại — ứng dụng hiện ra gần như tức thì và con trỏ đã nằm sẵn trong ô soạn thảo của một ghi chú mới. Cô gõ ba dòng, khoá màn hình, bỏ điện thoại vào túi. Không có nút "Lưu" nào được bấm và cũng không cần: ghi chú đã nằm trong kho cục bộ ngay khi ký tự đầu tiên được gõ. **Trường hợp biên:** nếu trình duyệt bị hệ điều hành thu hồi bộ nhớ giữa chừng, nội dung đã gõ vẫn còn nguyên khi cô mở lại.

- **UJ-2. Lan tìm lại một ghi chú cũ chỉ với hai từ nhớ mang máng.**
  > Ba tháng sau, Lan cần lại địa chỉ một quán cà phê cô từng ghi. Cô không nhớ đã ghi vào đâu, chỉ nhớ có chữ "cà phê" và tên đường. Cô mở ứng dụng, gõ vào ô tìm kiếm — danh sách kết quả thu hẹp dần theo từng ký tự, mỗi kết quả kèm một đoạn trích có từ khoá được tô sáng. Ghi chú cần tìm nằm ở vị trí thứ hai. Cô chạm vào, thấy địa chỉ. **Trường hợp biên:** cô gõ không dấu ("ca phe") vì đang vội — kết quả vẫn ra đúng.

- **UJ-3. Minh gom ghi chú của một dự án bằng thẻ.**
  > Minh, kỹ sư, dùng ứng dụng để ghi lại quyết định kỹ thuật rải rác trong ngày. Cuối tuần anh cần đọc lại toàn bộ những gì liên quan đến một dự án. Anh đã gắn thẻ `dự-án-x` cho từng ghi chú ngay lúc viết, chỉ mất một thao tác mỗi lần. Giờ anh chạm vào thẻ đó và thấy đúng 23 ghi chú đó, theo thứ tự thời gian. Anh thu hẹp thêm bằng cách gõ một từ khoá vào ô tìm kiếm trong khi bộ lọc thẻ vẫn đang bật.

- **UJ-4. Lan viết trên điện thoại, mở laptop và thấy mọi thứ đã ở đó.**
  > Lan đã bật đồng bộ và ghép hai thiết bị của mình. Tối qua cô viết ba ghi chú trên điện thoại khi đang offline. Sáng nay cô mở laptop, ứng dụng hiện chỉ báo "đang đồng bộ" trong chốc lát rồi chuyển sang "đã đồng bộ" — ba ghi chú của tối qua nằm trong danh sách. **Trường hợp biên:** một ghi chú cô đã sửa ở cả hai thiết bị khi cả hai đều offline; hệ thống không tự ý chọn bên nào mà giữ lại cả hai nội dung và đánh dấu để cô tự gộp — không có ký tự nào bị mất.

## 3. Bảng thuật ngữ

*Các workflow phía sau và người đọc phải dùng đúng những thuật ngữ này. FR, UJ và SM dùng nguyên văn; đưa từ đồng nghĩa vào bất kỳ chỗ nào trong PRD là vi phạm kỷ luật tài liệu.*

- **Ghi chú** — Một đơn vị nội dung văn bản do người dùng tạo, có nội dung, thời điểm tạo và thời điểm sửa gần nhất. Một Ghi chú thuộc về một Kho cục bộ và có thể mang 0..n Thẻ.
- **Thẻ** — Một nhãn văn bản ngắn do người dùng đặt, dùng để nhóm Ghi chú. Một Thẻ gắn được với 0..n Ghi chú. Thẻ không có cấp bậc, không lồng nhau.
- **Kho cục bộ** — Toàn bộ Ghi chú và Thẻ được lưu trên chính thiết bị, trong trình duyệt. Là nguồn sự thật khi không có mạng, và là nguồn duy nhất khi Đồng bộ chưa bật.
- **Chỉ mục tìm kiếm** — Cấu trúc dữ liệu cục bộ cho phép Truy vấn trả kết quả trong ngưỡng ở NFR-2. Được cập nhật khi Ghi chú thay đổi.
- **Truy vấn** — Chuỗi ký tự người dùng nhập vào ô tìm kiếm, đối sánh với nội dung Ghi chú.
- **Thùng rác** — Nơi chứa Ghi chú đã xoá trong một khoảng thời gian trước khi bị xoá vĩnh viễn.
- **Đồng bộ** — Việc trao đổi Ghi chú và Thẻ giữa các Thiết bị của cùng một người dùng. Là tính năng người dùng tự bật, mặc định tắt.
- **Thiết bị** — Một cặp (trình duyệt, máy) có Kho cục bộ riêng. Một người dùng có 1..n Thiết bị.
- **Bản xung đột** — Hai phiên bản khác nhau của cùng một Ghi chú được sửa độc lập trên hai Thiết bị, được hệ thống giữ lại cả hai thay vì chọn một.

## 4. Tính năng

### 4.1 Soạn thảo và quản lý ghi chú

**Description:** Vòng lặp cơ bản của sản phẩm. Người dùng mở ứng dụng và có thể bắt đầu gõ ngay — không cần chọn "tạo mới" trước, không cần bấm "lưu" sau. Ghi chú là văn bản thuần; định dạng nhẹ theo cú pháp Markdown được lưu nguyên văn nhưng v1 không cần hiển thị đã dựng hình `[ASSUMPTION: ghi chú là văn bản thuần, không phải trình soạn thảo giàu định dạng — suy ra từ ràng buộc "tối giản"]`. Danh sách ghi chú là màn hình chính, sắp xếp theo thời điểm sửa gần nhất. Hiện thực hoá UJ-1, UJ-3.

**Functional Requirements:**

#### FR-1: Tạo ghi chú

Người dùng có thể tạo một Ghi chú mới từ màn hình chính bằng một thao tác duy nhất, kể cả khi không có mạng. Hiện thực hoá UJ-1.

**Consequences (testable):**
- Từ màn hình chính, số thao tác đến khi con trỏ nằm trong ô soạn thảo trống là 1.
- Ghi chú mới tồn tại trong Kho cục bộ ngay khi ký tự đầu tiên được nhập, không cần thao tác lưu tường minh.
- Tạo Ghi chú thành công khi trình duyệt hoàn toàn không có kết nối mạng.

#### FR-2: Sửa ghi chú với lưu tự động

Người dùng có thể sửa nội dung một Ghi chú và thay đổi được ghi vào Kho cục bộ mà không cần thao tác lưu. Hiện thực hoá UJ-1.

**Consequences (testable):**
- Sau khi ngừng gõ 1 giây, nội dung đã có trong Kho cục bộ.
- Đóng tab hoặc bị hệ điều hành thu hồi tiến trình sau thời điểm đó không làm mất nội dung đã gõ.
- Thời điểm sửa gần nhất của Ghi chú được cập nhật theo mỗi lần ghi.

#### FR-3: Xoá ghi chú qua thùng rác

Người dùng có thể xoá một Ghi chú; Ghi chú chuyển vào Thùng rác và có thể khôi phục trong 30 ngày trước khi bị xoá vĩnh viễn. `[ASSUMPTION: xoá là xoá mềm với thời hạn 30 ngày — brief chỉ nói "xoá"; xoá cứng ngay lập tức trên dữ liệu chỉ có một bản cục bộ là một đường mất dữ liệu]`

**Consequences (testable):**
- Ghi chú đã xoá không xuất hiện trong danh sách chính và không xuất hiện trong kết quả Truy vấn.
- Ghi chú trong Thùng rác khôi phục được về đúng nội dung và Thẻ trước khi xoá.
- Sau 30 ngày kể từ lúc xoá, Ghi chú bị loại khỏi Kho cục bộ và không khôi phục được.

#### FR-4: Duyệt danh sách ghi chú

Người dùng có thể xem danh sách Ghi chú của mình, sắp xếp theo thời điểm sửa gần nhất, và cuộn qua toàn bộ kho mà không bị giật.

**Consequences (testable):**
- Danh sách hiển thị được ở quy mô 10.000 Ghi chú mà vẫn giữ ngưỡng ở NFR-1 và NFR-3.
- Mỗi mục hiển thị đủ để nhận ra Ghi chú: dòng đầu nội dung, thời điểm sửa, các Thẻ đang gắn.

### 4.2 Tìm kiếm toàn văn

**Description:** Nửa còn lại của vòng lặp, và là nơi sản phẩm quyết định thắng thua. Người dùng gõ vào một ô tìm kiếm duy nhất và danh sách thu hẹp theo từng ký tự, đối sánh trên toàn bộ nội dung Ghi chú. Kết quả kèm đoạn trích có tô sáng để nhận ra ngay mà không cần mở từng cái. Tìm kiếm chạy hoàn toàn trên Kho cục bộ, nên hoạt động y hệt khi offline. Hiện thực hoá UJ-2, UJ-3.

**Functional Requirements:**

#### FR-5: Truy vấn toàn văn trên nội dung ghi chú

Người dùng có thể nhập một Truy vấn và nhận về các Ghi chú có nội dung khớp, không cần rời khỏi màn hình danh sách. Hiện thực hoá UJ-2.

**Consequences (testable):**
- Truy vấn đối sánh trên toàn bộ nội dung Ghi chú, không chỉ dòng đầu hay tiêu đề.
- Kết quả cập nhật theo từng ký tự người dùng gõ, trong ngưỡng ở NFR-2.
- Truy vấn nhiều từ trả về Ghi chú chứa tất cả các từ, không phụ thuộc thứ tự `[ASSUMPTION: ngữ nghĩa AND giữa các từ — brief không nêu]`.
- Truy vấn hoạt động đầy đủ khi không có mạng.

#### FR-6: Đối sánh không phân biệt dấu và hoa/thường

Người dùng có thể gõ Truy vấn không dấu hoặc sai hoa/thường và vẫn nhận về các Ghi chú có dấu tương ứng. Hiện thực hoá UJ-2. `[ASSUMPTION: yêu cầu này không có trong brief; với một sản phẩm tiếng Việt, tìm "ca phe" mà không ra "cà phê" là hỏng chính yêu cầu "tìm lại được"]`

**Consequences (testable):**
- Truy vấn `ca phe` trả về Ghi chú chứa `cà phê`.
- Truy vấn `CÀ PHÊ` và `cà phê` trả về cùng tập kết quả.
- Truy vấn có dấu vẫn khớp đúng nội dung có dấu (chuẩn hoá không làm mất khả năng tìm chính xác).

#### FR-7: Trình bày kết quả tìm kiếm

Người dùng có thể nhận ra Ghi chú cần tìm từ chính danh sách kết quả, không phải mở lần lượt từng kết quả. Hiện thực hoá UJ-2.

**Consequences (testable):**
- Mỗi kết quả hiển thị một đoạn trích chứa từ khớp, với phần khớp được tô sáng.
- Khi Truy vấn không khớp Ghi chú nào, hệ thống hiện trạng thái rỗng tường minh, không phải danh sách trắng.
- Thứ tự kết quả xác định và ổn định giữa các lần chạy cùng một Truy vấn trên cùng dữ liệu `[ASSUMPTION: chưa chốt tiêu chí xếp hạng — xem OQ-4]`.

### 4.3 Gắn thẻ

**Description:** Cơ chế nhóm duy nhất của sản phẩm — cố tình phẳng, không có thư mục và không có thẻ lồng nhau. Người dùng gắn Thẻ ngay trong lúc viết, và về sau chạm vào một Thẻ để xem mọi Ghi chú mang Thẻ đó. Bộ lọc Thẻ và ô tìm kiếm hoạt động đồng thời: lọc trước, tìm trong tập đã lọc. Hiện thực hoá UJ-3.

**Functional Requirements:**

#### FR-8: Gắn và gỡ thẻ

Người dùng có thể gắn một hoặc nhiều Thẻ vào một Ghi chú, và gỡ ra, ngay trong màn hình soạn thảo. Hiện thực hoá UJ-3.

**Consequences (testable):**
- Gắn một Thẻ chưa tồn tại sẽ tạo Thẻ đó, không cần bước tạo riêng.
- Khi gõ tên Thẻ, hệ thống gợi ý các Thẻ đã có để tránh tạo trùng do khác biệt gõ phím.
- Thẻ trùng tên không được tạo thành hai Thẻ khác nhau.

#### FR-9: Lọc theo thẻ

Người dùng có thể chọn một Thẻ và xem đúng tập Ghi chú mang Thẻ đó, đồng thời vẫn dùng được Truy vấn trên tập đã lọc. Hiện thực hoá UJ-3.

**Consequences (testable):**
- Bộ lọc Thẻ đang bật và Truy vấn đang có nội dung thì kết quả là giao của hai điều kiện.
- Trạng thái lọc hiện rõ trên giao diện và huỷ được bằng một thao tác.
- Lọc theo Thẻ giữ ngưỡng ở NFR-2 ở quy mô 10.000 Ghi chú.

#### FR-10: Quản lý thẻ

Người dùng có thể đổi tên hoặc xoá một Thẻ, và thay đổi được áp dụng cho mọi Ghi chú đang mang Thẻ đó.

**Consequences (testable):**
- Đổi tên Thẻ cập nhật mọi Ghi chú liên quan trong một thao tác.
- Xoá Thẻ gỡ Thẻ khỏi các Ghi chú nhưng không xoá Ghi chú nào.
- Thẻ không còn Ghi chú nào mang nó không hiện trong danh sách lọc.

### 4.4 Hoạt động offline và đồng bộ

**Description:** Offline là trạng thái mặc định chứ không phải chế độ dự phòng: mọi tính năng ở §4.1–4.3 chạy trên Kho cục bộ và không bao giờ chờ mạng. Đồng bộ là một lớp phủ lên trên, người dùng tự bật, để cùng một kho ghi chú xuất hiện trên nhiều Thiết bị. Nguyên tắc bất di bất dịch: Đồng bộ không bao giờ được phép làm mất chữ người dùng đã gõ — khi hai bên xung đột, hệ thống giữ cả hai và để người dùng quyết định. Hiện thực hoá UJ-1, UJ-4.

`[NOTE FOR PM] Nhóm FR này phụ thuộc vào OQ-1 (cơ chế định danh cho Đồng bộ khi tài khoản không bắt buộc). FR-13..FR-15 không thể đưa vào kiến trúc trước khi OQ-1 được chốt.`

**Functional Requirements:**

#### FR-11: Hoạt động đầy đủ khi không có mạng

Người dùng có thể tạo, sửa, xoá, tìm kiếm và lọc Ghi chú khi thiết bị hoàn toàn không có kết nối, kể cả ở lần mở ứng dụng đầu tiên sau khi đã dùng ít nhất một lần. Hiện thực hoá UJ-1.

**Consequences (testable):**
- Với mạng bị ngắt hoàn toàn, FR-1..FR-10 vẫn đạt toàn bộ điều kiện kiểm thử của chúng.
- Ứng dụng khởi động và hiển thị đầy đủ Ghi chú khi không có mạng, trong ngưỡng ở NFR-1.
- Không thao tác nào của người dùng bị chặn, bị làm chậm, hay hiện lỗi vì lý do mất mạng.

#### FR-12: Chỉ báo trạng thái mạng và đồng bộ

Người dùng có thể biết dữ liệu của mình đang ở trạng thái nào — chỉ nằm cục bộ, đang đồng bộ, đã đồng bộ, hay có Bản xung đột chờ xử lý. Hiện thực hoá UJ-4.

**Consequences (testable):**
- Trạng thái hiển thị được ở màn hình chính mà không cần mở menu.
- Khi Đồng bộ chưa bật, chỉ báo nói rõ dữ liệu chỉ nằm trên Thiết bị này.
- Chỉ báo chuyển sang trạng thái lỗi khi Đồng bộ thất bại, kèm thao tác thử lại.

#### FR-13: Bật đồng bộ và ghép thiết bị

Người dùng có thể bật Đồng bộ và ghép thêm Thiết bị vào cùng một kho ghi chú. Đồng bộ mặc định tắt và không bắt buộc để dùng sản phẩm. Hiện thực hoá UJ-4. `[ASSUMPTION: đồng bộ là opt-in, mặc định tắt — suy ra từ ràng buộc "không bắt buộc tài khoản"]`

**Consequences (testable):**
- Toàn bộ FR-1..FR-11 dùng được mà không bao giờ bật Đồng bộ.
- Bật Đồng bộ không xoá hay thay thế Ghi chú đang có trên Thiết bị.
- Người dùng tắt được Đồng bộ, và sau khi tắt, Kho cục bộ vẫn còn nguyên Ghi chú.

**Out of Scope:**
- Cơ chế định danh cụ thể (tài khoản, mã ghép thiết bị, khoá do người dùng giữ) — chưa chốt, xem OQ-1.

#### FR-14: Đồng bộ tự động khi có mạng

Khi Đồng bộ đã bật và thiết bị có mạng trở lại, các thay đổi cục bộ được gửi đi và thay đổi từ Thiết bị khác được nhận về, không cần người dùng thao tác. Hiện thực hoá UJ-4.

**Consequences (testable):**
- Thay đổi tạo ra khi offline được đồng bộ sau khi có mạng trở lại mà người dùng không bấm nút nào.
- Đồng bộ chạy nền, không chặn thao tác soạn thảo hay tìm kiếm đang diễn ra.
- Đồng bộ thất bại giữa chừng không để lại Ghi chú ở trạng thái nội dung dở dang.

#### FR-15: Giữ lại bản xung đột thay vì ghi đè

Khi cùng một Ghi chú bị sửa độc lập trên hai Thiết bị, hệ thống giữ lại cả hai phiên bản dưới dạng Bản xung đột và để người dùng quyết định, thay vì tự chọn một bên. Hiện thực hoá UJ-4.

**Consequences (testable):**
- Không có kịch bản xung đột nào khiến nội dung người dùng đã gõ biến mất khỏi Kho cục bộ.
- Bản xung đột hiện rõ trong danh sách và mở ra xem được cả hai phiên bản.
- Người dùng chọn giữ một bên hoặc gộp thủ công, và sau khi giải quyết thì Bản xung đột không còn.

### 4.5 Quyền sở hữu và an toàn dữ liệu

**Description:** Hệ quả trực tiếp của việc dữ liệu nằm cục bộ và không có tài khoản: nếu trình duyệt dọn dẹp dung lượng, ghi chú biến mất và không có server nào để khôi phục. Nhóm FR này là biện pháp phòng mất dữ liệu tối thiểu — không phải tính năng "cho oai". `[ASSUMPTION: cả nhóm 4.5 không có trong brief; được thêm vì mô hình chỉ-lưu-cục-bộ tạo ra một đường mất dữ liệu có thật]`

**Functional Requirements:**

#### FR-16: Xuất toàn bộ dữ liệu

Người dùng có thể xuất toàn bộ Ghi chú và Thẻ ra một tệp trên thiết bị, ở định dạng đọc được bằng công cụ khác.

**Consequences (testable):**
- Bản xuất chứa đầy đủ nội dung Ghi chú, Thẻ, thời điểm tạo và thời điểm sửa.
- Xuất dữ liệu chạy được khi không có mạng.
- Bản xuất đọc được mà không cần chính ứng dụng này.

#### FR-17: Cảnh báo rủi ro lưu trữ cục bộ

Người dùng được cảnh báo khi dung lượng lưu trữ của trình duyệt sắp cạn hoặc khi dữ liệu có nguy cơ bị trình duyệt thu hồi, kèm hướng xử lý.

**Consequences (testable):**
- Cảnh báo xuất hiện trước khi thao tác ghi bị thất bại vì hết dung lượng, không phải sau.
- Cảnh báo dẫn thẳng tới thao tác xuất dữ liệu ở FR-16.
- Khi thao tác ghi thất bại, hệ thống báo lỗi rõ ràng thay vì im lặng mất nội dung.

## 5. Yêu cầu phi chức năng xuyên suốt

- **NFR-1 — Thời gian mở ứng dụng.** Từ lúc chạm biểu tượng/tab đến lúc giao diện tương tác được: dưới 1 giây `[ASSUMPTION: đo ở lần mở lại (đã có cache), trên thiết bị Android tầm trung, phân vị 95 — brief chỉ nêu con số, không nêu điều kiện đo; xem OQ-6]`.
- **NFR-2 — Độ trễ tìm kiếm.** Truy vấn trả kết quả dưới 200ms với kho 10.000 Ghi chú, đo trên cùng điều kiện thiết bị như NFR-1, phân vị 95. Áp dụng cho cả FR-5, FR-6 và FR-9.
- **NFR-3 — Độ mượt tương tác.** Cuộn danh sách và gõ trong ô soạn thảo không rớt khung hình ở quy mô 10.000 Ghi chú.
- **NFR-4 — Không mất dữ liệu.** Không có kịch bản nào — đóng tab đột ngột, hết pin, mất mạng giữa lúc đồng bộ, xung đột hai thiết bị — làm mất nội dung người dùng đã gõ và đã qua ngưỡng ghi ở FR-2.
- **NFR-5 — Hoạt động offline.** Mọi năng lực ở §4.1–4.3 không phụ thuộc mạng, kể cả ở lần tải lại đầu tiên sau khi mất mạng.
- **NFR-6 — Trình duyệt hỗ trợ.** Chạy trên các trình duyệt hiện hành trên di động và desktop `[ASSUMPTION: phạm vi phiên bản cụ thể chưa chốt; xem OQ-7]`.
- **NFR-7 — Khả năng tiếp cận.** Thao tác được đầy đủ bằng bàn phím; ô soạn thảo và ô tìm kiếm có nhãn cho trình đọc màn hình; độ tương phản văn bản đạt WCAG 2.1 AA.

## 6. Ràng buộc và rào chắn

**Quyền riêng tư**
- Khi Đồng bộ chưa bật, không có nội dung Ghi chú nào rời khỏi Thiết bị. Đây là ràng buộc, không phải mặc định có thể đổi.
- Không có tài khoản bắt buộc, không thu thập dữ liệu cá nhân để dùng sản phẩm.
- Không đo đạc hành vi có gắn nội dung Ghi chú. Nếu có đo lường cho §7, chỉ đo ở mức số liệu tổng hợp, không kèm nội dung `[ASSUMPTION: chưa chốt có thu thập số liệu hay không; xem OQ-8]`.

**Dữ liệu**
- Kho cục bộ là nguồn sự thật. Đồng bộ là bản sao, không phải bản gốc.
- Xoá ở FR-3 là xoá mềm có thời hạn; hết thời hạn là xoá thật, không giữ bản ngầm ở đâu khác.

**Chi phí**
- Khi Đồng bộ chưa bật, sản phẩm không phát sinh chi phí hạ tầng cho mỗi người dùng.
- Đồng bộ là phần duy nhất cần hạ tầng phía server, và ràng buộc chi phí của nó gắn với quyết định ở OQ-1.

## 7. Nền tảng

- Ứng dụng web, chạy trong trình duyệt. Không phát hành ứng dụng cài đặt gốc cho v1.
- Ưu tiên thiết kế cho trình duyệt di động; desktop dùng chung một giao diện đáp ứng, không phải một bản riêng.
- Cài lên màn hình chính và chạy như ứng dụng độc lập là mong muốn ngầm của yêu cầu offline `[ASSUMPTION: cơ chế cụ thể thuộc về kiến trúc — xem addendum.md]`.

## 8. Ngoài phạm vi (tường minh)

- **Không** trở thành trình soạn thảo giàu định dạng: không bảng, không ảnh nhúng, không vẽ, không đính kèm tệp.
- **Không** trở thành công cụ cộng tác: không chia sẻ, không bình luận, không phân quyền, không chỉnh sửa nhiều người cùng lúc.
- **Không** trở thành hệ thống quản lý tri thức: không liên kết hai chiều, không đồ thị ghi chú, không thư mục lồng nhau, không truy vấn nâng cao.
- **Không** trở thành ứng dụng công việc: không nhắc nhở, không lịch, không danh sách việc cần làm có trạng thái.
- **Không** có quản trị tập trung, kiểm toán, hay chính sách lưu trữ cấp tổ chức.

## 9. Phạm vi MVP

### 9.1 Trong phạm vi

- Tạo, sửa (lưu tự động), xoá qua Thùng rác, duyệt danh sách Ghi chú (FR-1..FR-4).
- Tìm kiếm toàn văn có chuẩn hoá dấu tiếng Việt, kèm đoạn trích tô sáng (FR-5..FR-7).
- Gắn thẻ phẳng, lọc theo Thẻ kết hợp với Truy vấn, quản lý Thẻ (FR-8..FR-10).
- Hoạt động đầy đủ offline và chỉ báo trạng thái (FR-11, FR-12).
- Xuất dữ liệu và cảnh báo rủi ro lưu trữ (FR-16, FR-17).
- Đạt NFR-1..NFR-7.

### 9.2 Ngoài phạm vi MVP

- **Đồng bộ nhiều thiết bị (FR-13..FR-15)** — nằm trong yêu cầu gốc nhưng chặn bởi OQ-1: đồng bộ giữa các thiết bị cần một dạng định danh, trong khi ràng buộc là "không bắt buộc tài khoản". `[NOTE FOR PM] Đây là mục quan trọng nhất bị đẩy ra khỏi MVP. Nếu OQ-1 được chốt sớm, nên kéo lại vào MVP — sản phẩm không có đồng bộ vẫn dùng được, nhưng UJ-4 sẽ không tồn tại.`
- **Nhập dữ liệu từ tệp** — cặp đôi của FR-16, hoãn sang v2; không cần thiết để chống mất dữ liệu.
- **Hiển thị Markdown đã dựng hình** — nội dung vẫn lưu nguyên văn nên không mất gì khi thêm sau.
- **Mã hoá dữ liệu cục bộ** — phụ thuộc OQ-2; chỉ có ý nghĩa thật khi Đồng bộ tồn tại.
- **Ghim ghi chú, sắp xếp thủ công, chủ đề sáng/tối tuỳ chọn** — thuộc nhóm tinh chỉnh, không thuộc vòng lặp ghi–tìm.

## 10. Chỉ số thành công

*Mỗi SM tham chiếu FR hoặc NFR mà nó kiểm chứng.*

**Chính**
- **SM-1** — Thời gian mở ứng dụng: phân vị 95 dưới 1 giây trên thiết bị tham chiếu. Kiểm chứng NFR-1, FR-11.
- **SM-2** — Độ trễ tìm kiếm: phân vị 95 dưới 200ms với kho 10.000 Ghi chú. Kiểm chứng NFR-2, FR-5, FR-6, FR-9.
- **SM-3** — Thời gian đến ký tự đầu tiên: từ lúc mở ứng dụng đến lúc gõ được ký tự đầu vào Ghi chú mới, dưới 2 giây. Kiểm chứng FR-1, UJ-1.
- **SM-4** — Không mất dữ liệu: 0 sự cố mất nội dung đã ghi trong toàn bộ kiểm thử kịch bản đóng đột ngột, mất mạng và xung đột. Kiểm chứng NFR-4, FR-2, FR-15.

**Phụ**
- **SM-5** — Tỉ lệ tìm kiếm thành công: tỉ lệ phiên tìm kiếm kết thúc bằng việc mở một Ghi chú trong kết quả, thay vì bỏ dở hoặc sửa Truy vấn nhiều lần. Kiểm chứng FR-5, FR-6, FR-7 `[ASSUMPTION: chưa có ngưỡng mục tiêu; cần một đường cơ sở trước — xem OQ-5]`.
- **SM-6** — Duy trì sử dụng: người dùng còn tạo Ghi chú sau 4 tuần kể từ lần dùng đầu. Kiểm chứng giả thiết ở §1 rằng vòng lặp ghi–tìm giữ chân được người dùng.

**Đối trọng (không tối ưu)**
- **SM-C1** — Độ đầy đủ kết quả tìm kiếm. Không được đánh đổi để đạt SM-2: cắt bớt phạm vi đối sánh (chỉ tìm dòng đầu, chỉ tìm N ghi chú gần nhất) sẽ làm số liệu SM-2 đẹp lên trong khi phá đúng cái công việc ở §2.1. Đối trọng với SM-2.
- **SM-C2** — Độ trễ tương tác đầu tiên. Không được đánh đổi để đạt SM-1: hoãn tải quá nhiều thứ khiến màn hình hiện ra sớm nhưng thao tác đầu tiên bị đơ sẽ làm SM-1 đẹp lên mà trải nghiệm xấu đi. Đối trọng với SM-1.
- **SM-C3** — Số lượng tính năng. Tăng trưởng tính năng không phải chỉ số thành công. Mọi bổ sung phải vượt qua §8 trước. Đối trọng với SM-6.

## 11. Câu hỏi mở

1. **OQ-1 (chặn FR-13..FR-15)** — Đồng bộ nhiều thiết bị định danh người dùng bằng cách nào khi tài khoản không bắt buộc? Ba hướng thường gặp: tài khoản tuỳ chọn chỉ dành cho người bật đồng bộ; mã ghép thiết bị kèm khoá do người dùng tự giữ; hoặc đẩy sang kho lưu trữ của chính người dùng. Mỗi hướng kéo theo mô hình chi phí và mô hình khôi phục khác nhau. Chủ: PM. Cần chốt trước khi bước sang kiến trúc.
2. **OQ-2** — Dữ liệu trong Kho cục bộ có cần mã hoá không? Thiết bị dùng chung là kịch bản có thật; nhưng mã hoá kéo theo câu hỏi ai giữ khoá, và mất khoá là mất ghi chú. Chủ: PM.
3. **OQ-3** — Một Ghi chú có tiêu đề riêng, hay dòng đầu nội dung đóng vai tiêu đề? Ảnh hưởng đến FR-4, FR-7 và toàn bộ thiết kế danh sách. Chủ: PM/UX.
4. **OQ-4** — Kết quả tìm kiếm xếp hạng theo tiêu chí gì: thời điểm sửa gần nhất, độ liên quan, hay kết hợp? Ảnh hưởng FR-7. Chủ: PM.
5. **OQ-5** — Đường cơ sở và ngưỡng mục tiêu cho SM-5 và SM-6 là bao nhiêu? Hiện chưa có dữ liệu để đặt số. Chủ: PM.
6. **OQ-6** — Thiết bị tham chiếu và điều kiện đo cho NFR-1, NFR-2: mở lần đầu hay mở lại, thiết bị nào, mạng nào? Con số 1 giây và 200ms vô nghĩa nếu không cố định điều kiện đo. Chủ: PM/kiến trúc.
7. **OQ-7** — Danh sách trình duyệt và phiên bản tối thiểu phải hỗ trợ (NFR-6). Chủ: PM.
8. **OQ-8** — Có thu thập số liệu sử dụng để đo SM-5, SM-6 không, và nếu có thì theo cách nào để không mâu thuẫn với cam kết quyền riêng tư ở §6? Chủ: PM.

## 12. Chỉ mục giả định

Mọi `[ASSUMPTION]` trong tài liệu, gom lại để xác nhận tường minh:

- **§4.1** — Ghi chú là văn bản thuần (Markdown lưu nguyên văn, không dựng hình ở v1), không phải trình soạn thảo giàu định dạng.
- **§4.1 / FR-3** — Xoá là xoá mềm qua Thùng rác với thời hạn 30 ngày; brief chỉ nói "xoá".
- **§4.2 / FR-5** — Truy vấn nhiều từ dùng ngữ nghĩa AND.
- **§4.2 / FR-6** — Đối sánh không phân biệt dấu tiếng Việt là bắt buộc; yêu cầu này được thêm vào, không có trong brief.
- **§4.2 / FR-7** — Tiêu chí xếp hạng kết quả chưa chốt (OQ-4).
- **§4.4 / FR-13** — Đồng bộ là tính năng opt-in, mặc định tắt.
- **§4.5** — Toàn bộ nhóm quyền sở hữu và an toàn dữ liệu (FR-16, FR-17) được thêm vào, không có trong brief.
- **§5 / NFR-1, NFR-2** — Điều kiện đo (mở lại đã có cache, Android tầm trung, phân vị 95) là suy diễn (OQ-6).
- **§5 / NFR-6** — Phạm vi trình duyệt và phiên bản chưa chốt (OQ-7).
- **§6** — Chưa chốt việc có thu thập số liệu sử dụng hay không (OQ-8).
- **§7** — Cài lên màn hình chính là mong muốn ngầm suy ra từ yêu cầu offline.
- **Toàn tài liệu** — Ngôn ngữ tài liệu là tiếng Việt, chọn theo ngôn ngữ của brief; `document_output_language` không được cấu hình trong dự án này.
