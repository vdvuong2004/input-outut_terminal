from flask import Flask, request, jsonify, send_from_directory, send_file, render_template
import serial
import threading
import time 
import xml.etree.ElementTree as ET
from datetime import datetime
import os
import queue
import re
app = Flask(__name__, static_url_path='')

ser = None
running = False
send_thread = None

# Thêm queue để lưu các frame nhận được
receive_queue = queue.Queue(maxsize=1000)  # Giới hạn tối đa 1000 frame
from serial.tools import list_ports
print([p.device for p in list_ports.comports()])
# Đường dẫn tới file XML
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
XML_FILE = os.path.join(BASE_DIR, 'can_data1.xml')

# Thread đọc dữ liệu từ serial và lưu vào receive_queue
def serial_receive_thread():
    global ser
    while True:
        if ser and ser.is_open:
            try:
                line = ser.readline()
                if line:
                    try:
                        decoded = line.decode(errors='ignore').strip()
                        match = re.match(r'ID:\s*0x([0-9A-Fa-f]+)\s*\[(Std|Ext)\],\s*Data:\s*([\dA-Fa-f\s]+)', decoded)
                        if match:
                            id_str = match.group(1)  # Lấy ID không có 0x
                            model = match.group(2)    # Std hoặc Ext
                            data_str = match.group(3).replace(" ", "").strip()  # Lấy dữ liệu, loại bỏ khoảng trắng
                            # timestamp dạng string
                            now = datetime.now()
                            timestamp_str = now.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]  # lấy đến mili giây
                            unix_ts = round(now.timestamp() * 1000)  # đơn vị: mili giây
                            # Định dạng lại dữ liệu trước khi đưa vào queue
                            receive_queue.put({
                                'timestamp': timestamp_str,
                                'unixtimestamp': unix_ts,
                                'id': id_str,
                                'data': data_str, 
                                'model': model
                            })
                    except Exception as e:
                        print(f"Parse error: {e}")
            except Exception as e:
                time.sleep(0.1)
        else:
            time.sleep(0.5)

# Khởi động thread nhận dữ liệu khi app chạy lần đầu

@app.before_request
def start_receive_thread():
    if not hasattr(app, 'thread_started'):
        t = threading.Thread(target=serial_receive_thread, daemon=True)
        t.start()
        app.thread_started = True

@app.route('/get_received_data')
def get_received_data():
    # Lấy đường dẫn tuyệt đối tới file can_dict.xml
    current_dir = os.path.dirname(os.path.abspath(__file__))
    xml_path = os.path.join(current_dir, 'can_dict.xml')

    # Đọc ánh xạ id -> Description từ can_dict.xml
    desc_map = {}
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        for frame in root.findall('Frame'):
            id_val = frame.find('ID').text.strip()
            desc = frame.find('Description').text if frame.find('Description') is not None else ""
            desc_map[id_val.upper()] = desc
    except Exception as e:
        print("Lỗi khi đọc can_dict.xml:", e)

    # Lấy danh sách frame nhận được
    frames = list(receive_queue.queue)

    # Thêm Description vào từng frame dựa theo id
    for f in frames:
        # Chuẩn hóa ID: loại bỏ số 0 ở đầu và chuyển về in hoa
        normalized_id = f['id'].lstrip('0').upper()
        if normalized_id == '':
            normalized_id = '0'
        f['description'] = desc_map.get(normalized_id, "")
    return jsonify(frames)

def encode_uart_frame(model, id_str, data_str, cyclics):
    id_val = int(id_str, 16)  # Chuyển ID từ chuỗi hex sang số nguyên

    # Kiểm tra giới hạn ID theo loại frame
    if model == 0 and id_val > 0x7FF:
        raise ValueError("Standard ID must be <= 0x7FF (11-bit)")
    if model == 1 and id_val > 0x1FFFFFFF:
        raise ValueError("Extended ID must be <= 0x1FFFFFFF (29-bit)")

    # Chuyển ID thành bytes: 2 byte nếu Standard, 4 byte nếu Extended
    id_bytes = id_val.to_bytes(4, 'big') if model else id_val.to_bytes(2, 'big')
    # data_bytes = data_str.encode('utf-8')
    # Chuyển data thành bytes (hex)
    try:
        data_bytes = bytes.fromhex(data_str)
    except Exception:
        data_bytes = b''

    # Nếu data dài quá 256 byte thì cắt bớt
    if len(data_bytes) > 256:
        data_bytes = data_bytes[:256]
    
    # Độ dài data (1 byte)
    length_byte = len(data_bytes).to_bytes(1, 'big')

    # Cyclics (2 byte, giá trị 0-10000 ms, nếu lớn hơn thì lấy 10000)
    try:
        cyclics_int = int(float(cyclics))
    except Exception:
        cyclics_int = 0
    if cyclics_int < 0:
        cyclics_int = 0
    if cyclics_int > 10000:
        cyclics_int = 10000
    cyclics_bytes = cyclics_int.to_bytes(2, 'big')

    # Ghép tất cả thành frame: [model][id][length][cyclics(2 bytes)][data]
    frame = bytes([model]) + id_bytes + length_byte + data_bytes + cyclics_bytes
    return frame

