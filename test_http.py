# tests/test_http.py
#!/usr/bin/env python3
"""
Test HTTP Alarm
"""

import requests
import sys

def test_dahua():
    url = "http://localhost:8081/dahua"
    data = "Code=VideoMotion&action=Start&index=1&channel=1"
    
    print("Sending Dahua test alarm...")
    r = requests.post(url, data=data)
    print(f"Response: {r.status_code} - {r.text}")

def test_hikvision():
    url = "http://localhost:8081/hikvision"
    data = """<?xml version="1.0" encoding="UTF-8"?>
<EventNotificationAlert>
    <eventType>VideoMotion</eventType>
    <eventState>active</eventState>
    <channelID>1</channelID>
</EventNotificationAlert>"""
    
    print("Sending Hikvision test alarm...")
    r = requests.post(url, data=data, headers={'Content-Type': 'application/xml'})
    print(f"Response: {r.status_code} - {r.text}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "dahua":
            test_dahua()
        elif sys.argv[1] == "hikvision":
            test_hikvision()
    else:
        test_dahua()
        test_hikvision()
