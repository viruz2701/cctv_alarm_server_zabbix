#!/usr/bin/env python3
"""
Dahua Private Protocol Handler
Поддержка протокола Dahua (порты 37777, 37778)
Формат: [Header: 0x12,0x34] [Length: 4 bytes] [Data]
"""

import struct
import socket
import threading
import json
import logging
from datetime import datetime

class DahuaPrivateHandler:
    """Обработчик приватного протокола Dahua"""
    
    def __init__(self, config, message_queue):
        self.config = config
        self.queue = message_queue
        self.running = True
        self.servers = []
    
    def parse_packet(self, data):
        """Парсинг пакета приватного протокола"""
        try:
            if len(data) < 6:
                return None
            
            # Проверяем заголовок (0x12, 0x34)
            if data[0] != 0x12 or data[1] != 0x34:
                return None
            
            # Извлекаем длину пакета (4 байта, big-endian)
            packet_len = struct.unpack('>I', data[2:6])[0]
            
            if len(data) < packet_len:
                return None
            
            # Извлекаем полезную нагрузку
            payload = data[6:packet_len]
            
            # Парсим payload (обычно в формате key=value)
            return self.parse_payload(payload)
            
        except Exception as e:
            logging.error(f"Error parsing Dahua private packet: {e}")
            return None
    
    def parse_payload(self, payload):
        """Парсинг полезной нагрузки"""
        try:
            # Пробуем декодировать как строку
            payload_str = payload.decode('utf-8', errors='ignore')
            
            # Формат: Code=VideoMotion&action=Start&index=0&data=...
            event = {}
            for item in payload_str.split('&'):
                if '=' in item:
                    k, v = item.split('=', 1)
                    event[k] = v
            
            # Извлекаем тип события
            event_type = event.get('Code', 'unknown')
            action = event.get('action', '')
            index = event.get('index', '0')
            channel = event.get('channel', index)
            data = event.get('data', '')
            timestamp = event.get('timestamp', datetime.now().strftime('%Y%m%d%H%M%S'))
            
            # Маппинг событий Dahua
            event_map = {
                'VideoMotion': 'Motion Detection',
                'VideoLoss': 'Video Loss',
                'VideoBlind': 'Video Tampering',
                'AlarmLocal': 'Local Alarm',
                'CrossLineDetection': 'Tripwire',
                'RegionDetection': 'Intrusion',
                'FaceDetection': 'Face Detected',
                'HumanDetection': 'Human Detected',
                'VehicleDetection': 'Vehicle Detected',
                'HDDFailure': 'HDD Failure',
                'HDDFull': 'HDD Full',
                'NetworkDisconnect': 'Network Disconnected',
                'TemperatureAlarm': 'Temperature Alarm',
                'FanAlarm': 'Fan Error',
                'StorageFailure': 'Storage Failure'
            }
            
            return {
                'type': event_map.get(event_type, event_type),
                'action': action,
                'index': index,
                'channel': channel,
                'data': data,
                'timestamp': timestamp,
                'raw': payload_str,
                'event_code': event_type
            }
            
        except Exception as e:
            logging.error(f"Error parsing payload: {e}")
            return None
    
    def handle_connection(self, conn, addr):
        """Обработка TCP соединения"""
        try:
            # Устанавливаем таймаут
            conn.settimeout(10)
            
            # Читаем данные
            data = conn.recv(8192)
            if not data:
                return
            
            # Парсим пакет
            event = self.parse_packet(data)
            if event:
                # Формируем имя камеры
                camera_name = f"Dahua_Private_{addr[0]}_{event['channel']}"
                
                # Формируем сообщение
                message = f"{event['type']}|{event['action']}|{event['data']}|{event['event_code']}"
                
                # Отправляем в очередь
                self.queue.put({
                    'camera': camera_name,
                    'event': event['type'],
                    'message': message,
                    'ip': addr[0],
                    'raw': event['raw'],
                    'channel': event['channel'],
                    'timestamp': event['timestamp'],
                    'protocol': 'dahua_private'
                })
                
                logging.info(f"Dahua Private: {camera_name} - {event['type']} ({event['action']})")
            
        except socket.timeout:
            pass
        except Exception as e:
            logging.error(f"Error handling Dahua private connection: {e}")
        finally:
            conn.close()
    
    def start_server(self, port):
        """Запуск TCP сервера на указанном порту"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            sock.bind(('0.0.0.0', port))
            sock.listen(10)
            logging.info(f"Dahua Private protocol server started on port {port}")
            
            while self.running:
                try:
                    conn, addr = sock.accept()
                    thread = threading.Thread(target=self.handle_connection, args=(conn, addr))
                    thread.daemon = True
                    thread.start()
                except Exception as e:
                    logging.error(f"Error accepting connection: {e}")
                    
        except Exception as e:
            logging.error(f"Failed to start Dahua private server on port {port}: {e}")
        finally:
            sock.close()
    
    def start(self):
        """Запуск всех серверов Dahua Private Protocol"""
        ports = self.config.get('dahua_private', {}).get('ports', [37777, 37778])
        
        for port in ports:
            thread = threading.Thread(target=self.start_server, args=(port,))
            thread.daemon = True
            thread.start()
            self.servers.append(thread)
        
        return self.servers
    
    def stop(self):
        """Остановка всех серверов"""
        self.running = False
        for server in self.servers:
            server.join(timeout=1)


# Тестовый клиент для отправки тестовых пакетов
def send_test_packet(host='127.0.0.1', port=37777, event_type='VideoMotion', action='Start', channel=1):
    """Отправка тестового пакета Dahua Private Protocol"""
    import socket
    
    # Формируем payload
    payload_str = f"Code={event_type}&action={action}&index={channel}&channel={channel}&timestamp={datetime.now().strftime('%Y%m%d%H%M%S')}"
    payload = payload_str.encode('utf-8')
    
    # Формируем пакет
    packet = bytearray()
    packet.append(0x12)  # Header byte 1
    packet.append(0x34)  # Header byte 2
    packet.extend(struct.pack('>I', len(payload) + 6))  # Length
    packet.extend(payload)  # Payload
    
    # Отправляем
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((host, port))
        sock.send(packet)
        print(f"Test packet sent to {host}:{port}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        sock.close()

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        send_test_packet()
    else:
        print("Dahua Private Protocol Handler Module")
        print("Usage: python3 dahua_private.py test")
