# Configuration Guide

## Configuration File Location

`/etc/alarm_receiver/config.yaml`

## Full Configuration Example

```yaml
# HTTP Server (for Dahua/Hikvision)
http:
  port: 8081
  debug: false

# Dahua Private Protocol
dahua_private:
  enabled: true
  ports: [37777, 37778]
  debug: false

# Hisilicon Cameras
hisilicon:
  enabled: true
  port: 15002
  debug: false

# FTP Server (for image upload)
ftp:
  enabled: false
  port: 2121
  image_path: "/var/lib/alarm_receiver/images"
  password: "alarm_pass"

# Zabbix Integration
zabbix:
  server: "192.168.80.7"
  port: 10051
  sender: "/usr/bin/zabbix_sender"

# Logging
logging:
  level: "INFO"  # DEBUG, INFO, WARNING, ERROR
  file: "/var/log/alarm_receiver/receiver.log"
