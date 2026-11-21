# CI Standards — Account-wide QA standard (staged)

Repository trung tâm dành cho `cavoixanh638`. **Giai đoạn 3: bộ nhận webhook và kiểm kê GitHub App chỉ đọc đã được viết/test ngoại tuyến; chưa đăng ký App, chưa triển khai máy chủ, chưa kích hoạt tự động thực tế.**

## Các thành phần hiện có

- `config/account.defaults.json`: chính sách `dry_run`, không tự tạo PR, không chạy CI, không merge, không deploy hoặc tiêu tiền GitHub.
- `tools/select_tests.py` + `tools/policy-hdnd.json`: chọn test thận trọng theo ảnh hưởng của mã nguồn (chưa dùng như cổng production).
- `tools/checkpoint.py` + JSON Schema: bằng chứng PASS/FAIL/NOT_RUN và fingerprint kiểm thử.
- `tools/plan_onboarding.py`: lập kế hoạch onboarding từ inventory JSON ngoại tuyến.
- **`github_app/`:** GitHub App controller PoC: webhook HMAC-SHA256, chống replay bằng SQLite, kiểm tra owner/installation, nhận diện repo mới/đổi quyền, đồng bộ metadata read-only có phân trang và chế độ định kỳ khi operator bật `--live`.
- `tests/`: unit và HTTP integration test cục bộ. Không có `.github/workflows`, không gọi Actions.
- `docs/account/STEP3_WEBHOOK.md`: kiến trúc, quyền tối thiểu, setup với HTTPS, dừng khẩn.

## Tự kiểm thử mà không dùng GitHub Actions

```sh
python3 -m unittest discover -s tests -v
python3 tools/validate_account_policy.py config/account.defaults.json
python3 -m github_app.cli --help
```

## Quy tắc an toàn

Không commit inventory Private, token/key, bản ghi/tài liệu riêng hoặc billing export vào repo Public. Không coi GitHub App kết nối ChatGPT là App receiver của hệ thống. Chỉ khi có HTTPS host, App do chủ tài khoản đăng ký với **Metadata: read**, cài **All repositories** và cấu hình khóa an toàn mới có thể nhận webhook thực tế. Để tự tạo PR, cần bước riêng xét quyền ghi và điều kiện kiểm thử, không được mặc định bật.

Xem hướng dẫn tại [`github_app/README.md`](github_app/README.md), [`docs/account/STEP3_WEBHOOK.md`](docs/account/STEP3_WEBHOOK.md) và [`docs/account/STEP3_CHECKPOINT.md`](docs/account/STEP3_CHECKPOINT.md).
