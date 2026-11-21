# Kiến trúc tự động hóa GitHub toàn tài khoản — thiết kế dự kiến

Ngày: 2026-11-21. Chủ sở hữu: `cavoixanh638`.

## Phân lớp

1. **Policy công khai:** `ci-standards` chỉ giữ công cụ và chính sách tổng quát; không công khai inventory hoặc metadata kho Private.
2. **Nguồn kiểm kê:** GitHub API của installation được phép xem các kho, kết quả phân loại và thông tin kho Private chỉ lưu ở vùng riêng.
3. **Bộ điều phối tương lai:** GitHub App do chủ tài khoản đăng ký và cài **All repositories**. Nhận webhook `repository`, `installation_repositories`, `pull_request`, `push` tại backend có xác thực HMAC và chống replay; hiện **chưa triển khai**.
4. **Lớp kiểm thử:** quick (cục bộ), selective (PR thay đổi phù hợp), acceptance (bảo mật/dữ liệu/release) theo chính sách từng repo.
5. **Onboarding:** phát hiện repo → khảo sát trigger/required checks → đề xuất Draft PR → chủ tài khoản duyệt → chạy đúng phạm vi. Không tự sửa `main`.

## Quyết định về quyền

- Reusable workflow trong `ci-standards` Public có thể được repository Private gọi sau khi thêm caller và pin SHA chính xác.
- Kết nối GitHub của ChatGPT đang có quyền với All repositories **không phải** dịch vụ tự động chạy nền. Không dùng installation hiện có như một GitHub App mới do chủ tài khoản quản lý.
- GitHub App tương lai chỉ nên nhận quyền nhỏ nhất; khi cần ghi chỉ đề xuất thay đổi trên branch/PR, không cấp quyền Administration, Secrets/Billing hoặc Deploy không cần thiết.
- Muốn tự nhận repo mới thì phải có webhook receiver hoặc polling bền vững; kho GitHub tĩnh không tự nhận webhook.

## Kiểm soát chi phí

- `dry_run` không khởi chạy workflow hoặc thao tác vào kho khác.
- Không chạy Actions ở repo Private khi chưa được cho phép; không đặt `schedule` hoặc gọi workflow nặng tự động ở bước này.
- Chỉ dùng cache/fingerprint cho những bài có bằng chứng tương đương. Không lấy `SKIPPED` hoặc `NOT_RUN` làm PASS.
- Ngân sách bổ sung 0 USD là policy của công cụ; việc khóa Billing thực tế cần được kiểm tra riêng trong GitHub Settings.

## Điều kiện trước khi bật chế độ thực

- Kiểm tra GitHub App permissions, webhook HMAC signature, event replay/idempotency, xử lý repository đổi quyền.
- Xác nhận dependency graph, required checks/branch protection, test suites, change filters từng dự án.
- Chỉ phát hành sau review và nghiệm thu thủ công, không tự merge/deploy.
- Có giám sát và phương án dừng/rollback.
