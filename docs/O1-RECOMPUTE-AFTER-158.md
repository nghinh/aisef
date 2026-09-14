# O1 tính lại sau lỗi 158 — phụ lục có ngày

Tính ngày **2026-09-14**, corpus: todo, todo-cli, todo-e2e, todo-oc.
Sinh lại bằng `python3 validation/recompute_reviewer_qual.py`. Không gọi model.

> **Đây là phụ lục, không phải bản thay thế.** `docs/handoff/o1-reviewer-qualification.md` và mục O1 của ADR-009 giữ nguyên chữ — luật của kho này là bản ghi có ngày thì không sửa lại sau.

## Vì sao phải tính lại

Lỗi 158: `Finding._LINE_RE` chỉ nhận dạng canonical `[high] tệp:dòng thân`, còn prompt dặn người rà soát viết `[block] đường/dẫn:dòng — thân`. Trước khi sửa, **0** dòng chặn đã ghi phân giải được, nên `Finding.id` chưa từng được tính trên đầu ra thật.

Trên corpus này, sau khi sửa: **113 / 174** dòng chặn phân giải được.

## OLD (đã công bố) vs NEW (parser đã sửa)

| số | đã công bố | tính lại | |
|---|---:|---:|---|
| total | 145 | 145 | không đổi |
| undecided | 18 | 18 | không đổi |
| blocks scored | 57 | 57 | không đổi |
| false block | 6 | 6 | không đổi |
| false block rate | 0.105 | 0.1053 | không đổi |
| passes scored | 70 | 70 | không đổi |
| miss | 27 | 27 | không đổi |
| miss rate | 0.386 | 0.3857 | không đổi |
| same-tree consecutive pairs | 20 | 20 | không đổi |
| same-tree verdict reversals | 11 | 11 | không đổi |
| block uncorroborated | 21 | 21 | không đổi |

## Kết luận

**Không số nào đổi.** Phép tính lại tự xác nhận lại các con số đã công bố: lỗi 158 đổi cách `Finding.id` được tính, nhưng các tỉ lệ O1 không đọc qua đường ấy — chúng đọc `note:review:verdict` và bảng cổng. Điều này đáng ghi ra, vì 'không đổi' chỉ có nghĩa khi đã đi đo.

Mỗi con số ở trên tính lại được bất cứ lúc nào; chúng không phụ thuộc một lượt gọi model nào.
