from flask import Flask, render_template, jsonify
import xml.etree.ElementTree as ET

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('receiveindex.html')

@app.route('/get_received_data')
def get_received_data():
    # Ví dụ đọc từ file XML, bạn có thể thay bằng nguồn dữ liệu thực tế
    filename = 'can_data.xml'
    try:
        tree = ET.parse(filename)
        root = tree.getroot()
        data = []
        for frame in root.findall('Frame'):
            item = {
                'id': frame.find('ID').text,
                'data': frame.find('Data').text
            }
            data.append(item)
        return jsonify(data)
    except Exception:
        return jsonify([])

def decode_uart_frame(frame_bytes):
    """
    Giải mã gói tin UART theo đúng cấu trúc encode_uart_frame:
    [model:1][id:2 hoặc 4][length:1][data:n]
    """
    if len(frame_bytes) < 4:
        return None  # Gói tin không hợp lệ

    model = frame_bytes[0]
    if model == 0:
        id_len = 2
    else:
        id_len = 4

    if len(frame_bytes) < 1 + id_len + 1:
        return None  # Không đủ dữ liệu

    id_bytes = frame_bytes[1:1+id_len]
    id_val = int.from_bytes(id_bytes, 'big')
    id_str = format(id_val, 'X')

    length = frame_bytes[1+id_len]
    data_bytes = frame_bytes[2+id_len:2+id_len+length]
    try:
        data_str = data_bytes.decode('utf-8')
    except Exception:
        data_str = ""

    return {
        'model': model,
        'id': id_str,
        'data': data_str
    }

if __name__ == '__main__':
    app.run(port=5001, debug=True)