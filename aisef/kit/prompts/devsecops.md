---
name: devsecops
version: 1
role: designer
---
# Bộ khung vận hành cho {{ project_name }}

Stack: {{ stack }}

Viết những thứ mà **mỗi dự án một khác**, nên không sinh sẵn được. Quy
trình CI đã do framework sinh ở `{{ ci_path }}` — đừng viết lại.

## Phải tạo

1. **`Dockerfile`** — nhiều tầng, chạy bằng người dùng không phải root,
   ghim phiên bản ảnh nền theo digest. Không cài công cụ dev vào ảnh chạy.

2. **`docker-compose.yml`** — dựng đủ phụ thuộc để chạy kiểm thử tích hợp
   trên máy (cơ sở dữ liệu, hàng đợi, dịch vụ giả). Không dùng cho môi
   trường thật.

3. **`deploy/`** — manifest triển khai đúng thứ dự án dùng (k8s, Compose,
   hay dịch vụ nền tảng). Khai giới hạn tài nguyên, thăm dò sẵn sàng
   (readiness) và thăm dò sống (liveness). Bí mật đọc từ nguồn bí mật,
   **không** nằm trong manifest.

4. **Quan sát** — log có cấu trúc (JSON, có mã tương quan), số đo cho
   những thứ NFR đặt ngưỡng, và luật cảnh báo gắn với **triệu chứng người
   dùng thấy** chứ không gắn với tài nguyên máy. "CPU 90%" không phải sự
   cố; "một phần mười yêu cầu lưu ghi chú thất bại" mới là.

5. **`{{ runbook_path }}`** — mỗi sự cố có thể xảy ra một mục, đủ bốn phần:
   {{ runbook_sections }}. Viết cho người trực lúc 3 giờ sáng chưa từng
   đọc hệ này: mỗi bước là một lệnh chạy được, không phải một lời khuyên.
   Thiếu phần leo thang thì runbook chỉ hữu ích với người đã biết phải gọi
   ai — tức là người không cần runbook.

## Không làm

* Không đặt bí mật, khoá, chuỗi kết nối vào bất kỳ file nào.
* Không `latest` cho ảnh nền — không lặp lại được thì không gỡ lỗi được.
* Không chạy bằng root, không `privileged`, không `--cap-add` nếu không
  giải thích được vì sao cần.
* Không viết runbook chung chung kiểu "kiểm tra log": nói rõ log nào, lọc
  gì, và thấy gì thì kết luận gì.

## Xong khi

`docker build` chạy được · manifest hợp lệ · runbook đủ bốn mục cho mọi
sự cố đã lường · không có bí mật nào trong kho.
