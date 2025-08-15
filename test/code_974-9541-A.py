import RPi.GPIO as GPIO
import paho.mqtt.client as mqtt
import time
import threading
import pytz
import logging
from datetime import datetime, time as datetime_time

# Biến global để lưu giá trị hiện tại
TIME_PER_100ML = 4.08
TIME_PER_100ML_MIK = 5.28
TIME_PER_100ML_SUG = 12.65

# Cấu hình chân GPIO cho module relay
PUMP_PINS = [15, 18, 16, 20, 21, 23]  # Chân GPIO kết nối với 6 relay
CLEAN_PIN = 26

# Cấu hình cho cảm biến lưu lượng nước 974-9541-A
FLOW_SENSOR_PIN = 22  # Chân GPIO cho cảm biến lưu lượng
FLOW_CALIBRATION_FACTOR = 10  # Hệ số hiệu chuẩn (xung/mL) - cần điều chỉnh thực tế

CONFIG_FILE = "app_betea/input/config.txt"
LOG_FILE = "app_betea/output/history.log"
VIETNAM_TZ = pytz.timezone("Asia/Ho_Chi_Minh")

# Biến toàn cục cho cảm biến lưu lượng
flow_pulse_count = 0
flow_rate = 0.0
total_volume = 0.0
flow_lock = threading.Lock()

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
GPIO.setwarnings(False)

# Thiết lập các pin relay
for pin in PUMP_PINS:
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.LOW)  # Ban đầu tắt tất cả relay

GPIO.setup(CLEAN_PIN, GPIO.OUT)
GPIO.output(CLEAN_PIN, GPIO.LOW)  # Ban đầu tắt relay làm sạch

