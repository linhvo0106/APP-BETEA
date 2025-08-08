import RPi.GPIO as GPIO
import paho.mqtt.client as mqtt
import time
import threading
import pytz
import logging
from datetime import datetime, time as datetime_time

# Hằng số chuyển đổi: 100ml tương ứng 3 giây
# DEFAULT_TIME_PER_100ML = 5.5
# Hằng số chuyển đổi: 100ml tương ứng 5 giây
# DEFAULT_TIME_PER_100ML_SPECIAL = 5.5

# Biến global để lưu giá trị hiện tại
TIME_PER_100ML = 4.08
TIME_PER_100ML_MIK = 5.28
TIME_PER_100ML_SUG = 12.65
# Cấu hình chân GPIO cho module relay
RELAY_PINS = [15, 18, 16, 20, 21, 23]  # Chân GPIO kết nối với 5 relay
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
    if not GPIO.gpio_function(pin) == GPIO.OUT:
        GPIO.setup(pin, GPIO.OUT)
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.LOW)  # Ban đầu tắt tất cả relay

# Callback khi kết nối đến MQTT Broker
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Đã kết nối đến MQTT Broker!")
        # Đăng ký theo dõi nhiều topic
        client.subscribe([
            ("pump/control", 0),
            ("system/status", 0),
            ("pump/parameter", 0)
        ])
    else:
        print(f"Kết nối thất bại với mã lỗi {rc}")

def handle_system_status(msg):
    """Xử lý các lệnh hệ thống"""
    threads = []
    if msg == "###":
        # Chạy tất cả các bơm liên tục
        for i in range(len(RELAY_PINS)):
            threads.append(run_pump(i, -1))
            time.sleep(0.05)  # -1 là chế độ chạy liên tục
        logging.info("Tất cả các bơm đang chạy liên tục")
    elif msg == "000":
        # Dừng tất cả các bơm
        for i in range(len(RELAY_PINS)):
            threads.append(run_pump(i, 0))  # 0 là lệnh dừng
        logging.info("Tất cả các bơm đã dừng")
    elif msg == "***":
        # Chạy tất cả các bơm trong 5 giây rồi dừng
        logging.info("Chạy tất cả các bơm trong 5 giây")
        for i in range(len(RELAY_PINS)):
            GPIO.output(RELAY_PINS[i], GPIO.HIGH)
        time.sleep(5)
        for i in range(len(RELAY_PINS)):
            GPIO.output(RELAY_PINS[i], GPIO.LOW)
        logging.info("Tất cả các bơm đã dừng sau 5 giây")

def on_message(client, userdata, message):
    topic = message.topic
    msg = message.payload.decode("utf-8")
    print(f"Nhận được tin nhắn từ topic {topic}: {msg}")
    logging.info(f"Đã nhận tin nhắn MQTT từ topic {topic}: {msg}")
    logging.info("Start!")
    
    try:
        if topic == "system/status":
            handle_system_status(msg)
            return
        
        # elif topic == "pump/parameter":
        #     handle_pump_parameter(msg)
        #     return   
         
        elif topic == "pump/control":
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
            
            # Chờ tất cả các bơm hoàn thành
            for thread in active_threads:
                thread.join()
            
            logging.info("Done")
            logging.info("-" * 50)
                    
    except Exception as e:
        logging.error(f"Lỗi xử lý tin nhắn MQTT: {e}")
        print(f"Lỗi xử lý tin nhắn: {e}")

# Thêm biến global để điều khiển bơm liên tục
pump_running = [False] * len(RELAY_PINS)

# Hàm chạy máy bơm trong một thread riêng biệt
def pump_thread(index, state):
    try:
        if state == -1:  # Chạy liên tục
            pump_running[index] = True
            time.sleep(0.01)
            GPIO.output(RELAY_PINS[index], GPIO.HIGH)
            logging.info(f"Bơm {index + 1} bắt đầu chạy liên tục")
            # Vòng lặp để giữ bơm chạy liên tục
            while pump_running[index]:
                time.sleep(0.1)  # Kiểm tra mỗi 0.1 giây
            GPIO.output(RELAY_PINS[index], GPIO.LOW)
            logging.info(f"Bơm {index + 1} đã dừng chạy liên tục")
        elif state == 0:  # Dừng
            pump_running[index] = False
            GPIO.output(RELAY_PINS[index], GPIO.LOW)
            logging.info(f"Bơm {index + 1} đã dừng")
        else:  # Chạy theo thời gian định sẵn
            run_time = (state / 100) * (TIME_PER_100ML_MIK if index == 5 else TIME_PER_100ML_SUG if index == 4 else TIME_PER_100ML)
            GPIO.output(RELAY_PINS[index], GPIO.HIGH)
            logging.info(f"Bơm {index + 1} hoạt động {run_time:.2f} giây (Lưu lượng: {state}ml)")
            time.sleep(run_time)
            GPIO.output(RELAY_PINS[index], GPIO.LOW)
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


def main():
    try:
        print("Bắt đầu chương trình điều khiển máy bơm...")
        logging.info("Khởi động hệ thống")
                
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