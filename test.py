import serial
import time

PORT = 'COM10'   # Thay bằng cổng COM của bạn
BAUDRATE = 115200

def send_std_frame(can_id, data, interval_ms):
    with serial.Serial(PORT, BAUDRATE, timeout=1) as ser:
        frame = bytearray()
        frame.append(0x00)  # model = 0 (standard)
        frame.append((can_id >> 8) & 0xFF)  # ID high byte
        frame.append(can_id & 0xFF)         # ID low byte
        frame.append(len(data))             # length
        frame += bytearray(data)            # data
        frame.append((interval_ms >> 8) & 0xFF)  # interval high byte
        frame.append(interval_ms & 0xFF)         # interval low byte

        ser.write(frame)
        print(f"Sent STD ID: 0x{can_id:X}, LEN: {len(data)}, DATA: {data}, INTERVAL: {interval_ms}ms")

# Gửi ID 0x123, dữ liệu [0x11, 0x22], gửi lặp lại mỗi 1000ms
send_std_frame(0x122, [0x11, 0x22], 1000)