# Thiết lập cảm biến lưu lượng
GPIO.setup(FLOW_SENSOR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# Hàm callback cho cảm biến lưu lượng
def flow_pulse_callback(channel):
    global flow_pulse_count
    with flow_lock:
        flow_pulse_count += 1

# Đăng ký ngắt cho cảm biến lưu lượng
try:
    GPIO.add_event_detect(FLOW_SENSOR_PIN, GPIO.FALLING, callback=flow_pulse_callback, bouncetime=20)
    logging.info("Đã khởi tạo cảm biến lưu lượng 974-9541-A thành công")
except Exception as e:
    logging.error(f"Lỗi khởi tạo cảm biến lưu lượng: {e}")

# Hàm reset bộ đếm lưu lượng
def reset_flow_counter():
    global flow_pulse_count, total_volume
    with flow_lock:
        flow_pulse_count = 0
        total_volume = 0.0

# Hàm tính toán lưu lượng
def calculate_flow_volume():
    global flow_pulse_count, total_volume
    with flow_lock:
        # Tính thể tích dựa trên số xung và hệ số hiệu chuẩn
        total_volume = flow_pulse_count / FLOW_CALIBRATION_FACTOR
        return total_volume

# Hàm điều khiển bơm số 2 với cảm biến lưu lượng
def pump_with_flow_sensor(target_volume_ml):
    """
    Điều khiển bơm số 2 dựa trên cảm biến lưu lượng
    target_volume_ml: Thể tích mục tiêu (mL)
    """
    try:
        # Reset bộ đếm
        reset_flow_counter()
        
        # Bật bơm số 2
        GPIO.output(PUMP_PINS[1], GPIO.HIGH)  # Bơm số 2 là index 1
        logging.info(f"Bơm 2 bắt đầu - Mục tiêu: {target_volume_ml}mL (Dùng cảm biến lưu lượng)")
        
        start_time = time.time()
        max_pump_time = 30  # Giới hạn thời gian tối đa 60 giây để an toàn
        
        while True:
            current_volume = calculate_flow_volume()
            
            # Kiểm tra đã đạt thể tích mục tiêu chưa
            if current_volume >= target_volume_ml:
                break
            
            # Kiểm tra thời gian để tránh bơm quá lâu
            if (time.time() - start_time) > max_pump_time:
                logging.warning(f"Bơm 2 vượt quá thời gian giới hạn. Thể tích đạt được: {current_volume:.1f}mL")
                break
            
            # Nghỉ ngắn để tránh CPU cao
            time.sleep(0.1)
        
        # Tắt bơm
        GPIO.output(PUMP_PINS[1], GPIO.LOW)
        
        # Lấy thể tích cuối cùng
        final_volume = calculate_flow_volume()
        pump_time = time.time() - start_time
        
        with flow_lock:
            final_pulses = flow_pulse_count
        
        logging.info(f"Bơm 2 hoàn thành: {final_volume:.1f}mL ({final_pulses} xung) trong {pump_time:.2f}s")
        
        return final_volume
        
    except Exception as e:
        logging.error(f"Lỗi điều khiển bơm 2 với cảm biến: {e}")
        GPIO.output(PUMP_PINS[1], GPIO.LOW)  # Đảm bảo tắt bơm
        return 0

# Callback khi kết nối đến MQTT Broker
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Đã kết nối đến MQTT Broker!")
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
    if msg == "###":
        # Chạy tất cả các bơm liên tục
        GPIO.output(CLEAN_PIN, GPIO.HIGH)
        logging.info("Relay vệ sinh bật")
        for i in range(len(PUMP_PINS)):
            run_pump(i, -1)
            time.sleep(0.05)
        logging.info("Tất cả các bơm đang chạy liên tục")
    elif msg == "000":
        # Dừng tất cả các bơm
        GPIO.output(CLEAN_PIN, GPIO.LOW)
        logging.info("Relay vệ sinh tắt")
        for i in range(len(PUMP_PINS)):
            run_pump(i, 0)
        logging.info("Tất cả các bơm đã dừng")
    elif msg == "***":
        # Chạy tất cả các bơm song song với thời gian riêng biệt
        logging.info("Ready for business")
        pump_times = [3.0, 4.0, 2.5, 5.0, 3.5, 4.5]
        active_threads = []
        for i in range(len(PUMP_PINS)):
            run_time = pump_times[i]
            thread = threading.Thread(target=pump_with_custom_time, args=(i, run_time))
            thread.daemon = True
            thread.start()
            active_threads.append(thread)
        for thread in active_threads:
            thread.join()

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

# Biến global để điều khiển bơm liên tục
pump_running = [False] * len(PUMP_PINS)

# Hàm chạy máy bơm trong một thread riêng biệt
def pump_thread(index, state):
    try:
        # Nếu là bơm số 2 (index 1) và có thể tích cụ thể
        if index == 1 and state > 0:
            pump_with_flow_sensor(state)  # Sử dụng cảm biến lưu lượng
            return
            
        if state == -1:  # Chạy liên tục
            pump_running[index] = True
            time.sleep(0.01)
            GPIO.output(PUMP_PINS[index], GPIO.HIGH)
            logging.info(f"Bơm {index + 1} bắt đầu chạy liên tục")
            while pump_running[index]:
                time.sleep(0.1)
            GPIO.output(PUMP_PINS[index], GPIO.LOW)
            logging.info(f"Bơm {index + 1} đã dừng chạy liên tục")
        elif state == 0:  # Dừng
            pump_running[index] = False
            GPIO.output(PUMP_PINS[index], GPIO.LOW)
            logging.info(f"Bơm {index + 1} đã dừng")
        else:  # Chạy theo thời gian định sẵn (các bơm khác)
            # if index == 1:
            #     logging.info(f"Bơm 2 bỏ qua - chỉ hoạt động với cảm biến lưu lượng")
            #     return
            
            run_time = (state / 100) * (TIME_PER_100ML_MIK if index == 5 else TIME_PER_100ML_SUG if index == 4 else TIME_PER_100ML)
            GPIO.output(PUMP_PINS[index], GPIO.HIGH)
            logging.info(f"Bơm {index + 1} hoạt động {run_time:.2f} giây (Lưu lượng: {state}ml)")
            time.sleep(run_time)
            GPIO.output(PUMP_PINS[index], GPIO.LOW)
    except Exception as e:
        logging.error(f"Lỗi khi điều khiển bơm {index + 1}: {str(e)}")
        GPIO.output(PUMP_PINS[index], GPIO.LOW)

# Điều khiển bơm bằng cách tạo thread riêng
def run_pump(index, state):
    """Khởi động máy bơm trong một thread riêng"""
    pump_th = threading.Thread(target=pump_thread, args=(index, state))
    pump_th.daemon = True
    pump_th.start()
    return pump_th

# Thêm hàm debug này vào code
def debug_flow_sensor():
    """Hàm debug để kiểm tra cảm biến hoạt động"""
    global flow_pulse_count
    print("=== DEBUG CẢM BIẾN LƯU LƯỢNG ===")
    
    # Reset counter
    reset_flow_counter()
    
    # Bật bơm số 2 trong 5 giây
    GPIO.output(PUMP_PINS[1], GPIO.HIGH)
    print("Bơm 2 đang chạy - theo dõi cảm biến...")
    
    for i in range(50):  # 5 giây, mỗi 0.1s kiểm tra 1 lần
        with flow_lock:
            current_pulses = flow_pulse_count
        print(f"Thời gian: {i*0.1:.1f}s - Xung: {current_pulses}")
        time.sleep(0.1)
    
    # Tắt bơm
    GPIO.output(PUMP_PINS[1], GPIO.LOW)
    
    with flow_lock:
        final_pulses = flow_pulse_count
    
    print(f"=== KẾT QUẢ: {final_pulses} xung trong 5 giây ===")
    if final_pulses == 0:
        print("❌ CẢM BIẾN KHÔNG HOẠT ĐỘNG!")
    else:
        print("✅ Cảm biến hoạt động bình thường")


def main():
    try:
        print("Bắt đầu chương trình điều khiển máy bơm...")
        logging.info("Khởi động hệ thống")
        logging.info("Đã tích hợp cảm biến lưu lượng 974-9541-A cho bơm 2")

        # THÊM DÒNG NÀY ĐỂ TEST CẢM BIẾN
        input("Nhấn Enter để test cảm biến lưu lượng...")
        debug_flow_sensor()
        input("Nhấn Enter để tiếp tục chương trình chính...")

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