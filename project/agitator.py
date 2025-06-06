import RPi.GPIO as GPIO
import time
import logging
from azure.iot.device import IoTHubDeviceClient, MethodResponse

# Cấu hình GPIO cho động cơ
MOTOR_PIN = 21  # Thay đổi số pin GPIO phù hợp với setup của bạn

# Thiết lập logging
logging.basicConfig(
    filename="app_betea/project/agitator_history.log",
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S')

# Thiết lập GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(MOTOR_PIN, GPIO.OUT)
GPIO.output(MOTOR_PIN, GPIO.LOW)  # Tắt động cơ khi khởi động

# Connection string từ Azure IoT Hub
CONNECTION_STRING = "HostName=aicofi-iothub.azure-devices.net;DeviceId=1234567654321;SharedAccessKey=paZqJGqIR9kjg73/gdgIXH89cUdLpdSoizRukJMJ5YU="
device_client = IoTHubDeviceClient.create_from_connection_string(CONNECTION_STRING)

def method_request_handler(method_request):
    print(f"Nhận lệnh: {method_request.name}")
    print(f"Giá trị: {method_request.payload}")
    
    if method_request.name == "Agitator":
        msg = method_request.payload
        if msg == "ON":
            GPIO.output(MOTOR_PIN, GPIO.HIGH)
            logging.info("Động cơ đã BẬT")
            print("Máy khuấy bắt đầu hoạt động")
            payload = {"result": True, "message": "Motor turned ON"}
            status = 200
        elif msg == "OFF":
            GPIO.output(MOTOR_PIN, GPIO.LOW)
            logging.info("Động cơ đã TẮT")
            print("Máy khuấy đã dừng")
            payload = {"result": True, "message": "Motor turned OFF"}
            status = 200
        else:
            payload = {"result": False, "message": "Invalid command"}
            status = 400
    else:
        payload = {"result": False, "message": "Method not supported"}
        status = 400

    # Gửi phản hồi về cloud
    method_response = MethodResponse.create_from_method_request(method_request, status, payload)
    device_client.send_method_response(method_response)

def main():
    try:
        print("🔌 Đang kết nối tới Azure IoT Hub...")
        device_client.connect()
        device_client.on_method_request_received = method_request_handler
        
        logging.info("Hệ thống đã khởi động")
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nĐang dừng chương trình...")
        logging.info("Hệ thống đã dừng")
    except Exception as e:
        logging.error(f"Lỗi: {str(e)}")
        print(f"Lỗi: {str(e)}")
    finally:
        GPIO.output(MOTOR_PIN, GPIO.LOW)  # Đảm bảo tắt động cơ
        GPIO.cleanup()
        device_client.disconnect()

if __name__ == "__main__":
    main()