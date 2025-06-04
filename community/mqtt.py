import paho.mqtt.client as mqtt

# def run_mqtt_client():
# Callback khi kết nối đến MQTT Broker
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Đã kết nối đến MQTT Broker!")
        # Đăng ký theo dõi chủ đề pump/control
        client.subscribe("pump/control")
    else:
        print(f"Kết nối thất bại với mã lỗi {rc}")

# Callback khi nhận được tin nhắn
def on_message(client, userdata, message):
    msg = message.payload.decode("utf-8")
    # print(f"Nhận được tin nhắn từ {message.topic}: {msg}")
    print(f"Nhận được tin nhắn từ App BeTea: {msg}")
    # Lưu tin nhắn vào file
    try:
        with open('app_betea/input/config.txt', 'w') as file:
            file.write(msg)
        # print(f"Đã lưu tin nhắn vào file")
    except Exception as e:
        print(f"Lỗi khi lưu file: {e}")
    
    # Phân tích chuỗi nhận được (vd: "50||100||50||0||0")
    try:
        values = msg.split("||")
        if len(values) >= 5:
            param1 = int(values[0])
            param2 = int(values[1])
            param3 = int(values[2])
            param4 = int(values[3])
            param5 = int(values[4])
            
            # print(f"Tham số 1: {param1}")
            # print(f"Tham số 2: {param2}")
            # print(f"Tham số 3: {param3}")
            # print(f"Tham số 4: {param4}")
            # print(f"Tham số 5: {param5}")
    except Exception as e:
        print(f"Lỗi xử lý tin nhắn: {e}")

# Tạo client MQTT
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

# Địa chỉ MQTT Broker - mặc định localhost, có thể thay đổi nếu broker ở máy khác
mqtt_broker = "localhost"  
mqtt_port = 1883

# Kết nối đến MQTT Broker
try:
    client.connect(mqtt_broker, mqtt_port, 60)
    
    # Bắt đầu vòng lặp để duy trì kết nối và xử lý các callback
    # print(f"Đang kết nối đến {mqtt_broker}:{mqtt_port}")
    client.loop_forever()
    
except KeyboardInterrupt:
    print("Chương trình đã dừng bởi người dùng")
except Exception as e:
    print(f"Lỗi kết nối: {e}")