@app.route('/')
def index():
    try:
        # Đọc dữ liệu từ XML khi load trang
        tree = ET.parse(XML_FILE)
        root = tree.getroot()
        initial_data = []
        for frame in root.findall('Frame'):
            item = {
                'id': frame.find('ID').text,
                'data': frame.find('Data').text,
                'model': 'Standard' if frame.find('Model').text == '0' else 'Extended',
                'description': frame.find('Description').text if frame.find('Description') is not None else '',
                'cyclics': frame.find('Cyclics').text,
                'baudrate': frame.find('Baudrate').text
            }
            initial_data.append(item)
        return render_template('index.html', initial_data=initial_data)
    except Exception as e:
        print(f"Error loading XML: {e}")
        return render_template('index.html', initial_data=[])

@app.route('/send', methods=['POST'])
def send():
    global ser
    if ser is None or not ser.is_open:
        return jsonify({'error': 'Serial not connected'}), 400
    try:
        data = request.json
        print("Received data:", data)
        model = int(data['model'])
        id_str = data['id']
        data_str = data['data']
        cyclics = data.get('cyclics', 0)
        baudrate = int(data['baudrate'])

        frame = encode_uart_frame(model, id_str, data_str, cyclics)
        print("Frame to send:", frame)

        if ser is None or not ser.is_open or ser.baudrate != baudrate:
            if ser:
                ser.close()
            ser = serial.Serial('com16', baudrate = baudrate, timeout=1)

        ser.write(frame)

        return jsonify({'status': 'sent'})
    except Exception as e:
        print("Send error:", e)
        return jsonify({'error': str(e)}), 500

@app.route('/add', methods=['POST'])
def save_to_xml(filename=XML_FILE):
    data = request.json

    # Nếu file đã tồn tại, đọc và thêm Frame mới
    try:
        tree = ET.parse(filename)
        root = tree.getroot()
    except (FileNotFoundError, ET.ParseError):
        root = ET.Element('CANData')
        tree = ET.ElementTree(root)

    # Kiểm tra trùng IDAdd commentMore actions
    for frame in root.findall('Frame'):
        if frame.find('ID').text == data['id']:
            return jsonify({'error': 'ID already exists'}), 400

    frame = ET.SubElement(root, 'Frame')
    ET.SubElement(frame, 'Model').text = str(data['model'])
    ET.SubElement(frame, 'ID').text = data['id']
    ET.SubElement(frame, 'Data').text = data['data']
    ET.SubElement(frame, 'Description').text = data.get('description', '')
    ET.SubElement(frame, 'Cyclics').text = str(data['cyclics'])
    ET.SubElement(frame, 'Baudrate').text = str(data['baudrate'])

    tree.write(filename, encoding='utf-8', xml_declaration=True)
    return jsonify({'status': 'added'})

@app.route('/get_data', methods=['GET'])
def get_data():
    filename = XML_FILE
    try:
        tree = ET.parse(filename)
        root = tree.getroot()
        data = []
        for frame in root.findall('Frame'):
            item = {
                'id': frame.find('ID').text,
                'data': frame.find('Data').text,
                'model': frame.find('Model').text,
                'description': frame.find('Description').text if frame.find('Description') is not None else '',
                'cyclics': frame.find('Cyclics').text if frame.find('Cyclics') is not None else '',
                'baudrate': frame.find('Baudrate').text if frame.find('Baudrate') is not None else ''
            }
            data.append(item)
        return jsonify(data)
    except Exception as e:
        return jsonify([])

@app.route('/delete', methods=['POST'])
def delete_from_xml():
    filename = XML_FILE
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
    filename = XML_FILE
    try:
        # Tạo lại file với root rỗng
        root = ET.Element('CANData')
        tree = ET.ElementTree(root)
        tree.write(filename, encoding='utf-8', xml_declaration=True)
        return jsonify({'status': 'all deleted'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/export_xml', methods=['GET'])
def export_xml():
    filename = XML_FILE
    if os.path.exists(filename):
        return send_file(filename, as_attachment=True)
    else:
        return jsonify({'error': 'File not found'}), 404

@app.route('/import_xml', methods=['POST'])
def import_xml():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    file.save(XML_FILE)
    return jsonify({'status': 'imported'})


from serial.tools import list_ports
@app.route('/connect_serial', methods=['POST'])
def connect_serial():
    global ser
    data = request.json
    port = data.get('port', 'com16')
    baudrate = int(data.get('baudrate', 115200))
    print(f"Trying to connect to port: {port} with baudrate: {baudrate}")

    available_ports = [p.device for p in list_ports.comports()]
    print(f"Available ports: {available_ports}")
    if port not in available_ports:
        return jsonify({'status': 'error', 'message': f'Port {port} not found. Available: {available_ports}'}), 500

    try:
        if ser and ser.is_open:
            ser.close()
        ser = serial.Serial(port, baudrate=baudrate, timeout=1)
        print(f"Connected to {port} successfully")
        return jsonify({'status': 'connected'})
    except Exception as e:
        import traceback
        print("Error connecting serial:", e)
        print(traceback.format_exc())
        return jsonify({'status': 'error', 'message': str(e), 'trace': traceback.format_exc()}), 500

@app.route('/disconnect_serial', methods=['POST'])
def disconnect_serial():
    global ser
    try:
        if ser and ser.is_open:
            ser.close()
        ser = None
        return jsonify({'status': 'disconnected'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)

