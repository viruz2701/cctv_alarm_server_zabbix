# Alarm Server Makefile

PREFIX ?= /usr/local
CONFIG_DIR = /etc/alarm_receiver
LOG_DIR = /var/log/alarm_receiver
DATA_DIR = /var/lib/alarm_receiver

.PHONY: install uninstall start stop status restart logs test monitor clean

install:
	@echo "Installing Alarm Server..."
	@mkdir -p $(CONFIG_DIR) $(LOG_DIR) $(DATA_DIR)/images
	@cp -r src/* $(PREFIX)/bin/
	@cp scripts/* $(PREFIX)/bin/
	@chmod +x $(PREFIX)/bin/alarm_receiver.py
	@chmod +x $(PREFIX)/bin/alarm-*
	@cp config/alarm-receiver.service /etc/systemd/system/
	@systemctl daemon-reload
	@echo "Installation complete. Edit config: $(CONFIG_DIR)/config.yaml"

uninstall:
	@echo "Uninstalling Alarm Server..."
	@systemctl stop alarm-receiver
	@systemctl disable alarm-receiver
	@rm -f /etc/systemd/system/alarm-receiver.service
	@rm -f $(PREFIX)/bin/alarm_receiver.py
	@rm -f $(PREFIX)/bin/alarm-*
	@rm -rf $(CONFIG_DIR) $(LOG_DIR) $(DATA_DIR)
	@systemctl daemon-reload
	@echo "Uninstall complete"

start:
	@systemctl start alarm-receiver
	@echo "Alarm Server started"

stop:
	@systemctl stop alarm-receiver
	@echo "Alarm Server stopped"

restart:
	@systemctl restart alarm-receiver
	@echo "Alarm Server restarted"

status:
	@systemctl status alarm-receiver --no-pager

logs:
	@tail -f $(LOG_DIR)/receiver.log

monitor:
	@alarm-monitor

test:
	@echo "Running tests..."
	@python3 tests/test_http.py
	@python3 tests/test_private.py
	@python3 tests/test_hisilicon.py

clean:
	@rm -rf $(LOG_DIR)/*.log
	@rm -rf $(DATA_DIR)/images/*
	@echo "Cleaned logs and images"

help:
	@echo "Available commands:"
	@echo "  make install   - Install alarm server"
	@echo "  make uninstall - Uninstall alarm server"
	@echo "  make start     - Start service"
	@echo "  make stop      - Stop service"
	@echo "  make restart   - Restart service"
	@echo "  make status    - Check service status"
	@echo "  make logs      - View logs"
	@echo "  make monitor   - Monitor events in real-time"
	@echo "  make test      - Run tests"
	@echo "  make clean     - Clean logs and images"
