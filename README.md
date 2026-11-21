# CI Standards — Account-wide QA bootstrap v0.2

**Trạng thái:** Bước 2, ứng viên Draft PR; chế độ `dry_run`. Chưa có GitHub App riêng, webhook receiver, Actions tự động hay thay đổi tại repository khác.

## Mục tiêu

Bộ chuẩn kiểm thử dùng chung cho các repository hiện tại và tương lai của tài khoản `cavoixanh638`, hỗ trợ:
- Phân loại mã nguồn thay đổi, chọn test phù hợp và không bỏ qua cổng bắt buộc.
- Checkpoint có bằng chứng và fingerprint; đánh giá việc tái sử dụng có điều kiện.
- Kiểm kê và lập kế hoạch onboarding ngoại tuyến, không thao tác trực tiếp vào repository.
- Chính sách ở cấp tài khoản: không kích hoạt CI trả phí, không tự merge/deploy.

## Chạy thử ngoại tuyến (không tạo Actions)

```sh
python3 -m unittest discover -s tests -v
python3 tools/validate_account_policy.py config/account.defaults.json
python3 tools/plan_onboarding.py --policy config/account.defaults.json --inventory examples/inventory.example.json
```

Bản chuẩn bị có 51/51 unit tests PASS khi chạy ngoại tuyến; kiểm thử Actions end-to-end: **NOT_RUN**.

## Cấu trúc

- `config/account.defaults.json`: chính sách bảo vệ mặc định, `dry_run`, ngân sách bổ sung 0 USD.
- `tools/validate_account_policy.py`: bộ xác thực chính sách, fail-closed.
- `tools/plan_onboarding.py`: dự kiến onboarding dựa trên inventory JSON, không gọi API.
- `tools/checkpoint.py`, `tools/checkpoint.schema.json`: hồ sơ kiểm thử và điều kiện tái sử dụng.
- `tools/select_tests.py`, `tools/policy-hdnd.json`: bộ chọn thử nghiệm cho HĐND, chỉ có tính tham khảo.
- `tests/`: bài kiểm thử hồi quy Python chuẩn.
- `docs/account/`: kiến trúc, checkpoint và quy trình kích hoạt an toàn.
- `templates/reusable-qa.yml.txt`: mẫu không thực thi (không đổi tên thành yml khi chưa nghiệm thu).
- `docs/qa/`: chính sách QA, ma trận, lịch sử, chi phí, hướng dẫn.

## Không được đưa lên repository Public

Tệp kiểm kê tên kho Private, credentials, dump dữ liệu, token, nội dung tài liệu riêng, thông tin thanh toán chi tiết. Không xem `max_additional_paid_usd=0` của bộ công cụ là bằng chứng GitHub Billing đã được khóa tương ứng.

## Sau PR

Chỉ sau khi chủ tài khoản nghiệm thu mới cân nhắc tích hợp mã vào `main`. Bước 3 sẽ nghiên cứu và tạo PoC GitHub App có xác thực webhook; chưa có bộ điều phối tự chạy nền. Không tự merge, deploy, sửa Billing hoặc vô hiệu required checks.
