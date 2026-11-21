# Bước 3 — GitHub App tự phát hiện repository (PoC chỉ đọc)

**Trạng thái 22/11/2026:** Đã viết và kiểm thử trên máy cô lập. Chưa đăng ký GitHub App riêng, chưa triển khai HTTPS receiver, chưa cài App, chưa đụng GitHub Settings/Actions/Billing. Bộ công cụ đang ở stacked Draft PR dự kiến trên nhánh Bước 2; chưa hoạt động nền.

## Luồng vận hành đã lập trình

1. **Webhook có HMAC-SHA256:** chỉ tiếp nhận sau khi kiểm tra chữ ký `X-Hub-Signature-256` trên raw bytes. Chặn thiếu/mất chữ ký, sai owner, sai App installation ID, duplicate JSON keys, payload vượt 512 KiB, event lạ.
2. **Chống replay:** khóa `X-GitHub-Delivery` (UUID) và SHA-256 nội dung trong SQLite. Gửi lại y hệt = idempotent; trùng ID nhưng khác nội dung = từ chối.
3. **Phát hiện sự kiện:** `repository.created/renamed/deleted/archived/...`, `installation.created/deleted/suspend/unsuspend`, `installation_repositories.added/removed`. Repo bị gỡ quyền được đánh dấu không truy cập được, không còn là đối tượng đề xuất.
4. **Kiểm kê ban đầu và dự phòng:** đọc danh sách `GET /installation/repositories` qua installation access token giới hạn **Metadata: read**, xử lý phân trang và chỉ commit inventory khi mọi trang hợp lệ. Có tùy chọn tự đồng bộ sáu giờ/lần qua `--live` khi có App auth và host thật.
5. **Đích trạng thái:** SQLite riêng, không lưu raw webhook, không đưa danh sách repo Private vào repo Public, không thay đổi kho nguồn. Không tạo workflow hoặc Actions nào.

## Quyền GitHub App ở giai đoạn hiện tại

| Thiết lập | Giá trị tối thiểu |
|---|---|
| Owner | Tài khoản cá nhân `cavoixanh638` |
| Availability | Only on this account (`private` App) |
| Repository access khi cài đặt | All repositories, sau khi xác minh quyền |
| Repository permission | Metadata: Read-only |
| Subscribe | Repository |
| Events mặc định | Installation, Installation repositories |
| Contents Write / Pull Requests Write | Không xin ở bước này |
| Administration / Secrets / Actions Write | Không xin |
| Webhook URL | HTTPS công khai của máy chủ do chủ tài khoản kiểm soát; **chưa có** |

**Không đăng ký App bằng một webhook URL giả và bật nhận sự kiện.** Đợi chọn HTTPS host, lưu secret trong kho bí mật và kiểm thử delivery thực tế, rồi mới bật webhook. App mới khác hoàn toàn GitHub App kết nối ChatGPT đang có.

## Chạy kiểm thử và nghiệm thu

```sh
python3 -m unittest discover -s tests -v
python3 -m github_app.cli --help
python3 tools/validate_account_policy.py config/account.defaults.json
```

Bằng chứng test cụ thể trong `STEP3_CHECKPOINT.md`. Test offline không phải nghiệm thu webhook thật; JWT/installation token chưa được phát hành từ GitHub trong phiên này. Khi vận hành thật phải kiểm tra TLS, retries, response codes, rate limit, quyền khi chuyển Public/Private, khả năng hồi phục SQLite và backup ngoài máy.

## Chặn triển khai và dừng khẩn cấp

- Default `config/account.defaults.json`: `dry_run`, `allow_repository_writes=false`, `create_pr_automatically=false`, `allow_workflow_execution=false`, `max_additional_paid_usd=0`.
- Receiver chỉ có API metadata read và không chứa lệnh ghi repo, Actions dispatch, merge, deploy.
- Dừng khẩn: dừng tiến trình hoặc tắt webhook trong App Settings, thu hồi App key/installation; không có code được tự phục hồi nhờ Actions.
- Những kho Private và chi phí chỉ được kiểm soát qua cấu hình và GitHub Billing thực, không dựa trên cơ sở dữ liệu này làm chứng nhận đã miễn phí.

## Bước 4 sau khi duyệt

Thiết kế cơ chế tạo **Draft PR** cho từng repo theo policy: phân loại công nghệ -> phát hiện required checks -> ước lượng trigger trước khi push -> tạo nhánh an toàn -> đề xuất sửa ở chế độ opt-in -> chủ tài khoản review. App cần cấp thêm quyền Contents/Pull requests sau khi quyền được nghiệm thu, không xin trước.
