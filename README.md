# 🎧 Mac Live Translator & Visual Meeting Understanding Copilot

> **Giải pháp theo dõi và hiểu cuộc họp kỹ thuật tiếng Anh theo thời gian thực dành cho người dùng Việt Nam trên macOS Apple Silicon (M1/M2/M3/M4).**

Ứng dụng kết hợp hai luồng xử lý độc lập và bổ trợ cho nhau:
1. **Pipeline A — Phụ đề trực tiếp (Live Vietsub 2.0)**: Chạy 100% offline trên máy (MLX Whisper Small.en + Ollama TranslateGemma 4B), dịch tức thì từng câu nói thành phụ đề tiếng Việt mượt mà, độ trễ thấp.
2. **Pipeline B — Hiểu cuộc họp trực quan (Visual Meeting Understanding)**: Dịch vụ ngữ cảnh cục bộ (SQLite FTS5) kết hợp phân tích đơn lượt Claude Haiku 5.5 (chỉ bật khi người dùng chủ động cho phép). Trích xuất thẻ ý chính (Meaning Cards), tóm tắt quyết định, hành động, câu hỏi mở, hỗ trợ đọc tập trung (**Freeze Reading**) và bắt kịp nội dung (**Catch Up**) mà không làm gián đoạn việc theo dõi cuộc họp.
3. **Meeting Copilot**: Trợ lý đề xuất câu trả lời tiếng Anh (1–3 câu ngắn gọn kèm trích dẫn nguồn), giải thích ngữ cảnh và tra cứu tài liệu nội bộ (.md, .txt).

---

## 📋 Mục lục

