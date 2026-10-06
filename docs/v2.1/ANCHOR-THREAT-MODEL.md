# Evidence anchor — mô hình đe doạ (AISEF 2.1, nhánh chưa phát hành)

`EVIDENCE.json` băm record (JSON chuẩn hoá), `RUN.started.json`, journal, mọi luồng phiên và tệp preflight; **anchor** là
sha256 của manifest đó (ADR-3). `aisef run --verify --expect-anchor A` bác bỏ mọi thư mục mà manifest dựng lại không ra `A`.

## Anchor bảo vệ được gì

| Kẻ sửa | Ghi được thư mục run | Ghi được nơi giữ anchor | `--verify --expect-anchor` |
|---|---|---|---|
| ai đó sửa thư mục run sau khi lượt chạy xong (đồng nghiệp, script, đồng bộ hỏng) | có | **không** | REFUTED — đã đo (`AnchorThreatModel.test_an_attacker_who_cannot_write_the_store_is_refuted`) |
| bất kỳ ai có **cùng quyền** với nơi giữ anchor | có | **có** | VERIFIED — **không phát hiện được**; đã đo (`test_the_limit_an_attacker_who_can_write_the_store_too_is_not_detected`) |
| không có anchor | có | — | chỉ chứng minh *nhất quán*, không chứng minh *xác thực* |

"Ngoài thư mục run" **không** đồng nghĩa "ngoài quyền kiểm soát của developer". Không có cách ly (mặc định, và luôn luôn trên
macOS), developer agent và mã test chạy dưới chính user của người vận hành: chúng ghi được mọi thứ người vận hành ghi
được, kể cả một tệp anchor trong HOME. Khi đó anchor chỉ chống được việc sửa *sau* lượt chạy bởi người không có quyền ghi
nơi giữ nó.

## Nơi giữ anchor đúng

- `aisef run ... --anchor-out FILE` ghi anchor vào một tệp **mới** (tạo độc quyền, không bao giờ ghi đè).
- Tệp đó phải nằm nơi tiến trình của developer **không** ghi được: một máy khác, một kho chỉ-thêm, một commit đã ký, một
  hệ thống ghi nhận ngoài; hoặc — khi chạy có cách ly (ADR cách ly, chỉ Linux) — một đường dẫn không được gắn vào sandbox.
- Ngay khi lượt chạy in anchor, chép nó ra nơi đó; đừng giữ nó cạnh thư mục run.

## Không tuyên bố

- Không có chữ ký số: AISEF không giữ khoá nào mà developer chắc chắn không đọc được khi chạy cùng user.
- Anchor không chứng minh lượt chạy diễn ra như journal kể — chỉ chứng minh tệp hôm nay là tệp lúc anchor được ghi.
