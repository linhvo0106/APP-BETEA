import RPi.GPIO as GPIO
import paho.mqtt.client as mqtt
import time
import threading
import pytz
import logging
from datetime import datetime, time as datetime_time

# Hằng số chuyển đổi: 100ml tương ứng 3 giây
TIME_PER_100ML = 2.7
# Hằng số chuyển đổi: 100ml tương ứng 5 giây
TIME_PER_100ML_special = 3

# Cấu hình chân GPIO cho module relay
RELAY_PINS = [15, 18, 16, 20, 21, 23, 24, 25, 8, 7]  # Chân GPIO kết nối với 5 relay
CONFIG_FILE = "app_betea/input/config.txt"
LOG_FILE = "app_betea/output/history.log"
VIETNAM_TZ = pytz.timezone("Asia/Ho_Chi_Minh")

# Thiết lập logging
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logging.Formatter.converter = lambda *args: datetime.now(VIETNAM_TZ).timetuple()

# Thiết lập GPIO
GPIO.setmode(GPIO.BCM)
for pin in RELAY_PINS:
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.LOW)  # Ban đầu tắt tất cả relay

# Callback khi kết nối đến MQTT Broker
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Đã kết nối đến MQTT Broker!")
        # Đăng ký theo dõi chủ đề pump/control
        client.subscribe("pump/control")
    else:
        print(f"Kết nối thất bại với mã lỗi {rc}")

# Hàm chạy máy bơm trong một thread riêng biệt
def pump_thread(index, state):
    try:
        if state == -1:  # Chạy liên tục
            GPIO.output(RELAY_PINS[index], GPIO.HIGH)
            logging.info(f"Bơm {index + 1} bắt đầu chạy liên tục")
        elif state == 0:  # Dừng
            GPIO.output(RELAY_PINS[index], GPIO.LOW)
            logging.info(f"Bơm {index + 1} đã dừng")
        else:  # Chạy theo thời gian định sẵn
            run_time = (state / 100) * (TIME_PER_100ML_special if index == 4 else TIME_PER_100ML)
            GPIO.output(RELAY_PINS[index], GPIO.HIGH)
            logging.info(f"Bơm {index + 1} hoạt động {run_time:.2f} giây (Lưu lượng: {state}ml)")
            time.sleep(run_time)
            GPIO.output(RELAY_PINS[index], GPIO.LOW)
            # logging.info(f"Bơm {index + 1} hoàn thành")
    except Exception as e:
        logging.error(f"Lỗi khi điều khiển bơm {index + 1}: {str(e)}")
        GPIO.output(RELAY_PINS[index], GPIO.LOW)  # Đảm bảo tắt bơm khi có lỗi

# Điều khiển bơm bằng cách tạo thread riêng
def run_pump(index, state):
    """Khởi động máy bơm trong một thread riêng"""
    pump_th = threading.Thread(target=pump_thread, args=(index, state))
    pump_th.daemon = True
    pump_th.start()
    return pump_th

# Sửa hàm on_message để xử lý các bơm chạy đồng thời
def on_message(client, userdata, message):
    msg = message.payload.decode("utf-8")
    print(f"Nhận được tin nhắn từ App BeTea: {msg}")
    logging.info(f"Đã nhận tin nhắn MQTT: {msg}")
    logging.info("Start!")
    
    try:
        # Kiểm tra nếu là lệnh đặc biệt
        if msg == "#|#|#|#|#":
            # Chạy tất cả các bơm liên tục
            threads = []
            for i in range(len(RELAY_PINS)):
                threads.append(run_pump(i, -1))  # -1 là chế độ chạy liên tục
            logging.info("Tất cả các bơm đang chạy liên tục")
            return
            
        if msg == "0|0|0|0|0":
            # Dừng tất cả các bơm
            threads = []
            for i in range(len(RELAY_PINS)):
                threads.append(run_pump(i, 0))  # 0 là lệnh dừng
            logging.info("Tất cả các bơm đã dừng")
            return

        # Xử lý các lệnh thông thường - chạy đồng thời
        pump_commands = msg.split("|")
        active_threads = []
        
        for command in pump_commands:
            if not command:
                continue
                
            pump_num, volume = map(int, command.split("-"))
            pump_index = pump_num - 1
            
            if 0 <= pump_index < len(RELAY_PINS):
                thread = run_pump(pump_index, volume)
                active_threads.append(thread)
            else:
                logging.error(f"Số bơm không hợp lệ: {pump_num}")
        
        # Chờ tất cả các bơm hoàn thành (không bắt buộc)
        # Nếu muốn báo cáo khi tất cả các bơm hoàn thành:
        for thread in active_threads:
            thread.join()
        
        # logging.info("Tất cả các bơm đã hoàn thành xong")
        logging.info("Done")
        logging.info("-" * 50)
                
    except Exception as e:
        logging.error(f"Lỗi xử lý tin nhắn MQTT: {e}")
        print(f"Lỗi xử lý tin nhắn: {e}")

def clear_log():
    """Xóa toàn bộ nội dung file history.log"""
    try:
        open(LOG_FILE, 'w').close()
        print("Đã xóa lịch sử log thành công")
        logging.info("Đã xóa log tự động")
    except Exception as e:
        print(f"Lỗi khi xóa file log: {e}")
        logging.error(f"Lỗi khi xóa log: {e}")

def auto_clear_log():
    """Tự động xóa log vào 00:00 mỗi ngày"""
    while True:
        now = datetime.now(VIETNAM_TZ)
        # Đặt thời gian xóa log là 00:00
        next_run = datetime.combine(now.date(), datetime_time(0, 0))
        next_run = VIETNAM_TZ.localize(next_run)
        
        if now >= next_run:
            # Nếu đã qua 00:00, đợi đến ngày mai
            next_run = next_run.replace(day=next_run.day + 1)
        
        # Tính thời gian chờ đến lần xóa tiếp theo
        sleep_seconds = (next_run - now).total_seconds()
        time.sleep(sleep_seconds)
        
        # Xóa log
        clear_log()

def main():
    try:
        print("Bắt đầu chương trình điều khiển máy bơm...")
        logging.info("Khởi động hệ thống")
        
        # Thêm thread xóa log tự động
        auto_clear_thread = threading.Thread(target=auto_clear_log)
        auto_clear_thread.daemon = True
        auto_clear_thread.start()
        
        # Tạo MQTT client
        client = mqtt.Client()
        client.on_connect = on_connect
        client.on_message = on_message

        # Địa chỉ MQTT Broker
        mqtt_broker = "localhost"  
        mqtt_port = 1883

        # Kết nối đến MQTT Broker
        client.connect(mqtt_broker, mqtt_port, 60)
        print(f"Đang kết nối đến MQTT Broker {mqtt_broker}:{mqtt_port}")
        print("Đang chờ tin nhắn MQTT từ App BeTea...")
        
        # Chạy MQTT client trong thread chính
        client.loop_forever()
            
    except KeyboardInterrupt:
        print("\nĐang dừng chương trình...")
        logging.info("Dừng hệ thống")
    except Exception as e:
        logging.error(f"Lỗi: {str(e)}")
        print(f"Lỗi: {str(e)}")
    finally:
        # Đảm bảo tắt tất cả các bơm khi kết thúc
        for pin in RELAY_PINS:
            GPIO.output(pin, GPIO.LOW)
        GPIO.cleanup()

if __name__ == "__main__":
    main()