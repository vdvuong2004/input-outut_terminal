from flask import Flask, request, jsonify, send_from_directory
import serial
import threading
import time
import xml.etree.ElementTree as ET

app = Flask(__name__, static_url_path='')

ser = None
running = False
send_thread = None

# Hàm mã hóa dữ liệu thành frame UART
def encode_uart_frame(model, id_str, data_str):
    id_val = int(id_str, 16)  # Chuyển ID từ chuỗi hex sang số nguyên

    # Kiểm tra giới hạn ID theo loại frame
    if model == 0 and id_val > 0x7FF:
        raise ValueError("Standard ID must be <= 0x7FF (11-bit)")
    if model == 1 and id_val > 0x1FFFFFFF:
        raise ValueError("Extended ID must be <= 0x1FFFFFFF (29-bit)")

    # Chuyển ID thành bytes: 2 byte nếu Standard, 4 byte nếu Extended
    id_bytes = id_val.to_bytes(4, 'big') if model else id_val.to_bytes(2, 'big')
    # Chuyển data thành bytes (UTF-8)
    data_bytes = data_str.encode('utf-8')
    
    # Nếu data dài quá 256 byte thì cắt bớt
    if len(data_bytes) > 256:
        data_bytes = data_bytes[:256]
    
    # Độ dài data (1 byte)
    length_byte = len(data_bytes).to_bytes(1, 'big')

    # Ghép tất cả thành frame: [model][id][length][data]
    frame = bytes([model]) + id_bytes + length_byte + data_bytes
    return frame

@app.route('/')
def index():
    return send_from_directory('templates', 'index.html')

@app.route('/send', methods=['POST'])
def send():
    global ser, running
    try:
        data = request.json
        print("Received data:", data)
        model = data['model']
        id_str = data['id']
        data_str = data['data']
        mode = data['mode']
        cyclics = float(data['cyclics']) / 1000.0
        baudrate = int(data['baudrate'])

        frame = encode_uart_frame(model, id_str, data_str)
        print("Frame to send:", frame)

        if ser is None or not ser.is_open or ser.baudrate != baudrate:
            if ser:
                ser.close()
            ser = serial.Serial('COM6', baudrate, timeout=1)

        if cyclics == 0:
            ser.write(frame)
        else:
            def loop_send():
                global running
                while running:
                    ser.write(frame)
                    time.sleep(cyclics)
            running = True
            threading.Thread(target=loop_send, daemon=True).start()

        return jsonify({'status': 'started'})
    except Exception as e:
        print("Send error:", e)
        return jsonify({'error': str(e)}), 500

@app.route('/send_all', methods=['POST'])
def send_all():
    global ser
    data = request.json
    rows = data['list']
    mode = data['mode']
    cyclics = data['cyclics'] / 1000.0
    baudrate = data['baudrate']

    if ser is None or not ser.is_open or ser.baudrate != baudrate:
        if ser:
            ser.close()
        ser = serial.Serial('COM6', baudrate, timeout=1)

    def loop():
        for row in rows:
            frame = encode_uart_frame(row['model'], row['id'], row['data'])
            ser.write(frame)
            time.sleep(cyclics)

    threading.Thread(target=loop).start()
    return jsonify({'status': 'sending all'})

@app.route('/stop')
def stop():
    global running
    running = False
    if ser:
        ser.write(b'\xFF')  # Tín hiệu dừng
    return jsonify({'status': 'stopped'})

@app.route('/stop_frame', methods=['POST'])
def stop_frame():
    global running
    running = False
    return jsonify({'status': 'stopped'})

@app.route('/add', methods=['POST'])
def save_to_xml(filename='can_data.xml'):
    data = request.json

    # Nếu file đã tồn tại, đọc và thêm Frame mới
    try:
        tree = ET.parse(filename)
        root = tree.getroot()
    except (FileNotFoundError, ET.ParseError):
        root = ET.Element('CANData')
        tree = ET.ElementTree(root)

    frame = ET.SubElement(root, 'Frame')
    ET.SubElement(frame, 'Model').text = str(data['model'])
    ET.SubElement(frame, 'ID').text = data['id']
    ET.SubElement(frame, 'Data').text = data['data']
    ET.SubElement(frame, 'Description').text = data.get('description', '')
    ET.SubElement(frame, 'Mode').text = str(data['mode'])
    ET.SubElement(frame, 'Cyclics').text = str(data['cyclics'])
    ET.SubElement(frame, 'Baudrate').text = str(data['baudrate'])

    tree.write(filename, encoding='utf-8', xml_declaration=True)
    return jsonify({'status': 'added'})

@app.route('/get_data', methods=['GET'])
def get_data():
    filename = 'can_data.xml'
    try:
        tree = ET.parse(filename)
        root = tree.getroot()
        data = []
        for frame in root.findall('Frame'):
            item = {
                'model': frame.find('Model').text,
                'id': frame.find('ID').text,
                'data': frame.find('Data').text,
                'description': frame.find('Description').text if frame.find('Description') is not None else '',
                'mode': frame.find('Mode').text,
                'cyclics': frame.find('Cyclics').text,
                'baudrate': frame.find('Baudrate').text
            }
            data.append(item)
        return jsonify(data)
    except Exception as e:
        return jsonify([])

@app.route('/delete', methods=['POST'])
def delete_from_xml():
    filename = 'can_data.xml'
    req = request.json
    id_to_delete = req.get('id')
    model_to_delete = str(req.get('model'))
    data_to_delete = req.get('data')
    description_to_delete = req.get('description', '')

    try:
        tree = ET.parse(filename)
        root = tree.getroot()
        removed = False
        for frame in root.findall('Frame'):
            if (frame.find('ID').text == id_to_delete and
                frame.find('Model').text == model_to_delete and
                frame.find('Data').text == data_to_delete and
                (frame.find('Description').text if frame.find('Description') is not None else '') == description_to_delete):
                root.remove(frame)
                removed = True
                break
        if removed:
            tree.write(filename, encoding='utf-8', xml_declaration=True)
            return jsonify({'status': 'deleted'})
        else:
            return jsonify({'status': 'not found'}), 404
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/delete_all', methods=['POST'])
def delete_all():
    filename = 'can_data.xml'
    try:
        # Tạo lại file với root rỗng
        root = ET.Element('CANData')
        tree = ET.ElementTree(root)
        tree.write(filename, encoding='utf-8', xml_declaration=True)
        return jsonify({'status': 'all deleted'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
