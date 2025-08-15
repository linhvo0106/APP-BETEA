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
TIME_PER_100ML_DEFAULT = 10
TIME_PER_100ML_1 = 10.8
TIME_PER_100ML_2 = 12.06
TIME_PER_100ML_3 = 11.67
TIME_PER_100ML_4 = 9.68

TIME_PER_100ML_MIK = 10
TIME_PER_100ML_SUG = 10

time_per_pump = [
    TIME_PER_100ML_1,    # index 0 - Bơm 1
    TIME_PER_100ML_2,    # index 1 - Bơm 2
    TIME_PER_100ML_3,    # index 2 - Bơm 3  
    TIME_PER_100ML_4,    # index 3 - Bơm 4
    TIME_PER_100ML_SUG,  # index 4 - Bơm 5
    TIME_PER_100ML_MIK   # index 5 - Bơm 6
]

# Cấu hình chân GPIO cho module relay
PUMP_PINS = [15, 18, 16, 20, 21, 23]  # Chân GPIO kết nối với 5 relay
CLEAN_PIN = 26
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
for pin in PUMP_PINS:
    if not GPIO.gpio_function(pin) == GPIO.OUT:
        GPIO.setup(pin, GPIO.OUT)
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.LOW)  # Ban đầu tắt tất cả relay

GPIO.setup(CLEAN_PIN, GPIO.OUT)
GPIO.output(CLEAN_PIN, GPIO.LOW)  # Ban đầu tắt relay làm sạch

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

def pump_with_custom_time(index, run_time):
    """Chạy bơm với thời gian tùy chỉnh (giây)"""
    try:
        GPIO.output(PUMP_PINS[index], GPIO.HIGH)
        logging.info(f"Bơm {index + 1} bắt đầu chạy trong {run_time} giây")
        time.sleep(run_time)
        GPIO.output(PUMP_PINS[index], GPIO.LOW)
    except Exception as e:
        logging.error(f"Lỗi khi chạy bơm {index + 1}: {str(e)}")
        GPIO.output(PUMP_PINS[index], GPIO.LOW)

def handle_system_status(msg):
    """Xử lý các lệnh hệ thống"""
    threads = []
    if msg == "###":
        # Chạy tất cả các bơm liên tục
        GPIO.output(CLEAN_PIN, GPIO.HIGH)  # Bật relay làm sạch
        logging.info("Relay vệ sinh bật")
        for i in range(len(PUMP_PINS)):
            threads.append(run_pump(i, -1))
            time.sleep(0.05)  # -1 là chế độ chạy liên tục
        logging.info("Tất cả các bơm đang chạy liên tục")
    elif msg == "000":
        # Dừng tất cả các bơm
        GPIO.output(CLEAN_PIN, GPIO.LOW)  # Tắt relay làm sạch
        logging.info("Relay vệ sinh tắt")
        for i in range(len(PUMP_PINS)):
            threads.append(run_pump(i, 0))  # 0 là lệnh dừng
        logging.info("Tất cả các bơm đã dừng")
    elif msg == "***":
        # Chạy tất cả các bơm song song với thời gian riêng biệt
        logging.info("Ready for business")
        
        # Định nghĩa thời gian chạy cho từng bơm (giây)
        pump_times = [3.0, 4.0, 2.5, 5.0, 3.5, 4.5]  # Thời gian cho bơm 1-6
        
        # Tạo thread cho từng bơm với thời gian riêng
        active_threads = []
        for i in range(len(PUMP_PINS)):
            run_time = pump_times[i]
            thread = threading.Thread(target=pump_with_custom_time, args=(i, run_time))
            thread.daemon = True
            thread.start()
            active_threads.append(thread)
            
        # Chờ tất cả các bơm hoàn thành
        for thread in active_threads:
            thread.join()
            
        # logging.info("Hoàn thành chạy tất cả các bơm với thời gian riêng biệt")

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
                
                if 0 <= pump_index < len(PUMP_PINS):
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
pump_running = [False] * len(PUMP_PINS)

# Hàm chạy máy bơm trong một thread riêng biệt
def pump_thread(index, state):
    try:
        if state == -1:  # Chạy liên tục
            pump_running[index] = True
            time.sleep(0.01)
            GPIO.output(PUMP_PINS[index], GPIO.HIGH)
            logging.info(f"Bơm {index + 1} bắt đầu chạy liên tục")
            # Vòng lặp để giữ bơm chạy liên tục
            while pump_running[index]:
                time.sleep(0.1)  # Kiểm tra mỗi 0.1 giây
            GPIO.output(PUMP_PINS[index], GPIO.LOW)
            logging.info(f"Bơm {index + 1} đã dừng chạy liên tục")
        elif state == 0:  # Dừng
            pump_running[index] = False
            GPIO.output(PUMP_PINS[index], GPIO.LOW)
            logging.info(f"Bơm {index + 1} đã dừng")
        else:  # Chạy theo thời gian định sẵn
            run_time = (state / 100) * time_per_pump[index]
                # TIME_PER_100ML_MIK if index == 5 else 
                # TIME_PER_100ML_SUG if index == 4 else 
                # TIME_PER_100ML_1 if index == 0 else
                # TIME_PER_100ML_2 if index == 1 else
                # TIME_PER_100ML_3 if index == 2 else
                # TIME_PER_100ML_4 if index == 3 else
                # TIME_PER_100ML_DEFAULT)
            GPIO.output(PUMP_PINS[index], GPIO.HIGH)
            logging.info(f"Bơm {index + 1} hoạt động {run_time:.2f} giây (Lưu lượng: {state}ml)")
            time.sleep(run_time)
            GPIO.output(PUMP_PINS[index], GPIO.LOW)
    except Exception as e:
        logging.error(f"Lỗi khi điều khiển bơm {index + 1}: {str(e)}")
        GPIO.output(PUMP_PINS[index], GPIO.LOW)  # Đảm bảo tắt bơm khi có lỗi

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
        for pin in PUMP_PINS:
            GPIO.output(pin, GPIO.LOW)
        GPIO.cleanup()

if __name__ == "__main__":
    main()