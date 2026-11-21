# Các bước thao tác GitHub của chủ tài khoản

## Bước 1 — Đã thực hiện

Tạo repository `cavoixanh638/ci-standards` dạng Public. Repo đã được kết nối và khởi tạo `main` với README tối thiểu.

## Bước 2 — Đang nghiệm thu

Bộ mã được đề xuất qua nhánh `feat/account-wide-qa-bootstrap-20261121` và Draft PR vào `main`; chưa merge, không kích hoạt Actions. Xem `docs/account/STEP2_CHECKPOINT.md` và kiểm thử trước khi phê duyệt.

## Bước 3 — Chưa thực hiện

GitHub App riêng của chủ tài khoản và webhook receiver **chưa có**. Không được tạo bí mật trong chat hoặc commit. Để App thực sự tự phát hiện dự án mới, sau khi mã backend được duyệt sẽ cần bạn đăng ký App ở Settings → Developer settings → GitHub Apps, chọn sự kiện và cài vào All repositories. Phải kiểm tra quyền tối thiểu và có cơ chế ngắt khẩn cấp trước khi kích hoạt.

Không chuyển repository Private thành Public, không đổi Settings/Billing, không tự merge/deploy.
