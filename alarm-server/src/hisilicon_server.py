#!/usr/bin/env python3
"""
Hisilicon Camera Alarm Server
Порт: 15002 (по умолчанию)
"""

import socket
import threading
import json
import logging
from datetime import datetime

class HisiliconServer:
    """TCP сервер для приёма Alarm от Hisilicon камер"""
    
    def __init__(self, port, message_queue, config):
        self.port = port
        self.queue = message_queue
        self.config = config
        self.running = True
        self.socket = None
    
    def parse_event(self, data):
        """Парсинг JSON события от Hisilicon камеры"""
        try:
            # Hisilicon отправляет JSON в формате:
            # {"Event":"MotionDetect","SerialID":"XXXXXXXX","Address":...}
            event = json.loads(data)
            
            # Извлекаем IP из Address (hex)
            ip_addr = event.get('Address', '0')
            if ip_addr and ip_addr != '0':
                try:
                    # Конвертируем hex IP (например 0x1704A8C0 -> 192.168.4.23)
                    hex_ip = hex(int(ip_addr))[2:]
                    ip_parts = [str(int(hex_ip[i:i+2], 16)) for i in range(0, len(hex_ip), 2)]
                    ip_addr = '.'.join(reversed(ip_parts))
                except:
                    ip_addr = event.get('ipAddr', 'unknown')
            
            return {
                'type': event.get('Event', 'unknown'),
                'serial': event.get('SerialID', event.get('SerialId', 'unknown')),
                'ip': ip_addr,
                'raw': data,
                'timestamp': datetime.now().isoformat()
            }
        except json.JSONDecodeError:
            return None
        except Exception as e:
            logging.error(f"Hisilicon parse error: {e}")
            return None
    
    def handle_connection(self, conn, addr):
        """Обработка TCP соединения"""
        try:
            conn.settimeout(10)
            data = conn.recv(8192)
            
            if data:
                data_str = data.decode('utf-8', errors='ignore')
                event = self.parse_event(data_str)
                
                if event:
                    camera_name = f"Hisilicon_{event['serial']}"
                    
                    self.queue.put({
                        'camera': camera_name,
                        'event': event['type'],
                        'message': f"{event['type']}|{event['serial']}|{event['ip']}",
                        'ip': addr[0],
                        'raw': data_str,
                        'protocol': 'hisilicon',
                        'timestamp': event['timestamp']
                    })
                    
                    logging.info(f"Hisilicon: {camera_name} - {event['type']}")
            
        except socket.timeout:
            pass
        except Exception as e:
            logging.error(f"Hisilicon connection error: {e}")
        finally:
            conn.close()
    
    def start(self):
        """Запуск TCP сервера"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind(('0.0.0.0', self.port))
            self.socket.listen(10)
            logging.info(f"Hisilicon server started on port {self.port}")
            
            while self.running:
                try:
                    conn, addr = self.socket.accept()
                    thread = threading.Thread(target=self.handle_connection, args=(conn, addr))
                    thread.daemon = True
                    thread.start()
                except Exception as e:
                    if self.running:
                        logging.error(f"Hisilicon accept error: {e}")
                        
        except Exception as e:
            logging.error(f"Failed to start Hisilicon server on port {self.port}: {e}")
        finally:
            if self.socket:
                self.socket.close()
    
    def stop(self):
        """Остановка сервера"""
        self.running = False
        if self.socket:
            self.socket.close()


def send_test_hisilicon(host='127.0.0.1', port=15002):
    """Отправка тестового Hisilicon пакета"""
    import socket
    import json
    
    test_event = {
        "Event": "MotionDetect",
        "SerialID": "TEST_SERIAL_001",
        "Address": "0x1704A8C0",
        "Time": "2026-03-23 06:00:00"
    }
    
    data = json.dumps(test_event)
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((host, port))
        sock.send(data.encode())
        print(f"Test Hisilicon packet sent to {host}:{port}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        sock.close()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        send_test_hisilicon()
    else:
        print("Hisilicon Server Module")
        print("Usage: python3 hisilicon_server.py test")
