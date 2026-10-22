import traceback
import sys
import asyncio
from discovery import discover_devices
import subprocess
from pathlib import Path
from datetime import datetime

import requests
from androidtvremote2 import AndroidTVRemote

from PySide6.QtCore import QThread, Signal
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
    QMessageBox,
)


# -------------------- ESP32 HUB WORKER --------------------

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

            self.finished_result.emit(
                True,
                "Hub API responded successfully",
                {
                    "status": status,
                    "devices": devices_data.get("devices", []),
                },
            )

        except (requests.RequestException, ValueError) as error:
            self.finished_result.emit(False, str(error), {})


# -------------------- ANDROID TV WORKER --------------------

class TVPowerWorker(QThread):
    finished_result = Signal(bool, str)

    def __init__(self, host):
        super().__init__()
        self.host = host

    def run(self):
        script = Path(__file__).resolve().with_name(
            "tv_power_test.py"
        )

        if not script.is_file():
            self.finished_result.emit(
                False,
                f"Power test script not found: {script.name}",
            )
            return

        try:
            result = subprocess.run(
                [sys.executable, str(script), self.host],
                input="YES\n",
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(script.parent),
                check=False,
            )

            output = (result.stdout or "").strip()
            errors = (result.stderr or "").strip()

            if result.returncode == 0:
                self.finished_result.emit(
                    True,
                    output or "TV power script completed.",
                )
            else:
                self.finished_result.emit(
                    False,
                    errors or output or
                    f"Power script exited with code {result.returncode}.",
                )

        except subprocess.TimeoutExpired:
            self.finished_result.emit(
                False,
                "TV power test timed out.",
            )
        except Exception as error:
            self.finished_result.emit(
                False,
                f"{type(error).__name__}: {error}",
            )
# -------------------- NETWORK DEVICE DISCOVERY --------------------

class DiscoveryWorker(QThread):
    finished_result = Signal(bool, str, list)

    def run(self):
        try:
            devices = discover_devices(duration=6)
            self.finished_result.emit(
                True,
                f"Discovery finished: {len(devices)} devices found.",
                devices,
            )
        except Exception as error:
            self.finished_result.emit(
                False,
                f"{type(error).__name__}: {error}",
                [],
            )
