# AI Hôm Nay Có Gì? — Newsroom

Ứng dụng biên tập tin AI tiếng Việt: thu thập → gom sự kiện → viết bản nháp → kiểm chứng/duyệt → tạo ảnh → lên lịch → đăng Facebook Page.

## Khởi động trên Windows (Python 3.12)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/setup_local.py
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Mở http://127.0.0.1:8000. Tên đăng nhập mặc định là `admin`; đọc mật khẩu ngẫu nhiên tại `ADMIN_PASSWORD` trong file `.env` trên máy. Script setup không ghi đè file đã có. Không đưa file này lên Git hoặc gửi mật khẩu/API key qua chat.

Với checkout cũ đã có .env, bổ sung ADMIN_PASSWORD (ít nhất 12 ký tự) và SECRET_KEY (ít nhất 32 ký tự ngẫu nhiên). Chạy migration trước khi khởi động. Nên sao lưu database và thư mục data/cards trước khi nâng cấp; dừng server để sao lưu SQLite hoặc dùng SQLite backup API.

## Chức năng

- Dashboard: thống kê dữ liệu thật, lịch lỗi/cần đối soát, trạng thái nguồn và nhật ký.
- Tin tức: tìm kiếm, lọc nguồn/trạng thái, phân trang, nội dung và liên kết nguồn.
- Sự kiện: so sánh các bài, chọn nguồn chính, gộp/chuyển bài trước khi tạo bản nháp.
- Nguồn: thêm/sửa/bật/tắt; RSS và đọc HTML có ngày xuất bản, không tạo nội dung giả.
- AI: Gemini GenerateContent hoặc OpenAI Responses, JSON schema và kiểm tra dữ liệu trả về.
- Biên tập: viết thủ công, sửa nội dung, ghi chú kiểm chứng, duyệt/từ chối; kiểm soát phiên bản chống ghi đè từ tab cũ.
- Ảnh: PNG 1200×630 từ tiêu đề, nhãn nguồn và bộ nhận diện; font hỗ trợ tiếng Việt.
- Lịch: giờ địa phương theo TIMEZONE, lưu UTC; chốt nội dung/ảnh; hủy, thử lại lỗi rõ ràng, đối soát lỗi không rõ kết quả.
- Facebook: bài văn bản hoặc ảnh kèm caption; lưu ID/link bài đã đăng.
- Đăng nhập: cookie ký, hết hạn sau 8 giờ, CSRF và giới hạn thử mật khẩu.

`sources.yaml` chỉ tự nhập khi database chưa có nguồn. Các thay đổi trên giao diện được giữ nguyên qua những lượt quét. Nút “Nhập từ YAML” cập nhật lại nguồn cùng tên; không xóa nguồn riêng đã thêm. URL của nhà cung cấp có thể thay đổi; xem lỗi tại trang Nguồn tin.

## Quy trình sử dụng

1. Mở Nguồn tin, bật các nguồn cần theo dõi; Quét tin từ Tổng quan.
2. Mở Sự kiện, kiểm tra bài nguồn và sửa nhóm nếu cần.
3. Chọn viết thủ công hoặc tạo bản nháp AI.
4. Sửa nội dung, ghi chú bằng chứng, lưu và tạo ảnh nếu cần. Kiểm tra cả ảnh.
5. Xác nhận đã kiểm tra nguồn rồi duyệt. Sửa nội dung/ảnh sẽ hủy phê duyệt cũ.
6. Chọn ngày giờ để lên lịch. Nội dung đã lên lịch bị khóa; hủy lịch trước khi sửa.
7. Khi đến giờ, bấm “Xử lý lịch”, hoặc bật AUTO_PUBLISH để scheduler xử lý.

Có thể thêm dữ liệu minh họa bằng `python scripts/generate_fixtures.py`. Script chỉ thêm bài có nhãn DEMO, không xóa dữ liệu hiện có. Không xuất bản các bài minh họa.

## Cấu hình AI

Trong .env, chọn `LLM_PROVIDER=gemini` hoặc `openai`, đặt `LLM_MODEL` là model hỗ trợ JSON schema mà tài khoản có quyền dùng, điền key tương ứng. Khởi động lại server. Không có key vẫn có thể biên tập thủ công và đăng thử.

AI chỉ đọc tối đa 8 bài nguồn, mỗi bài tối đa 6.000 ký tự. Các điểm quan trọng/phù hợp/tin cậy là gợi ý, không phải bằng chứng kiểm chứng độc lập. Người duyệt chịu trách nhiệm đối chiếu nguồn. Nội dung nguồn được gửi tới nhà cung cấp AI đã chọn khi bạn yêu cầu tạo bản nháp.

