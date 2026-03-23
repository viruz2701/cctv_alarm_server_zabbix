# Installation Guide

## Prerequisites

- Ubuntu 22.04/24.04 or Debian 11/12
- Python 3.8+
- Zabbix Server 6.0+ (for receiving events)
- Root access

## Step 1: Download and Install

```bash
# Clone repository
git clone https://github.com/yourname/alarm-server.git
cd alarm-server

# Install dependencies
sudo apt update
sudo apt install -y python3-pip python3-yaml tcpdump
sudo pip3 install pyyaml

# Install alarm server
sudo make install

# Copy example config
sudo cp config/config.yaml.example /etc/alarm_receiver/config.yaml

# Edit configuration
sudo nano /etc/alarm_receiver/config.yaml


# Start service
sudo make start

# Check status
sudo make status

# Send test event
make test

# Check logs
sudo make logs

# Monitor events
sudo make monitor

sudo make uninstall


#Debug Mode
#Enable debug to see detailed packet information:

http:
  debug: true
dahua_private:
  debug: true
logging:
  level: "DEBUG"
sudo systemctl restart alarm-receiver
tail -f /var/log/alarm_receiver/receiver.log



