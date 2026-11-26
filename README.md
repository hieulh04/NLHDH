# Mô phỏng các phương pháp kiểm tra xác định bế tắc – Nhóm 18 (bản Python)

Web Flask mô phỏng theo Giáo trình NLHĐH, Chương 4:

- Thuật toán kiểm tra tính an toàn (mục 4.2.2c), chạy từng bước Next / Back / Reset.
- Thuật toán chuyển hệ sang trạng thái an toàn – Banker (mục 4.2.2b).
- Thuật toán phát hiện bế tắc (mục 4.2.3) và gợi ý xử lý (mục 4.2.4).
- Phát hiện bế tắc qua đồ thị RAG / đồ thị chờ cho tài nguyên đơn thể (mục 1.3.1).

## Cài đặt và chạy

Cần Python 3.10 trở lên.

```
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py                      # mở http://localhost:5000
python tests/test_all.py           # kiểm thử module lõi
```

Ứng dụng dành cho một người dùng trên máy cá nhân: mọi tab trình duyệt dùng chung một trạng thái.

## Cấu trúc (đối chiếu với bản C++)

| Bản Python | Bản C++ |
|---|---|
| `app.py` | `gui/main_window.*`, phần xử lý của các panel |
| `utility.py` | `core/types`, `system_state`, `validator`, `file_io`, `logger`, `sample_data` |
| `report.py` | `core/report` |
| `models/safety.py` | `core/safety` (gồm `Stepper`) |
| `models/banker.py` | `core/banker` |
| `models/detection.py` | `core/detection` |
| `models/rag.py` | `core/rag` |
| `models/recovery.py` | `core/recovery` |
| `templates/`, `static/` | phần vẽ giao diện trong `gui/` |
| `tests/test_all.py` | `tests/test_all.cpp` |

## Dữ liệu mẫu (thư mục `data/`, hoặc chọn trên thanh công cụ)

| File | Nội dung | Kết quả mong đợi |
|---|---|---|
| `vidu_trang52.txt` | Ví dụ trang 52–54 | An toàn, dãy P4, P0, P1, P2, P3; P4 yêu cầu (1, 2, 2) được cấp |
| `cau5_trang57.txt` | Câu 5 trang 57 | An toàn, dãy P0, P2, P1, P3, P4; P1 yêu cầu (0, 4, 2, 0) được cấp |
| `cau6_trang57.txt` | Câu 6 trang 57 (có Request) | Không bế tắc; các yêu cầu đều cấp được |
| `be_tac_da_the.txt` | Bế tắc tài nguyên đa thể | Bế tắc P0, P1, P2; gợi ý đình chỉ P0 |
| `rag_don_the.txt` | Tài nguyên đơn thể (mục 1.3.1) | Chu trình P0 -> P1 -> P2 -> P0; P3 bị kéo theo |
| `khong_an_toan.txt` | Trạng thái không an toàn | Không có dãy an toàn |

Định dạng file: dòng `n m`, 1 dòng Available, n dòng Allocation, n dòng Max, n dòng Request (có thể bỏ).
Phần sau dấu `#` là chú thích.

Lưu ý: ví dụ trang 54, Work cuối cùng đúng là (10, 5, 7); giáo trình in nhầm (12, 5, 5).
