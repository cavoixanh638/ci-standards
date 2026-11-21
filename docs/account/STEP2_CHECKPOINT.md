# Checkpoint Bước 2 — 2026-11-21

## Phạm vi
- Khởi tạo `cavoixanh638/ci-standards` Public theo yêu cầu chủ tài khoản.
- `main`: chỉ README nền tảng (không có workflow Actions).
- Nhánh review: `feat/account-wide-qa-bootstrap-20261121`.
- Cây mã nguồn: `config/`, `tools/`, `tests/`, `examples/`, `templates/`, `docs/`.
- Không đẩy dữ liệu kiểm kê Private hoặc tệp billing lên kho Public.

## Kiểm thử
- Chạy `python -m unittest discover -s tests -v` với gói bootstrap chuẩn bị: **51/51 PASS**.
- Kiểm tra JSON, Python compile và quét một số định dạng bí mật: PASS/không phát hiện mẫu đã kiểm.
- So khớp từng tệp được push với gói chuẩn bị và trạng thái PR: cần xác minh sau commit.
- GitHub Actions/end-to-end: **NOT_RUN**, cố ý không kích hoạt.
- Billing/required checks/triển khai GitHub App: **NOT_VERIFIED / NOT_RUN**.

## An toàn / rollback
- Không có workflow hoạt động, không tự merge, deploy hoặc sửa Billing.
- Quay lui bằng đóng Draft PR/xóa nhánh sau review, không đụng mã dự án khác.

## Cổng tiếp theo
- Review chính sách phân quyền và ngăn metadata kho Private rò rỉ.
- Kiểm tra GitHub App webhook PoC offline (HMAC, replay, idempotency, deny-by-default) trước khi đăng ký App thật.
- Việc bật tự động sau này cần sự phê duyệt riêng.
