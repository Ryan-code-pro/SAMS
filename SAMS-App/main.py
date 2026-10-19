
import sys
import re
from datetime import datetime
from html import unescape

import requests
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QListWidget,
    QListWidgetItem,
)



class HubWorker(QThread):
    finished_result = Signal(bool, str, dict)

    def __init__(self, ip):
        super().__init__()
        self.ip = ip.rstrip("/")

    def run(self):
        try:
            status_response = requests.get(
                f"http://{self.ip}/api/v1/status",
                timeout=5,
            )
            status_response.raise_for_status()
            status = status_response.json()

            devices_response = requests.get(
                f"http://{self.ip}/api/v1/devices",
                timeout=5,
            )
            devices_response.raise_for_status()
            devices_data = devices_response.json()

            result = {
                "status": status,
                "devices": devices_data.get("devices", []),
            }

            self.finished_result.emit(
                True,
                "Hub API responded successfully",
                result,
            )

        except (requests.RequestException, ValueError) as error:
            self.finished_result.emit(False, str(error), {})

class SAMSApp(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("SAMS | Smart Asset Management System")
        self.resize(820, 650)

        self.setStyleSheet("""
            QWidget {
                background: #0b1020;
                color: #e8edf8;
                font-family: Segoe UI;
                font-size: 14px;
            }
            QLabel#title {
                font-size: 30px;
                font-weight: bold;
                color: #ffffff;
            }
            QLabel#muted {
                color: #94a3b8;
            }
            QLabel#section {
                color: #94a3b8;
                font-size: 11px;
                font-weight: bold;
            }
            QFrame#panel {
                background: #131b2e;
                border: 1px solid #25324a;
                border-radius: 12px;
            }
            QLineEdit {
                background: #0b1020;
                border: 1px solid #35435e;
                border-radius: 7px;
                padding: 10px;
            }
            QPushButton {
                background: #4778e8;
                color: white;
                border: none;
                border-radius: 7px;
                padding: 10px 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #5c89f0;
            }
            QPushButton:disabled {
                background: #34415c;
                color: #9ba8bb;
            }
            QListWidget, QTextEdit {
                background: #0b1020;
                border: 1px solid #25324a;
                border-radius: 8px;
                padding: 8px;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(15)

        title = QLabel("SAMS")
        title.setObjectName("title")

        subtitle = QLabel("SMART ASSET MANAGEMENT SYSTEM")
        subtitle.setObjectName("muted")

        root.addWidget(title)
        root.addWidget(subtitle)

        panel = QFrame()
        panel.setObjectName("panel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 18, 18, 18)
        panel_layout.setSpacing(12)

        section = QLabel("HUB CONNECTION")
        section.setObjectName("section")
        panel_layout.addWidget(section)

        row = QHBoxLayout()
        self.ip_input = QLineEdit("192.168.1.12")
        self.ip_input.setPlaceholderText("Hub IP address")

        self.connect_button = QPushButton("Connect & fetch devices")
        self.connect_button.clicked.connect(self.connect_to_hub)

        row.addWidget(self.ip_input, 1)
        row.addWidget(self.connect_button)
        panel_layout.addLayout(row)

        self.status = QLabel("● Not connected")
        self.status.setStyleSheet("color: #f0b45b;")
        panel_layout.addWidget(self.status)

        root.addWidget(panel)

        devices_heading = QHBoxLayout()
        devices_title = QLabel("DEVICES REPORTED BY HUB")
        devices_title.setObjectName("section")
        devices_heading.addWidget(devices_title)
        devices_heading.addStretch()

        self.device_count = QLabel("0 devices")
        self.device_count.setObjectName("muted")
        devices_heading.addWidget(self.device_count)

        root.addLayout(devices_heading)

        self.device_list = QListWidget()
        self.device_list.setMinimumHeight(140)
        root.addWidget(self.device_list, 1)

        log_heading = QLabel("ACTIVITY LOG")
        log_heading.setObjectName("section")
        root.addWidget(log_heading)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(105)
        root.addWidget(self.log)

        self.write_log("SAMS desktop prototype started.")
        self.write_log("Ready to fetch the hub's current dashboard data.")

    def write_log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log.append(f"[{timestamp}] {message}")

    def connect_to_hub(self):
        ip = self.ip_input.text().strip()

        if not ip:
            self.write_log("Enter the hub IP address.")
            return

        self.connect_button.setEnabled(False)
        self.status.setText("● Connecting...")
        self.status.setStyleSheet("color: #f0b45b;")
        self.write_log(f"Requesting dashboard from {ip}...")

        self.worker = HubWorker(ip)
        self.worker.finished_result.connect(self.on_hub_result)
        self.worker.start()

    
    def on_hub_result(self, success, message, data):
        self.connect_button.setEnabled(True)

        if not success:
            self.status.setText("● API CONNECTION FAILED")
            self.status.setStyleSheet("color: #ff7777;")
            self.write_log(f"API request failed: {message}")
            return

        hub_status = data["status"]
        devices = data["devices"]

        self.status.setText(
            f"● HUB {hub_status.get('status', 'UNKNOWN').upper()}"
        )
        self.status.setStyleSheet(
            "color: #62d995; font-weight: bold;"
        )

        self.device_list.clear()

        for device in devices:
            # Future registered-device records will use this format.
            if isinstance(device, dict):
                label = (
                    device.get("name")
                    or device.get("id")
                    or "Unnamed device"
                )
                details = device.get("type", "Registered device")
                self.device_list.addItem(f"●  {label} — {details}")
            else:
                self.device_list.addItem(f"●  {device}")

        count = len(devices)
        self.device_count.setText(
            f"{count} registered device{'s' if count != 1 else ''}"
        )

        self.write_log("Hub status retrieved through the JSON API.")
        self.write_log(f"Received {count} registered device records.")

        if not devices:
            self.write_log(
                "No device IPs were found in the dashboard HTML."
            )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SAMSApp()
    window.show()
    sys.exit(app.exec())
