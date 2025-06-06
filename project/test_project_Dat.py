import RPi.GPIO as GPIO
import time
import threading
import pytz
import logging
from datetime import datetime, time as datetime_time
from azure.iot.device import IoTHubDeviceClient, MethodResponse

# Hằng số chuyển đổi: 100ml tương ứng 3 giây
TIME_PER_100ML = 2.7
# Hằng số chuyển đổi: 100ml tương ứng 5 giây
TIME_PER_100ML_special = 3

# Cấu hình chân GPIO cho module relay
RELAY_PINS = [15, 18, 16, 20, 21, 23, 24, 25, 7]  # Chân GPIO kết nối với 5 relay
AGITATOR_PIN = 8  # Chân GPIO kết nối với máy khuấy
# Pin 7: Bơm nhu động
# Pin 8: Máy khuấy.

# Thiết lập logging
LOG_FILE = "app_betea/test/history_Dat.log"
VIETNAM_TZ = pytz.timezone("Asia/Ho_Chi_Minh")
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',)
logging.Formatter.converter = lambda *args: datetime.now(VIETNAM_TZ).timetuple()

# Thiết lập GPIO
GPIO.setmode(GPIO.BCM)
for pin in RELAY_PINS:
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.LOW)  # Ban đầu tắt tất cả relay

# Thay bằng connection string của bạn ở đây
CONNECTION_STRING = "HostName=aicofi-iothub.azure-devices.net;DeviceId=1234567654321;SharedAccessKey=paZqJGqIR9kjg73/gdgIXH89cUdLpdSoizRukJMJ5YU="
# Tạo device client
device_client = IoTHubDeviceClient.create_from_connection_string(CONNECTION_STRING)
# Kết nối tới IoT Hub
print("🔌 Connecting to Azure IoT Hub...")
device_client.connect()

# Hàm xử lý khi có cloud-to-device method được gọi
def method_request_handler(method_request):
    print(f"📨 Received direct method: {method_request.name}")
    print(f"📝 Payload: {method_request.payload}")
    msg= method_request.payload
    if method_request.name == "Agitator":
        if msg == "1":
            # threads = []
            threads.append(run_pump(AGITATOR_PIN, -1))
            logging.info("Máy khấy bắt đầu hoạt động")
            time.sleep(1)
            payload = {"result": True, "message": "Agitator started"}
            status = 200
        elif msg == "0":
            # threads = []
            threads.append(run_pump(AGITATOR_PIN, 0))
            logging.info("Máy khấy đã dừng")
            time.sleep(1)
            payload = {"result": True, "message": "Agitator stopped"}
            status = 200   

    elif method_request.name == "RunAll":
        # Xử lý logic tùy theo method name
        if msg == "#":
            # Chạy tất cả các bơm liên tục
            threads = []
            for i in range(len(RELAY_PINS)):
                threads.append(run_pump(i, -1))  # -1 là chế độ chạy liên tục
            logging.info("Tất cả các bơm đang chạy liên tục")
        time.sleep(1)
        payload = {"result": True, "message": "Run All Done"}
        status = 200

    elif method_request.name == "StopAll":
        if msg == "0":
            # Dừng tất cả các bơm
            threads = []
            for i in range(len(RELAY_PINS)):
                threads.append(run_pump(i, 0))  # 0 là lệnh dừng
            logging.info("Tất cả các bơm đã dừng")
        time.sleep(1)
        payload = {"result": True, "message": "Stop All Done"}
        status = 200

    elif method_request.name == "Pump":
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
        # Nếu muốn báo cáo khi tất cả các bơm hoàn thành:
        for thread in active_threads:
            thread.join()
        # logging.info("Tất cả các bơm đã hoàn thành xong")
        logging.info("Done")
        logging.info("-" * 50)
        time.sleep(1)
        payload = {"result": True, "message": "Pump Done"}
        status = 200  
    else:
        payload = {"result": False, "message": "Method not supported"}
        status = 400

    # Gửi response về cloud
    method_response = MethodResponse.create_from_method_request(method_request, status, payload)
    device_client.send_method_response(method_response)
#đăng kí method handler
device_client.on_method_request_received = method_request_handler

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

def main():
    try:
        logging.info("Khởi động hệ thống")
        while True:
            time.sleep(1)
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