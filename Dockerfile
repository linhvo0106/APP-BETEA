# 1. Base image nhẹ với Python 3.11
FROM python:3.11-slim

# 2. Tạo thư mục làm việc trong container
WORKDIR /app

# 3. Copy toàn bộ project vào container
COPY . /app

# 4. Copy requirements (nếu bạn chưa có, tạo từ pip freeze)
# Nếu chưa có requirements.txt, bạn có thể viết tay như sau:
# fake-rpi, websockets, paho-mqtt (tùy project bạn dùng gì)
COPY requirements.txt .

# 5. Cài đặt thư viện cần thiết
RUN pip install --no-cache-dir -r requirements.txt

# 6. Cấu hình biến môi trường (tuỳ chọn)
ENV PYTHONUNBUFFERED=1

# 7. Chạy file chính
CMD ["python", "main/main.py"]
