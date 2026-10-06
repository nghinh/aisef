# Evidence anchor — mô hình đe doạ (AISEF 2.1, nhánh chưa phát hành)

`EVIDENCE.json` băm record (JSON chuẩn hoá), `RUN.started.json`, journal, mọi luồng phiên và tệp preflight; **anchor** là
sha256 của manifest đó (ADR-3). `aisef run --verify --expect-anchor A` bác bỏ mọi thư mục mà manifest dựng lại không ra
`A`.

**Anchor kiểm tra toàn vẹn so với một giá trị neo đáng tin. Nó không chứng minh lịch sử thực thi là thật**: một thư mục
được dựng giả hoàn toàn từ đầu, rồi anchor của nó được lưu như thật, vẫn khớp. Anchor chỉ nói: "các tệp hôm nay là các tệp
lúc giá trị này được lấy".

## Ba nơi, ba câu hỏi khác nhau

| Nơi | Ai | Câu hỏi | Trong AISEF |
|---|---|---|---|
| **tạo** anchor | tiến trình `aisef run`, cuối lượt chạy | giá trị có đúng là của các tệp lúc đó không? | tính từ manifest vừa ghi; in ra; `--anchor-out FILE` ghi vào một tệp **mới** |
| **giữ bản tin cậy** | người vận hành, ngoài tầm developer | ai ghi được nơi đó? | **ngoài AISEF**: AISEF không giữ, không bảo vệ nơi này |
| **lấy expected anchor** khi verify | người/hệ thống chạy `--verify` | giá trị đưa vào lấy từ đâu, đọc qua kênh nào? | `--expect-anchor` nhận **giá trị**, không nhận đường dẫn: AISEF không đọc expected anchor từ một tệp mà kẻ tấn công có thể thay rồi tuyên bố "đã xác thực" |

Kết quả `VERIFIED` với `--expect-anchor` chỉ có nghĩa xác thực khi **nguồn** của giá trị đó đáng tin. AISEF không kiểm được
điều đó; người chạy verify phải biết mình lấy giá trị từ đâu.

## Ai bị phát hiện

| Kẻ sửa | Ghi được thư mục run | Ghi được nơi giữ anchor | `--verify --expect-anchor` |
|---|---|---|---|
| sửa thư mục run sau lượt chạy (đồng nghiệp, script, đồng bộ hỏng) | có | **không** | REFUTED — đo: `AnchorThreatModel.test_an_attacker_who_cannot_write_the_store_is_refuted` |
| cùng quyền với nơi giữ anchor (sửa cả hai) | có | **có** | VERIFIED — **không phát hiện được**; đo: `test_the_limit_an_attacker_who_can_write_the_store_too_is_not_detected` |
| không có anchor | có | — | chỉ chứng minh *nhất quán*, không chứng minh *xác thực* |

"Ngoài thư mục run" **không** đồng nghĩa "ngoài quyền kiểm soát của developer". Khi không có cách ly, developer agent và mã
test chạy dưới chính user của người vận hành và ghi được mọi thứ user đó ghi được, kể cả một tệp anchor trong HOME. Cách ly
Linux (ADR cách ly) không gắn nơi giữ anchor vào sandbox — điều đó bảo vệ nơi giữ **trong lúc chạy**, không bảo vệ nó khỏi
chính user của người vận hành sau lượt chạy.

## Các nơi giữ thường được đề xuất — và điều kiện để chúng có nghĩa

- **Commit đã ký.** Chỉ có ý nghĩa khi verifier *tin* signer (khoá công khai được phân phối qua kênh tin cậy) và *xác minh*
  chữ ký trước khi dùng giá trị. Chữ ký không ngăn developer sửa tệp hay tạo commit mới; nếu khoá ký nằm trong tầm
  developer (cùng user, agent ký được), chữ ký không chứng minh gì hơn tệp thường.
- **Kho chỉ-thêm.** Ngăn sửa mục cũ, không ngăn thêm mục mới: developer có quyền thêm vẫn thêm được "anchor mới" cho cùng
  run. Verifier phải chọn mục theo danh tính run và từ chối khi một run có hơn một mục.
- **Máy khác / hệ thống ghi nhận ngoài.** Chỉ có ý nghĩa khi developer không có credential tới đó (không qua biến môi
  trường, tệp cấu hình hay socket mà sandbox để lọt) và khi giá trị được gửi đi ngay lúc tạo, trước khi developer có cơ
  hội sửa thư mục run.

## Tệp anchor (`--anchor-out`)

- Tạo **độc quyền** (`O_CREAT|O_EXCL`), **không theo symlink** (`O_NOFOLLOW`; một symlink — kể cả trỏ vào chỗ không tồn
  tại — bị từ chối), quyền `0444`, `fsync` trước khi đóng.
- Nội dung đúng một dòng: 64 ký tự hex và một ký tự xuống dòng. `lineage.read_anchor` từ chối mọi thứ khác — tệp ngắn
  (ghi bị gián đoạn), dài hơn, không phải hex — nên một tệp chưa ghi xong không bao giờ được đọc như một anchor hợp lệ.
- CLI từ chối trước khi chạy: đường dẫn đã tồn tại (`lexists`, gồm cả symlink treo), `--anchor-out` cho `--verify`/`--check`,
  `--expect-anchor` không phải 64 hex. Ghi thất bại sau lượt chạy (thư mục không ghi được…) ⇒ thông báo trên stderr, mã
  thoát 2; bằng chứng của lượt chạy không bị ảnh hưởng, anchor in ra vẫn dùng được.
- Đã đo: `AnchorThreatModel.test_the_anchor_file_is_new_exact_and_never_through_a_link`,
  `test_the_cli_refuses_anchor_paths_it_would_not_write_and_a_malformed_expected_anchor`.

## Không tuyên bố

- Không có chữ ký số trong AISEF: không có khoá nào mà developer chắc chắn không đọc được khi chạy cùng user.
- Anchor không chứng minh lượt chạy diễn ra như journal kể.