class SAMSApp(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("SAMS | Smart Asset Management System")
        self.resize(850, 720)

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

        # Header
        title = QLabel("SAMS")
        title.setObjectName("title")

        subtitle = QLabel("SMART ASSET MANAGEMENT SYSTEM")
        subtitle.setObjectName("muted")

        root.addWidget(title)
        root.addWidget(subtitle)

        # ESP32 hub panel
        hub_panel = QFrame()
        hub_panel.setObjectName("panel")

        hub_layout = QVBoxLayout(hub_panel)
        hub_layout.setContentsMargins(18, 18, 18, 18)
        hub_layout.setSpacing(12)

        hub_heading = QLabel("ESP32 HUB CONNECTION")
        hub_heading.setObjectName("section")
        hub_layout.addWidget(hub_heading)

        hub_row = QHBoxLayout()

        # Change this if your Wemos IP changes.
        self.ip_input = QLineEdit("192.168.1.11")
        self.ip_input.setPlaceholderText("ESP32 hub IP address")

        self.connect_button = QPushButton("Connect & fetch devices")
        self.connect_button.clicked.connect(self.connect_to_hub)

        hub_row.addWidget(self.ip_input, 1)
        hub_row.addWidget(self.connect_button)

        hub_layout.addLayout(hub_row)

        self.status = QLabel("● Not connected")
        self.status.setStyleSheet("color: #f0b45b;")
        hub_layout.addWidget(self.status)

        root.addWidget(hub_panel)

        # Android TV panel
        tv_panel = QFrame()
        tv_panel.setObjectName("panel")

        tv_layout = QVBoxLayout(tv_panel)
        tv_layout.setContentsMargins(18, 18, 18, 18)
        tv_layout.setSpacing(12)

        tv_heading = QLabel("ANDROID TV CONTROL")
        tv_heading.setObjectName("section")
        tv_layout.addWidget(tv_heading)

        tv_description = QLabel(
            "Control your paired XStream Android TV box over Wi-Fi."
        )
        tv_description.setObjectName("muted")
        tv_layout.addWidget(tv_description)

        tv_row = QHBoxLayout()

        self.tv_ip_input = QLineEdit("192.168.1.10")
        self.tv_ip_input.setPlaceholderText("Android TV box IP address")

        self.tv_discover_button = QPushButton("Discover")
        self.tv_discover_button.clicked.connect(self.discover_tv_devices)

        self.tv_power_button = QPushButton("Power toggle")
        self.tv_power_button.clicked.connect(self.toggle_tv_power)

        tv_row.addWidget(self.tv_ip_input, 1)
        tv_row.addWidget(self.tv_discover_button)
        tv_row.addWidget(self.tv_power_button)

        tv_layout.addLayout(tv_row)
        root.addWidget(tv_panel)

        # Device list
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
        self.device_list.setMinimumHeight(110)
        root.addWidget(self.device_list, 1)

        # Activity log
        log_heading = QLabel("ACTIVITY LOG")
        log_heading.setObjectName("section")
        root.addWidget(log_heading)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(110)
        root.addWidget(self.log)

        self.write_log("SAMS desktop prototype started.")
        self.write_log("ESP32 hub and Android TV controls are ready.")

    # -------------------- ACTIVITY LOG --------------------

    def write_log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log.append(f"[{timestamp}] {message}")

    # -------------------- HUB CONNECTION --------------------

    def connect_to_hub(self):
        ip = self.ip_input.text().strip()

        if not ip:
            self.write_log("Enter the ESP32 hub IP address.")
            return

        self.connect_button.setEnabled(False)
        self.status.setText("● Connecting...")
        self.status.setStyleSheet("color: #f0b45b;")

        self.write_log(f"Requesting hub dashboard from {ip}...")

        self.hub_worker = HubWorker(ip)
        self.hub_worker.finished_result.connect(self.on_hub_result)
        self.hub_worker.start()

    def on_hub_result(self, success, message, data):
        self.connect_button.setEnabled(True)

        if not success:
            self.status.setText("● API CONNECTION FAILED")
            self.status.setStyleSheet("color: #ff7777;")
            self.write_log(f"Hub API request failed: {message}")
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
            self.write_log("The hub returned no registered devices.")

    # -------------------- ANDROID TV POWER CONTROL --------------------
        # -------------------- TV DEVICE DISCOVERY --------------------

    def discover_tv_devices(self):
        self.tv_discover_button.setEnabled(False)
        self.write_log("Scanning the network for TV and media devices...")

        self.discovery_worker = DiscoveryWorker()
        self.discovery_worker.finished_result.connect(
            self.on_tv_discovery_result
        )
        self.discovery_worker.start()

    def on_tv_discovery_result(self, success, message, devices):
        self.tv_discover_button.setEnabled(True)
        self.write_log(message)

        if not success:
            self.write_log("Discovery failed.")
            return

        if not devices:
            self.write_log(
                "No advertised devices found. Check that the TV box "
                "is powered and connected to the same network."
            )
            return

        candidates = []

        for device in devices:
            ip = device.get("ip", "")
            names = device.get("names", [])
            services = device.get("services", [])

            description = " ".join(names + services).lower()

            self.write_log(
                f"Found {ip} | "
                f"Names: {', '.join(names) or 'Unknown'} | "
                f"Services: {', '.join(services) or 'None'}"
            )

            # Prefer devices advertising Android TV Remote.
            if "_androidtvremote2._tcp.local." in description:
                candidates.append((3, ip, description))
            elif any(
                word in description
                for word in ("xstream", "technicolor", "android tv")
            ):
                candidates.append((2, ip, description))
            elif "_googlecast._tcp.local." in description:
                candidates.append((1, ip, description))

        if not candidates:
            self.write_log(
                "No confident TV-box match. Check the discovered "
                "device details in the activity log."
            )
            return

        # Prefer Android TV Remote, then matching device names.
        candidates.sort(key=lambda item: item[0], reverse=True)

        best_score = candidates[0][0]
        best_matches = [
            item for item in candidates if item[0] == best_score
        ]

        if len(best_matches) != 1:
            self.write_log(
                "Multiple possible TV boxes found. Keeping the current "
                "IP so the wrong device is not selected."
            )
            return

        discovered_ip = best_matches[0][1]
        self.tv_ip_input.setText(discovered_ip)

        self.write_log(
            f"TV candidate selected: {discovered_ip}"
        )
    def toggle_tv_power(self):
        host = self.tv_ip_input.text().strip()

        if not host:
            self.write_log("Enter the Android TV box IP address.")
            return

        answer = QMessageBox.question(
            self,
            "Confirm power toggle",
            "Send a POWER toggle command to the Android TV box?\n\n"
            "This may turn the box on or off depending on its state. "
            "It may not switch off the physical television.",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            self.write_log("TV power command cancelled.")
            return

        self.tv_power_button.setEnabled(False)
        self.write_log(f"Connecting to Android TV box at {host}...")

        self.tv_worker = TVPowerWorker(host)
        self.tv_worker.finished_result.connect(self.on_tv_power_result)
        self.tv_worker.start()

    def on_tv_power_result(self, success, message):
        self.tv_power_button.setEnabled(True)
        self.write_log(message)

        if success:
            QMessageBox.information(
                self,
                "SAMS",
                "The power command was sent successfully.",
            )
        else:
            QMessageBox.warning(
                self,
                "TV control",
                message,
            )


# -------------------- START APPLICATION --------------------

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SAMSApp()
    window.show()
    sys.exit(app.exec())