Tham khảo: [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [Gemini Structured Outputs](https://ai.google.dev/gemini-api/docs/structured-output).

## Facebook và đăng thử

Mặc định `FACEBOOK_DRY_RUN=true`, `AUTO_PUBLISH=false`: không gửi Facebook. Đăng thử tạo trạng thái “Đã đăng thử”, không tạo bản ghi bài Facebook, và trả bản nháp về “Đã duyệt”.

Đăng thật cần FACEBOOK_PAGE_ID, FACEBOOK_PAGE_ACCESS_TOKEN có quyền đăng Page và FACEBOOK_GRAPH_API_VERSION còn được Meta hỗ trợ. Sau khi kiểm tra quy trình, đổi FACEBOOK_DRY_RUN=false và khởi động lại. Các lịch đã tạo ở chế độ đăng thử vẫn là đăng thử; muốn đăng thật phải lên lịch mới.

Adapter dùng `POST /{page-id}/feed` hoặc `/{page-id}/photos`. Tham khảo [Meta Pages API](https://developers.facebook.com/docs/pages-api/posts/). Quyền thực tế phụ thuộc Page, ứng dụng và token; cấu hình đầy đủ chưa có nghĩa là đã xác minh quyền.

Chống đăng trùng:
- Claim tác vụ nguyên tử trong database; chỉ một lần xử lý nhận được lịch.
- Mỗi bản nháp chỉ có một lịch hoạt động. Nội dung trùng trên cùng Page được giữ chỗ.
- Snapshot bao gồm văn bản, ảnh, Page và chế độ đăng.
- HTTP 4xx rõ ràng có thể thử lại thủ công (tối đa 3 lần).
- Timeout/5xx/phản hồi không có ID hoặc gián đoạn sau khi gửi chuyển “Cần đối soát”. Không tự gửi lại.
- Nhập PAGE_ID_POST_ID để đối chiếu nội dung Facebook; hoặc tự kiểm tra Page, xác nhận chưa đăng rồi mới thử lại.
- Không thể bảo đảm exactly-once qua mạng nếu API không hỗ trợ idempotency. Đối soát thủ công là bắt buộc khi kết quả không rõ.

## Vận hành

Chạy **một worker ứng dụng** với SQLite. Scheduler chạy mỗi 15 giây, chỉ khi ứng dụng còn mở. AUTO_PUBLISH chỉ tự xử lý các bản đã duyệt và đã lên lịch; không tự duyệt. SCAN_INTERVAL_MINUTES=0 tắt quét định kỳ. Tác vụ đang quét/viết AI bị gián đoạn được đánh dấu lỗi khi khởi động lại; lịch đang gửi quá 10 phút chuyển sang đối soát.

Triển khai trên máy chủ: HTTPS, APP_ENV=production, COOKIE_SECURE=true, mật khẩu/secret mạnh, backup database và data/cards. Giới hạn egress mạng của server về Internet công khai; URL do quản trị viên cấu hình vẫn cần được tin cậy. Chưa hỗ trợ nhiều biên tập viên/phân quyền hoặc chạy nhiều worker. Không dùng database PostgreSQL với migration hiện tại mà chưa bổ sung migration enum và kiểm thử riêng.

Thu thập HTML chỉ hỗ trợ trang có nội dung article/main và ngày xuất bản trong HTML; trang JavaScript hoặc chống bot có thể cần collector riêng. Gom nhóm hiện dùng Jaccard trên tiêu đề, chưa dùng embeddings. Danh sách chọn nhóm đích hiển thị 300 nhóm mới nhất.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Test dùng database tạm, transport HTTP giả lập; không gọi AI, Facebook hoặc ghi database sử dụng thực tế. Test kiểm tra bảo vệ phiên, thao tác form, nhóm tin, pipeline biên tập, chống sửa phiên bản cũ, đăng thử, payload Facebook, timeout và đối soát. Các API bên ngoài cần kiểm thử riêng với thông tin kết nối thật.

## Kiến trúc

FastAPI + SQLAlchemy + SQLite/WAL + Alembic. Jinja2, CSS responsive và JavaScript nội bộ (không tải script CDN). APScheduler chạy tác vụ nền; bảng operations lưu trạng thái quét/AI. Các module chính: `app/services/ingestion.py`, `clustering.py`, `llm.py`, `publishing.py`, `operations.py`; giao diện trong `app/templates`.
