# B-10 — Tài liệu công khai: đã chuẩn bị, chờ chọn nơi đăng

**Trạng thái: CHUẨN BỊ XONG Ở LOCAL; nơi đăng là quyết định của chủ dự án** (repo đang private theo lựa chọn của chủ dự
án). Việc chọn nơi đăng không chặn gì ở local.

## Vấn đề (đo)

`README.md` là README của gói trên PyPI (`pyproject.toml: readme = "README.md"`). Nó có 27 link, **23 là link tương đối**
(`docs/v2/USAGE.md`, `CHANGELOG.md`, `closure-evidence/...`). Trên PyPI, link tương đối trỏ vào pypi.org ⇒ 404; và repo
private nên link tuyệt đối vào GitHub cũng không mở được với người đọc ngoài.

## Đã chuẩn bị

`validation/v21/public_readme.py` (test: `tests/test_v21_public_readme.py`):

- **Tự chứa** (không cần nơi đăng): `python3 validation/v21/public_readme.py --out PYPI-README.md` — mọi link vào repo trở
  thành tên đường dẫn dạng chữ; không còn link tương đối nào; link tuyệt đối giữ nguyên.
- **Có nơi đăng**: `--base https://<nơi-đăng>/aisef` — mọi link vào repo trỏ tới `BASE/<đường dẫn>`.
- Link tới một đường dẫn không có trong cây ⇒ từ chối (không đăng link hỏng). Không bao giờ ghi đè tệp có sẵn.

## Phương án nơi đăng

| | Nội dung | Ưu | Nhược |
|---|---|---|---|
| **A. README tự chứa cho PyPI** (khuyến nghị, làm được ngay) | lúc phát hành, `readme` trỏ tới tệp sinh ra ở chế độ tự chứa | không cần public gì; không link 404 | người đọc không mở được tài liệu chi tiết |
| B. Repo tài liệu công khai riêng (GitHub Pages) | xuất `docs/` đã chọn lọc (không có `closure-evidence/` nội bộ) sang repo public; `--base` trỏ tới đó | tài liệu đầy đủ | phải chọn lọc nội dung; duy trì hai nơi |
| C. Read the Docs / host khác | như B | tìm kiếm tốt | thêm một dịch vụ, thêm cấu hình |
| D. Public lại repo chính | link GitHub tuyệt đối | đơn giản nhất | ngược lại lựa chọn private hiện tại |

**Khuyến nghị: A cho 2.0.1/2.1** (không phụ thuộc quyết định nào khác), B khi chủ dự án muốn tài liệu đầy đủ công khai.

## Cần chủ dự án

Chọn A/B/C/D. Với A: không cần gì thêm ngoài việc dùng tệp sinh ra khi phát hành. Với B/C: chọn URL, chọn tập tài liệu
được công khai.
