#!/usr/bin/env python3
"""
Universal IP Camera Alarm Receiver for Zabbix
Версия: 5.0 - добавлена поддержка TVT (порт 15003)
"""

import json
import os
import sys
import logging
import subprocess
import http.server
import threading
import queue
import yaml
import re
import socket
import struct
from datetime import datetime
from logging.handlers import RotatingFileHandler

# Импортируем обработчики
from dahua_private import DahuaPrivateHandler
from hisilicon_server import HisiliconServer

# ============================================================================
# КОНФИГУРАЦИЯ
# ============================================================================

CONFIG_FILE = "/etc/alarm_receiver/config.yaml"
ZABBIX_SENDER = "/usr/bin/zabbix_sender"
ZABBIX_SERVER = "192.168.80.7"
ZABBIX_PORT = 10051

# Настройка ротации логов
os.makedirs("/var/log/alarm_receiver", exist_ok=True)
log_handler = RotatingFileHandler(
    '/var/log/alarm_receiver/receiver.log',
    maxBytes=50*1024*1024,
    backupCount=7
)
log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

logging.basicConfig(
    level=logging.INFO,
    handlers=[log_handler, console_handler]
)


# ============================================================================
# TVT ОБРАБОТЧИК
# ============================================================================

class TVTServer:
    """TCP сервер для приёма Alarm от TVT оборудования (порт 15003)"""
    
    def __init__(self, port, message_queue, config):
        self.port = port
        self.queue = message_queue
        self.config = config
        self.running = True
        self.socket = None
    
    def parse_tvt_data(self, data, addr):
        """Парсинг данных от TVT оборудования"""
        result = {
            'raw_hex': data.hex(),
            'raw_text': data.decode('utf-8', errors='ignore'),
            'size': len(data)
        }
        
        # TVT часто использует XML формат
        if b'<' in data and b'>' in data:
            try:
                import xml.etree.ElementTree as ET
                xml_str = data.decode('utf-8', errors='ignore')
                # Очищаем от мусора
                xml_str = re.sub(r'^[^<]*', '', xml_str)
                xml_str = re.sub(r'[^>]*$', '', xml_str)
                root = ET.fromstring(xml_str)
                
                event_type = root.findtext('.//EventType', '')
                event_desc = root.findtext('.//EventDesc', '')
                serial = root.findtext('.//DeviceID', root.findtext('.//SerialNo', 'unknown'))
                
                if event_type:
                    result['xml'] = xml_str
                    result['event_type'] = event_type
                    result['description'] = event_desc
                    result['serial'] = serial
                    result['type'] = 'xml'
            except Exception as e:
                pass
        
        # Поиск JSON
        try:
            start = data.find(b'{')
            if start != -1:
                bracket_count = 0
                end = start
                for i in range(start, len(data)):
                    if data[i] == ord('{'):
                        bracket_count += 1
                    elif data[i] == ord('}'):
                        bracket_count -= 1
                        if bracket_count == 0:
                            end = i + 1
                            break
                if end > start:
                    json_str = data[start:end].decode('utf-8', errors='ignore')
                    json_data = json.loads(json_str)
                    result['json'] = json_data
                    result['event_type'] = json_data.get('Event', json_data.get('event', 'unknown'))
                    result['serial'] = json_data.get('SerialID', json_data.get('serial', 'unknown'))
                    result['type'] = 'json'
        except Exception as e:
            pass
        
        # Поиск простых ASCII строк
        if result['type'] not in ['xml', 'json']:
            ascii_str = re.findall(b'[A-Za-z0-9_\-]{8,}', data)
            if ascii_str:
                result['ascii'] = [s.decode('utf-8', errors='ignore') for s in ascii_str]
                result['type'] = 'ascii'
        
        return result
    
    def handle_connection(self, conn, addr):
        try:
            conn.settimeout(10)
            data = conn.recv(4096)
            
            if data:
                parsed = self.parse_tvt_data(data, addr)
                logging.info(f"TVT from {addr[0]}: {parsed['size']} bytes, type={parsed.get('type', 'unknown')}")
                
                if parsed.get('event_type'):
                    camera_name = f"TVT_{parsed.get('serial', addr[0])}"
                    event_type = parsed['event_type']
                    
                    self.queue.put({
                        'camera': camera_name,
                        'event': event_type,
                        'message': f"{event_type}|{parsed.get('serial', '')}|{addr[0]}",
                        'ip': addr[0],
                        'raw': parsed.get('raw_text', '')[:500],
                        'protocol': 'tvt',
                        'timestamp': datetime.now().isoformat()
                    })
                    
                    logging.info(f"TVT: {camera_name} - {event_type}")
                    conn.send(b'OK')
                else:
                    if parsed['size'] > 20:
                        logging.warning(f"TVT unrecognized from {addr[0]}: {parsed['raw_text'][:100]}")
            
        except socket.timeout:
            pass
        except Exception as e:
            logging.error(f"TVT error: {e}")
        finally:
            conn.close()
    
    def start(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind(('0.0.0.0', self.port))
            self.socket.listen(10)
            logging.info(f"TVT server started on port {self.port}")
            
            while self.running:
                try:
                    conn, addr = self.socket.accept()
                    threading.Thread(target=self.handle_connection, args=(conn, addr), daemon=True).start()
                except Exception as e:
                    if self.running:
                        logging.error(f"TVT accept error: {e}")
        except Exception as e:
            logging.error(f"Failed to start TVT server on port {self.port}: {e}")
        finally:
            if self.socket:
                self.socket.close()
    
    def stop(self):
        self.running = False
        if self.socket:
            self.socket.close()


# ============================================================================
# HTTP ОБРАБОТЧИК
# ============================================================================

class AlarmHTTPHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    
    def log_message(self, format, *args):
        logging.info(f"{self.client_address[0]} - {format % args}")
    
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Alarm Receiver Running\n')
        self.wfile.write(b'Supported endpoints:\n')
        self.wfile.write(b'- POST /dahua\n')
        self.wfile.write(b'- POST /hikvision\n')
        self.wfile.write(b'- POST /tvt\n')
        self.wfile.write(b'\nSupported ports:\n')
        self.wfile.write(b'- TCP 15002 (Hisilicon)\n')
        self.wfile.write(b'- TCP 15003 (TVT)\n')
        self.wfile.write(b'- TCP 37777/37778 (Dahua Private)\n')
    
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8', errors='ignore')
        
        logging.info(f"POST from {self.client_address[0]}: path={self.path}, body={body[:100]}")
        
        camera_name = f"HTTP_{self.client_address[0]}"
        
        cmd = [
            ZABBIX_SENDER, '-z', ZABBIX_SERVER, '-p', str(ZABBIX_PORT),
            '-s', camera_name, '-k', 'alarm.event', '-o', body
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            logging.info(f"Sent to Zabbix: {camera_name}")
        except Exception as e:
            logging.error(f"Failed to send: {e}")
        
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'OK')


# ============================================================================
# ОСНОВНОЙ КЛАСС
# ============================================================================

class AlarmReceiver:
    def __init__(self, config):
        self.config = config
        self.message_queue = queue.Queue()
        
        self.dahua_private_handler = DahuaPrivateHandler(config, self.message_queue)
        self.servers = []
    
    def start_http_server(self, port):
        server = http.server.HTTPServer(('0.0.0.0', port), AlarmHTTPHandler)
        server.timeout = 10
        server.handle_timeout = lambda: None
        
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.servers.append((server, thread))
        logging.info(f"HTTP server started on port {port}")
    
    def start_hisilicon_server(self, port):
        def run_hisilicon():
            server = HisiliconServer(port, self.message_queue, self.config)
            server.start()
        
        thread = threading.Thread(target=run_hisilicon, daemon=True)
        thread.start()
        self.servers.append(thread)
    
    def start_tvt_server(self, port):
        def run_tvt():
            server = TVTServer(port, self.message_queue, self.config)
            server.start()
        
        thread = threading.Thread(target=run_tvt, daemon=True)
        thread.start()
        self.servers.append(thread)
    
    def process_messages(self):
        while True:
            try:
                msg = self.message_queue.get(timeout=1)
                self.send_to_zabbix(msg)
            except queue.Empty:
                continue
    
    def send_to_zabbix(self, msg):
        hostname = msg['camera'].replace(' ', '_').replace('.', '_')[:64]
        value = f"{msg['event']}|{msg.get('status', '')}|{msg.get('message', '')}|{msg.get('ip', '')}"
        
        cmd = [
            ZABBIX_SENDER, '-z', ZABBIX_SERVER, '-p', str(ZABBIX_PORT),
            '-s', hostname, '-k', 'alarm.event', '-o', value
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                logging.info(f"Sent to Zabbix: {hostname} - {msg['event']}")
            else:
                logging.error(f"Zabbix sender error: {result.stderr}")
        except Exception as e:
            logging.error(f"Failed to send: {e}")
    
    def run(self):
        http_port = self.config.get('http', {}).get('port', 8081)
        self.start_http_server(http_port)
        
        # Dahua Private Protocol
        self.dahua_private_handler.start()
        
        # Hisilicon сервер (порт 15002)
        hisilicon_port = self.config.get('hisilicon', {}).get('port', 15002)
        if hisilicon_port:
            self.start_hisilicon_server(hisilicon_port)
        
        # TVT сервер (порт 15003)
        tvt_port = self.config.get('tvt', {}).get('port', 15003)
        if self.config.get('tvt', {}).get('enabled', True) and tvt_port:
            self.start_tvt_server(tvt_port)
        
        self.process_messages()


def load_config():
    default_config = {
        'http': {'port': 8081},
        'dahua_private': {'ports': [37777, 37778]},
        'hisilicon': {'port': 15002},
        'tvt': {'enabled': True, 'port': 15003},
        'zabbix': {
            'server': '192.168.80.7',
            'port': 10051,
            'sender': '/usr/bin/zabbix_sender'
        }
    }
    
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = yaml.safe_load(f)
                if config:
                    for key, value in default_config.items():
                        if key not in config:
                            config[key] = value
                    return config
        except Exception as e:
            logging.error(f"Error loading config: {e}")
    
    return default_config


def main():
    config = load_config()
    
    global ZABBIX_SERVER, ZABBIX_PORT, ZABBIX_SENDER
    ZABBIX_SERVER = config.get('zabbix', {}).get('server', ZABBIX_SERVER)
    ZABBIX_PORT = config.get('zabbix', {}).get('port', ZABBIX_PORT)
    ZABBIX_SENDER = config.get('zabbix', {}).get('sender', ZABBIX_SENDER)
    
    logging.info("Starting Alarm Receiver v5.0 (TVT support added)...")
    logging.info(f"HTTP port: {config['http']['port']}")
    logging.info(f"Dahua Private ports: {config['dahua_private']['ports']}")
    logging.info(f"Hisilicon port: {config['hisilicon']['port']}")
    logging.info(f"TVT port: {config['tvt']['port']}")
    
    receiver = AlarmReceiver(config)
    
    try:
        receiver.run()
    except KeyboardInterrupt:
        logging.info("Shutting down...")
        sys.exit(0)


if __name__ == "__main__":
    main()