- [1. Yêu cầu hệ thống & Kiến trúc](#1-yêu-cầu-hệ-thống--kiến-trúc)
- [2. Hướng dẫn cài đặt từ A đến Z](#2-hướng-dẫn-cài-đặt-từ-a-đến-z)
- [3. Cấu hình định tuyến âm thanh (Audio MIDI Setup)](#3-cấu-hình-định-tuyến-âm-thanh-audio-midi-setup)
- [4. Hướng dẫn chạy ứng dụng (Quickstart)](#4-hướng-dẫn-chạy-ứng-dụng-quickstart)
- [5. Hướng dẫn sử dụng chi tiết](#5-hướng-dẫn-sử-dụng-chi-tiết)
  - [Chế độ Hiểu trực quan (Visual Understanding Mode)](#-chế-độ-hiểu-trực-quan-visual-understanding-mode)
  - [Chế độ Phụ đề chi tiết (Live Vietsub 2.0)](#-chế-độ-phụ-đề-chi-tiết-live-vietsub-20)
  - [Trợ lý Meeting Copilot](#-trợ-lý-meeting-copilot)
- [6. Chạy riêng dịch vụ Context Service (FastAPI)](#6-chạy-riêng-dịch-vụ-context-service-fastapi)
- [7. Xử lý sự cố thường gặp (Troubleshooting)](#7-xử-lý-sự-cố-thường-gặp-troubleshooting)

---

## 1. Yêu cầu hệ thống & Kiến trúc

- **Hệ điều hành**: macOS Apple Silicon (M1 Pro, M1 Max, M2, M3, M4...). Tối thiểu 16GB Unified Memory.
- **Python Runtime**: Python 3.12 (quản lý tự động qua `uv` và file khoá `uv.lock`).
- **Mô hình AI cục bộ**:
  - ASR: `mlx-community/whisper-small.en-mlx` (tối ưu hoá Metal Performance Shaders trên Apple Silicon).
  - Dịch thuật: `translategemma:4b` chạy trên máy chủ Ollama cục bộ (`127.0.0.1:11434`).
- **Bảo mật & Quyền riêng tư (Privacy-First)**:
  - 100% âm thanh và biên bản dịch cơ bản không bao giờ rời khỏi máy của bạn.
  - Phân tích Claude chỉ kích hoạt khi người dùng **tích chọn rõ ràng** (Cloud Opt-In mặc định luôn tắt).
  - Toàn bộ dữ liệu phiên họp lưu trong bộ nhớ tạm (in-memory SQLite FTS5) và tự động xoá sạch khi đóng ứng dụng.

---

## 2. Hướng dẫn cài đặt từ A đến Z

Mở ứng dụng **Terminal** trên macOS và thực hiện tuần tự các bước sau:

### Bước 2.1: Cài đặt công cụ nền tảng qua Homebrew

```bash
# Cài đặt Homebrew (nếu máy chưa có)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Cài đặt uv (quản lý gói Python siêu nhanh), ffmpeg, ollama và BlackHole 2ch
brew install uv ffmpeg ollama
brew install --cask blackhole-2ch
```

> **Lưu ý**: Sau khi cài đặt BlackHole, bạn có thể cần vào **System Settings > Privacy & Security** để cấp quyền âm thanh nếu macOS yêu cầu.

### Bước 2.2: Khởi động Ollama và tải mô hình TranslateGemma 4B

```bash
# Khởi động dịch vụ Ollama chạy nền
brew services start ollama

# Hoặc khởi động thủ công:
# ollama serve

# Tải mô hình dịch chuyên sâu TranslateGemma 4B (khoảng 3.3 GB)
ollama pull translategemma:4b
```

Kiểm tra mô hình đã sẵn sàng chưa bằng lệnh:
```bash
ollama list
```
*(Nếu thấy `translategemma:4b` xuất hiện trong danh sách là thành công).*

### Bước 2.3: Đồng bộ môi trường Python của dự án

Di chuyển vào thư mục dự án và chạy:

```bash
cd mac-live-voice-translator-m1pro

# Cài đặt toàn bộ dependencies theo uv.lock
uv sync --locked

# Tải trước trọng số Whisper Small.en tối ưu MLX về bộ nhớ đệm
uv run --locked python -c 'from huggingface_hub import snapshot_download; snapshot_download("mlx-community/whisper-small.en-mlx")'
```

---

## 3. Cấu hình định tuyến âm thanh (Audio MIDI Setup)

Để ứng dụng nghe được âm thanh từ cuộc họp (Google Meet, Zoom, Teams, YouTube) trong khi tai bạn vẫn nghe thấy tiếng bình thường, cần tạo **Multi-Output Device**:

1. Mở ứng dụng **Audio MIDI Setup** (bấm `Cmd + Space`, gõ `Audio MIDI Setup` rồi Enter).
2. Ở góc dưới bên trái, bấm nút dấu **`+`** ➔ Chọn **Create Multi-Output Device**.
3. Ở khung bên phải:
   - Đặt tên thiết bị là: **`Multi-Output Device`** (viết đúng chính tả).
   - Tích chọn **BlackHole 2ch**.
   - Tích chọn **Tai nghe của bạn** (ví dụ: *External Headphones*, *MacBook Pro Speakers*, hoặc *AirPods*).
   - Đặt thiết bị tai nghe của bạn làm **Master Device** (hoặc tích chọn Drift Correction cho BlackHole).
4. Mở **System Settings > Sound > Output**:
   - Chọn ngõ ra âm thanh chính của máy Mac là: **Multi-Output Device**.
   - Bật thử một video tiếng Anh trên YouTube, kiểm tra xem tai nghe của bạn vẫn nghe rõ tiếng.
5. Trong ứng dụng cuộc họp (Google Meet / Zoom):
   - **Microphone**: Chọn Micro thật của bạn (MacBook Mic / Headset Mic).
   - **Speaker**: Chọn *Same as System* hoặc *Multi-Output Device*.

---

## 4. Hướng dẫn chạy ứng dụng (Quickstart)

Chạy giao diện Desktop PySide6:
```bash
uv run --locked python ui.py
```

Chạy dịch vụ Context Service REST API độc lập (nếu cần):
```bash
uv run --locked python -m mac_live_translator.context_service.server
```

Kiểm tra thiết bị âm thanh:
```bash
uv run --locked python main.py --list-devices
```

> **Lưu ý khi chạy**:
> 1. Trên giao diện, chọn **Đầu vào (Input)** là `BlackHole 2ch`, **Đầu ra (Output)** là `Multi-Output Device` rồi bấm **▶ Start**.
> 2. Để dùng trợ lý Claude (Hiểu cuộc họp hoặc Copilot), hãy dán API key qua nút **⚙ Key** hoặc chạy `export ANTHROPIC_API_KEY="..."` trước.

---

## 5. Hướng dẫn sử dụng chi tiết

### 🧠 Chế độ Hiểu trực quan (Visual Understanding Mode)

Dành cho người dùng hạn chế kỹ năng nghe tiếng Anh, muốn nắm bắt bức tranh toàn cảnh của cuộc họp kỹ thuật mà không cần căng mắt đọc từng dòng phụ đề chạy liên tục:

- **Chuyển chế độ**: Bấm nút **`🧠 Hiểu trực quan`** ở góc trên khung bên trái.
- **Bật phân tích Claude**: Tích chọn `☁️ Bật phân tích hiểu cuộc họp (Cloud Understanding Opt-In)` và xác nhận đồng ý trên hộp thoại bảo mật.
- **📌 Chủ đề hiện tại (Current Topic)**: Tự động cập nhật chủ đề kỹ thuật mà team đang thảo luận (ví dụ: *Cấu hình Redis Cache và Migration Database*).
- **❓ Câu hỏi đang thảo luận**: Khi có người đặt câu hỏi thảo luận, khung câu hỏi sẽ được ghim nổi bật.
- **💡 Thẻ ý chính (Meaning Cards)**:
  - Hiển thị 3–5 thẻ ý gần nhất, mỗi thẻ gói gọn **1 ý chính rõ ràng**, kèm 1–2 gạch đầu dòng giải thích ngắn gọn bằng tiếng Việt tự nhiên.
  - Đã loại bỏ từ đệm ("uh", "um", "you know").
  - Phân loại rõ ràng qua nhãn màu: `✅ QUYẾT ĐỊNH`, `📋 HÀNH ĐỘNG`, `💡 Ý CHÍNH`, `❓ CÂU HỎI`, `💭 ĐỀ XUẤT`.
  - Có trích dẫn mã đoạn gốc: `[T#12, T#13]`.
- **✅ Quyết định & 📋 Hành động đã chốt**: Tổng hợp nhanh các thỏa thuận đã chốt và công việc cụ thể (kèm người phụ trách và hạn chót nếu có).
- **⏸ Đọc tập trung (Freeze Reading)**:
  - Khi cần đọc kỹ một thẻ ý hoặc thảo luận mà không muốn nội dung mới đẩy trôi màn hình, hãy tích chọn **`⏸ Tạm dừng cuộn (Freeze Reading)`**.
  - Hệ thống vẫn âm thầm xử lý audio và phân tích nền. Huy hiệu `🔔 X ý mới đang chờ` sẽ đếm số lượng thẻ ý mới.
- **⚡ Bắt kịp (Catch Up)**:
  - Bấm nút **`⚡ Bắt kịp (Catch Up)`** để xem tóm lược nhanh các ý vừa bỏ lỡ trong lúc dừng đọc và lập tức đồng bộ đến các thẻ mới nhất.
- **Phụ đề trực tiếp tham chiếu**: Hộp phụ đề tiếng Việt gọn gàng ở dưới cùng giúp bạn dễ dàng đối chiếu khi cần.

---

### 💬 Chế độ Phụ đề chi tiết (Live Vietsub 2.0)

Dành cho người muốn theo dõi sát từng câu nói song ngữ:
- Bấm nút **`💬 Phụ đề chi tiết`** ở góc trên khung bên trái.
- **Phụ đề đang nói (Live Caption)**: Hiển thị câu tiếng Việt trực tiếp đang nói với độ trễ thấp và màu sắc phân biệt nháp/ổn định.
- **Phụ đề vừa xác nhận**: Hiển thị 2 câu hoàn tất gần nhất.
- **Biên bản hội thoại**: Cho phép xem lại toàn bộ lịch sử dạng `VI - Bản dịch`, `EN - Transcript`, hoặc `Song ngữ (Bilingual)`.

---

### 🤖 Trợ lý Meeting Copilot

Nằm ở khung bên phải, hỗ trợ bạn phản hồi và tương tác trong cuộc họp:

- **Help Me Reply (Gợi ý câu trả lời)**: Bấm nút này để Claude Haiku soạn sẵn 1–3 câu tiếng Anh nói tự nhiên, lịch sự dựa đúng ngữ cảnh cuộc họp. Kèm theo bản dịch nghĩa tiếng Việt và nút **📋 Sao chép** để bạn có thể copy hoặc đọc ngay.
- **Explain Context (Giải thích ngữ cảnh)**: Giải thích nhanh quyết định kỹ thuật, sự đồng thuận hoặc các khó khăn (blocker) đang tranh luận.
- **Suggest Question (Gợi ý câu hỏi)**: Gợi ý câu hỏi kỹ thuật thông minh, mang tính xây dựng để bạn hỏi lại đối tác.
- **Nạp tài liệu dự án (.md, .txt)**: Bấm vào thẻ **`📄 Tài liệu`** để nạp các file tài liệu thiết kế hệ thống hoặc README dự án. Copilot sẽ tự động tìm kiếm FTS5 và đối chiếu khi trả lời.
- **Thu gọn trí nhớ cuộc họp (Incremental Compaction)**: Bấm vào thẻ **`📚 Ngữ cảnh họp`** để xem hoặc kích hoạt thu gọn trí nhớ dài hạn của cuộc họp mà không lo tràn token.

---

## 6. Chạy riêng dịch vụ Context Service (FastAPI)

Ứng dụng desktop tích hợp sẵn Context Service chạy in-process cực nhanh và an toàn. Tuy nhiên, nếu bạn muốn tích hợp hoặc kiểm thử qua REST API trên cổng mạng cục bộ:

Khởi chạy server FastAPI:
```bash
uv run --locked python -m mac_live_translator.context_service.server
```
Dịch vụ sẽ lắng nghe tại `http://127.0.0.1:8765` với các endpoint chuẩn:

| Phương thức | Endpoint | Mô tả |
|---|---|---|
| `POST` | `/sessions` | Khởi tạo phiên họp mới (`session_id`) |
| `POST` | `/sessions/{id}/segments` | Nạp đoạn tiếng Anh hoàn tất vào FTS5 (idempotent) |
| `POST` | `/sessions/{id}/analyze` | Kích hoạt phân tích ý chính đơn lượt qua Claude |
| `GET` | `/sessions/{id}/feed` | Lấy danh sách thẻ ý, chủ đề, quyết định hiện tại |
| `POST` | `/sessions/{id}/search` | Tìm kiếm toàn văn biên bản họp bằng SQLite FTS5 |
| `POST` | `/sessions/{id}/catchup` | Lấy nội dung và tóm tắt thẻ ý chưa đọc từ `last_read_card_id` |
| `DELETE` | `/sessions/{id}` | Xoá sạch phiên họp và giải phóng bộ nhớ tạm |

---

## 7. Xử lý sự cố thường gặp (Troubleshooting)

### 1. Bấm Start nhưng không thấy phụ đề tiếng Anh xuất hiện
- **Kiểm tra âm lượng**: Đảm bảo video YouTube hoặc cuộc họp đang phát ra tiếng và bạn đang nghe thấy trong tai nghe.
- **Kiểm tra thiết bị**: Chạy lệnh kiểm tra danh sách thiết bị âm thanh:
  ```bash
  uv run --locked python main.py --list-devices
  ```
  Xác nhận `BlackHole 2ch` và `Multi-Output Device` hiển thị đúng.
- **Kiểm tra tên thiết bị**: macOS Sound Output bắt buộc phải đặt tên chính xác là `Multi-Output Device`.

### 2. Báo lỗi `ConnectionRefusedError` tới Ollama (11434)
- Kiểm tra xem dịch vụ Ollama đã chạy chưa:
  ```bash
  curl http://127.0.0.1:11434
  ```
- Nếu chưa chạy, hãy khởi động lại bằng:
  ```bash
  brew services restart ollama
  # hoặc chạy cửa sổ riêng: ollama serve
  ```

### 3. Không tạo được thẻ ý chính (Meaning Cards)
- Kiểm tra xem bạn đã tích chọn `☁️ Bật phân tích hiểu cuộc họp (Cloud Understanding Opt-In)` chưa.
- Kiểm tra Anthropic API Key bằng nút **⚙ Key** xem key có hợp lệ và còn số dư không.
- Chế độ phân tích gom nhóm từ 5–8 câu nói hoặc sau 15–25 giây để tối ưu chi phí và tránh spam API, vì vậy hãy kiên nhẫn sau vài câu nói ban đầu.

### 4. Kiểm tra biên dịch toàn bộ mã nguồn
Trước khi đóng gói hoặc cập nhật code:
```bash
uv run --locked python -m compileall -q -x '/(\.venv|\.git)/' .
git diff --check
```
