# IP Camera Alarm Server for Zabbix

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8%2B-green.svg)](https://www.python.org/)
[![Zabbix](https://img.shields.io/badge/zabbix-6.0%2B-orange.svg)](https://www.zabbix.com/)

Universal Alarm Server for IP cameras that sends events to Zabbix via webhook. 
Works with cameras behind NAT without direct access.

## 🌟 Features

- **Multi-protocol support**: Dahua, Hikvision, Hisilicon, Dahua Private Protocol
- **Works behind NAT**: Cameras initiate connection (push model)
- **Dual server support**: Configure primary and backup servers
- **Image upload**: Receive snapshots via FTP/HTTP
- **Zabbix integration**: Automatic event sending via zabbix_sender
- **Lightweight**: < 50 MB RAM, < 1% CPU
- **Easy configuration**: YAML config file

## 📋 Supported Cameras

| Manufacturer | Protocol | Ports | Events |
|--------------|----------|-------|--------|
| **Dahua** | HTTP / Private | 8081 / 37777 | Motion, Video Loss, HDD, Network |
| **Hikvision** | HTTP | 8081 | Motion, Video Loss, Alarm |
| **Hisilicon** | TCP | 15002 | Motion, Alarm |
| **Generic** | FTP | 2121 | Image upload |

## 🚀 Quick Start

```bash
# Clone repository
git clone https://github.com/yourname/alarm-server.git
cd alarm-server

# Install
sudo make install

# Configure
sudo cp config/config.yaml.example /etc/alarm_receiver/config.yaml
sudo nano /etc/alarm_receiver/config.yaml

# Start
sudo make start

# Check status
make status




