#!/usr/bin/env python3
"""
Universal IP Camera Alarm Receiver for Zabbix
Версия: 3.1 - с исправленным Hisilicon
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
from datetime import datetime

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

# Настройка логирования
os.makedirs("/var/log/alarm_receiver", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/var/log/alarm_receiver/receiver.log')
    ]
)


# ============================================================================
# HTTP ОБРАБОТЧИК
# ============================================================================

class DahuaAlarmHandler:
    def __init__(self, config, message_queue):
        self.config = config
        self.queue = message_queue
    
    def parse_event(self, data):
        try:
            event = {}
            for item in data.split('&'):
                if '=' in item:
                    k, v = item.split('=', 1)
                    event[k] = v
            return {
                'type': event.get('Code', 'unknown'),
                'action': event.get('action', ''),
                'index': event.get('index', '0'),
                'data': event.get('data', '')
            }
        except:
            return None
    
    def handle_request(self, body, client_ip):
        event = self.parse_event(body)
        if event:
            camera_name = f"Dahua_{client_ip}_{event.get('index', '0')}"
            message = f"{event['type']}|{event['action']}|{event.get('data', '')}"
            self.queue.put({
                'camera': camera_name,
                'event': event['type'],
                'message': message,
                'ip': client_ip,
                'raw': body,
                'protocol': 'http'
            })
            return True
        return False


class HikvisionAlarmHandler:
    def __init__(self, config, message_queue):
        self.config = config
        self.queue = message_queue
    
    def parse_event(self, data):
        try:
            event_type = re.search(r'<eventType>([^<]+)</eventType>', data)
            event_state = re.search(r'<eventState>([^<]+)</eventState>', data)
            event_desc = re.search(r'<eventDescription>([^<]+)</eventDescription>', data)
            channel = re.search(r'<channelID>([^<]+)</channelID>', data)
            
            return {
                'type': event_type.group(1) if event_type else 'unknown',
                'state': event_state.group(1) if event_state else '',
                'description': event_desc.group(1) if event_desc else '',
                'channel': channel.group(1) if channel else '0'
            }
        except:
            return None
    
    def handle_request(self, body, client_ip):
        event = self.parse_event(body)
        if event:
            camera_name = f"Hikvision_{client_ip}_{event['channel']}"
            message = f"{event['type']}|{event['state']}|{event['description']}"
            self.queue.put({
                'camera': camera_name,
                'event': event['type'],
                'message': message,
                'ip': client_ip,
                'raw': body,
                'protocol': 'http'
            })
            return True
        return False


# ============================================================================
# HTTP СЕРВЕР
# ============================================================================

class AlarmHTTPHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    
    def log_message(self, format, *args):
        logging.info(f"{self.client_address[0]} - {format % args}")
    
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8', errors='ignore')
        
        if '/dahua' in self.path.lower() or 'dahua' in body:
            if self.server.dahua_handler.handle_request(body, self.client_address[0]):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'OK')
                return
        
        elif '/hikvision' in self.path.lower() or 'hikvision' in body:
            if self.server.hikvision_handler.handle_request(body, self.client_address[0]):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'OK')
                return
        
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'OK')
    
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Alarm Receiver OK\n\nSupported protocols:\n- HTTP: /dahua, /hikvision\n- TCP: 37777, 37778 (Dahua Private)\n- TCP: 15002 (Hisilicon)')


# ============================================================================
# ОСНОВНОЙ КЛАСС
# ============================================================================

class AlarmReceiver:
    def __init__(self, config):
        self.config = config
        self.message_queue = queue.Queue()
        
        self.dahua_handler = DahuaAlarmHandler(config, self.message_queue)
        self.hikvision_handler = HikvisionAlarmHandler(config, self.message_queue)
        self.dahua_private_handler = DahuaPrivateHandler(config, self.message_queue)
        
        self.servers = []
        self.hisilicon_server = None
    
    def start_http_server(self, port):
        class CustomHTTPHandler(AlarmHTTPHandler):
            pass
        
        server = http.server.HTTPServer(('0.0.0.0', port), CustomHTTPHandler)
        server.dahua_handler = self.dahua_handler
        server.hikvision_handler = self.hikvision_handler
        
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.servers.append((server, thread))
        logging.info(f"HTTP server started on port {port}")
    
    def start_hisilicon_server(self, port):
        """Запуск Hisilicon сервера в отдельном потоке"""
        def run_hisilicon():
            server = HisiliconServer(port, self.message_queue, self.config)
            server.start()
        
        thread = threading.Thread(target=run_hisilicon, daemon=True)
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
        value = f"{msg['event']}|{msg.get('protocol', 'unknown')}|{msg['message']}|{msg['ip']}"
        
        cmd = [
            ZABBIX_SENDER, '-z', ZABBIX_SERVER, '-p', str(ZABBIX_PORT),
            '-s', hostname, '-k', 'alarm.event', '-o', value
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            logging.info(f"Sent to Zabbix: {hostname} - {msg['event']} ({msg.get('protocol', 'http')})")
        except Exception as e:
            logging.error(f"Failed to send to Zabbix: {e}")
    
    def run(self):
        http_port = self.config.get('http', {}).get('port', 8081)
        self.start_http_server(http_port)
        
        # Запускаем Dahua Private Protocol
        self.dahua_private_handler.start()
        
        # Запускаем Hisilicon сервер
        hisilicon_port = self.config.get('hisilicon', {}).get('port', 15002)
        if hisilicon_port:
            self.start_hisilicon_server(hisilicon_port)
        
        # Запускаем обработку сообщений
        self.process_messages()


def load_config():
    default_config = {
        'http': {'port': 8081},
        'dahua_private': {'ports': [37777, 37778]},
        'hisilicon': {'port': 15002},
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
    
    logging.info("Starting Alarm Receiver v3.1...")
    logging.info(f"HTTP port: {config['http']['port']}")
    logging.info(f"Dahua Private ports: {config['dahua_private']['ports']}")
    logging.info(f"Hisilicon port: {config['hisilicon']['port']}")
    
    receiver = AlarmReceiver(config)
    
    try:
        receiver.run()
    except KeyboardInterrupt:
        logging.info("Shutting down...")
        sys.exit(0)


if __name__ == "__main__":
    main()
