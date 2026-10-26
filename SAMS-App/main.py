
import sys
import json
import socket
import subprocess
from pathlib import Path
from datetime import datetime
from ipaddress import ip_address

import requests
from discovery import discover_devices

from PySide6.QtCore import QThread, Signal, Qt, QTime
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QFrame, QListWidget,
    QListWidgetItem, QMessageBox, QStackedWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QComboBox, QTimeEdit,
    QDialog, QDialogButtonBox, QFormLayout, QInputDialog,
    QAbstractItemView
)


APP_DIR = Path(__file__).resolve().parent
SETTINGS_FILE = APP_DIR / "sams_settings.json"
SCHEDULE_FILE = APP_DIR / "sams_schedule.json"

DEFAULT_TV = {
    "name": "Living Room TV",
    "ip": "192.168.1.12",
    "type": "Android TV",
    "services": [],
    "source": "Manually configured",
}


# -------------------- WORKERS --------------------

class DiscoveryWorker(QThread):
    finished_result = Signal(bool, str, list)

    def run(self):
        try:
            devices = discover_devices(duration=6)
            self.finished_result.emit(
                True, f"Discovery finished: {len(devices)} records.", devices
            )
        except Exception as error:
            self.finished_result.emit(False, str(error), [])


class HubWorker(QThread):
    finished_result = Signal(bool, str, dict)

    def __init__(self, host):
        super().__init__()
        self.host = host.strip()

    def run(self):
        try:
            status = requests.get(
                f"http://{self.host}/api/v1/status", timeout=4
            )
            status.raise_for_status()
            self.finished_result.emit(True, "SAMS hub responded.", status.json())
        except Exception as error:
            self.finished_result.emit(False, str(error), {})


class ScheduleUploadWorker(QThread):
    finished_result = Signal(bool, str, dict)

    def __init__(self, host, schedules):
        super().__init__()
        self.host = host.strip()
        self.schedules = json.loads(json.dumps(schedules))

    def run(self):
        base_url = f"http://{self.host}"

        try:
            # The current firmware accepts a JSON array at this endpoint.
            response = requests.post(
                f"{base_url}/api/v1/schedules",
                json=self.schedules,
                timeout=10,
            )
            response.raise_for_status()

            # Fetch the schedule back from the ESP32 for verification.
            verification = requests.get(
                f"{base_url}/api/v1/schedules",
                timeout=8,
            )
            verification.raise_for_status()
            received = verification.json()

            self.finished_result.emit(
                True,
                "Upload request accepted; read-back completed.",
                received,
            )

        except Exception as error:
            self.finished_result.emit(
                False,
                f"Schedule upload or verification failed: {error}",
                {},
            )


class TVPowerWorker(QThread):
    finished_result = Signal(bool, str)

    def __init__(self, host):
        super().__init__()
        self.host = host.strip()

    def run(self):
        script = APP_DIR / "tv_power_test.py"
        if not script.is_file():
            self.finished_result.emit(
                False, "tv_power_test.py was not found."
            )
            return

        python_exe = sys.executable
        if Path(python_exe).name.lower() == "pythonw.exe":
            candidate = Path(python_exe).with_name("python.exe")
            if candidate.exists():
                python_exe = str(candidate)

        try:
            options = {}
            if sys.platform == "win32":
                options["creationflags"] = subprocess.CREATE_NO_WINDOW

            result = subprocess.run(
                [python_exe, str(script), self.host],
                input="YES\n",
                capture_output=True,
                text=True,
                timeout=35,
                cwd=str(APP_DIR),
                check=False,
                **options,
            )

            output = (result.stdout or "").strip()
            errors = (result.stderr or "").strip()
            if errors:
                output = f"{output}\n{errors}".strip()

            self.finished_result.emit(
                result.returncode == 0,
                output or f"Power helper exited with code {result.returncode}.",
            )
        except Exception as error:
            self.finished_result.emit(False, str(error))


# -------------------- SCHEDULE DIALOG --------------------

class AddScheduleDialog(QDialog):
    def __init__(self, device, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add scheduled action")
        self.setMinimumWidth(340)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.device_label = QLabel(device["name"])
        self.ip_label = QLabel(device["ip"])

        self.action = QComboBox()
        self.action.addItems(["Turn ON", "Turn OFF"])

        self.time = QTimeEdit()
        self.time.setDisplayFormat("HH:mm")
        self.time.setTime(QTime.currentTime())

        form.addRow("Device", self.device_label)
        form.addRow("IP address", self.ip_label)
        form.addRow("Action", self.action)
        form.addRow("Time", self.time)
        layout.addLayout(form)

        note = QLabel(
            "This schedule includes the device profile and can be "
            "uploaded to a configured ESP32 hub."
        )
        note.setWordWrap(True)
        note.setObjectName("muted")
        layout.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_schedule(self, device):
        action = "ON" if self.action.currentIndex() == 0 else "OFF"

        profile = {
            "name": device["name"],
            "ip": device["ip"],
            "type": device.get("type", "Network device"),
            "services": device.get("services", []),
            "source": device.get("source", "Unknown"),
        }

        return {
            "device": device["name"],
            "ip": device["ip"],
            "action": action,
            "time": self.time.time().toString("HH:mm"),
            "profile": profile,
        }


# -------------------- MAIN APPLICATION --------------------

class SAMSApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SAMS | Smart Asset Management System")
        self.resize(1120, 760)
        self.setMinimumSize(900, 620)

        self.devices = {}
        self.schedules = []
        self.discovery_worker = None
        self.hub_worker = None
        self.tv_worker = None
        self.upload_worker = None
        self.hub_ip = ""

        self.load_settings()
        self.load_schedule()
        self.apply_theme()

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        header = QHBoxLayout()
        brand = QVBoxLayout()

        title = QLabel("SAMS")
        title.setObjectName("title")
        subtitle = QLabel("SMART ASSET MANAGEMENT SYSTEM")
        subtitle.setObjectName("muted")
        brand.addWidget(title)
        brand.addWidget(subtitle)

        header.addLayout(brand)
        header.addStretch()

        self.hub_status = QLabel("ESP: Not configured")
        self.hub_status.setObjectName("muted")
        header.addWidget(self.hub_status)

        setup_button = QPushButton("ESP Setup")
        setup_button.clicked.connect(self.show_setup)
        header.addWidget(setup_button)

        root.addLayout(header)

        self.pages = QStackedWidget()
        root.addWidget(self.pages, 1)

        self.build_home_page()
        self.build_schedule_page()
        self.build_setup_page()

        if not self.hub_ip:
            self.pages.setCurrentWidget(self.setup_page)
        else:
            self.pages.setCurrentWidget(self.home_page)
            self.hub_status.setText(f"ESP: {self.hub_ip}")

        self.refresh_schedule_table()
        self.log_message("SAMS initialized.")

    # -------------------- THEME --------------------

    def apply_theme(self):
        self.setStyleSheet("""
            QWidget {
                background: #111111;
                color: #f5f5f5;
                font-family: Segoe UI;
                font-size: 14px;
            }
            QLabel#title {
                font-size: 32px;
                font-weight: 800;
                color: #ffffff;
            }
            QLabel#muted { color: #a5a5a5; }
            QLabel#section {
                color: #ff8a24;
                font-size: 12px;
                font-weight: bold;
            }
            QLabel#hero {
                font-size: 25px;
                font-weight: bold;
            }
            QFrame#panel {
                background: #1b1b1b;
                border: 1px solid #343434;
                border-radius: 12px;
            }
            QLineEdit, QComboBox, QTimeEdit {
                background: #101010;
                color: #ffffff;
                border: 1px solid #444444;
                border-radius: 7px;
                padding: 9px;
            }
            QPushButton {
                background: #ff841f;
                color: #111111;
                border: none;
                border-radius: 7px;
                padding: 10px 14px;
                font-weight: bold;
            }
            QPushButton:hover { background: #ffa04d; }
            QPushButton:disabled {
                background: #494949;
                color: #aaaaaa;
            }
            QPushButton#secondary {
                background: #292929;
                color: #f5f5f5;
                border: 1px solid #444444;
            }
            QPushButton#secondary:hover { background: #383838; }
            QListWidget, QTableWidget, QTextEdit {
                background: #101010;
                color: #f5f5f5;
                border: 1px solid #343434;
                border-radius: 8px;
                gridline-color: #333333;
                padding: 5px;
            }
            QHeaderView::section {
                background: #262626;
                color: #ff9a43;
                border: none;
                padding: 9px;
                font-weight: bold;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #292929;
            }
            QListWidget::item:selected {
                background: #49301d;
            }
            QTableWidget::item { padding: 7px; }
        """)

    def panel(self):
        frame = QFrame()
        frame.setObjectName("panel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        return frame, layout

    # -------------------- HOME PAGE --------------------

    def build_home_page(self):
        self.home_page = QWidget()
        layout = QVBoxLayout(self.home_page)
        layout.setSpacing(16)

        hero_panel, hero = self.panel()
        hero.addWidget(QLabel("YOUR DEVICES. YOUR SCHEDULE."))
        description = QLabel(
            "Discover devices on your network and plan automated actions "
            "from one place."
        )
        description.setObjectName("muted")
        description.setWordWrap(True)
        hero.addWidget(description)

        make_button = QPushButton("＋   Make Schedule")
        make_button.setMinimumHeight(52)
        make_button.clicked.connect(self.show_schedule_page)
        hero.addWidget(make_button)
        layout.addWidget(hero_panel)

        row = QHBoxLayout()

        device_panel, device_layout = self.panel()
        device_heading = QLabel("NETWORK DEVICES")
        device_heading.setObjectName("section")
        device_layout.addWidget(device_heading)

        scan_row = QHBoxLayout()
        self.scan_button = QPushButton("Scan Network")
        self.scan_button.clicked.connect(self.scan_network)
        scan_row.addWidget(self.scan_button)

        self.device_count = QLabel("0 devices")
        self.device_count.setObjectName("muted")
        scan_row.addWidget(self.device_count)
        device_layout.addLayout(scan_row)

        self.device_list = QListWidget()
        self.device_list.setMinimumHeight(250)
        device_layout.addWidget(self.device_list)

        hint = QLabel(
            "Use + beside a device to add an action to your schedule."
        )
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        device_layout.addWidget(hint)
        row.addWidget(device_panel, 3)

        right_panel, right_layout = self.panel()
        quick_heading = QLabel("SCHEDULE OVERVIEW")
        quick_heading.setObjectName("section")
        right_layout.addWidget(quick_heading)

        self.schedule_summary = QLabel("No actions scheduled.")
        self.schedule_summary.setWordWrap(True)
        right_layout.addWidget(self.schedule_summary)

        open_schedule = QPushButton("View Schedule")
        open_schedule.clicked.connect(self.show_schedule_page)
        right_layout.addWidget(open_schedule)

        setup = QPushButton("Configure ESP32")
        setup.setObjectName("secondary")
        setup.clicked.connect(self.show_setup)
        right_layout.addWidget(setup)

        right_layout.addStretch()
        row.addWidget(right_panel, 2)
        layout.addLayout(row, 1)

        self.pages.addWidget(self.home_page)

    # -------------------- SCHEDULE PAGE --------------------

    def build_schedule_page(self):
        self.schedule_page = QWidget()
        layout = QVBoxLayout(self.schedule_page)
        layout.setSpacing(12)

        top = QHBoxLayout()
        heading = QLabel("Schedule Builder")
        heading.setObjectName("hero")
        top.addWidget(heading)
        top.addStretch()

        home = QPushButton("← Home")
        home.setObjectName("secondary")
        home.clicked.connect(self.show_home_page)
        top.addWidget(home)
        layout.addLayout(top)

        description = QLabel(
            "Choose a device from the sidebar, add its action, then review "
            "the complete schedule before uploading it to the ESP32."
        )
        description.setObjectName("muted")
        description.setWordWrap(True)
        layout.addWidget(description)

        content = QHBoxLayout()

        sidebar, side_layout = self.panel()
        side_title = QLabel("AVAILABLE DEVICES")
        side_title.setObjectName("section")
        side_layout.addWidget(side_title)

        self.schedule_device_list = QListWidget()
        self.schedule_device_list.setMinimumWidth(260)
        side_layout.addWidget(self.schedule_device_list, 1)

        refresh = QPushButton("Refresh Devices")
        refresh.setObjectName("secondary")
        refresh.clicked.connect(self.scan_network)
        side_layout.addWidget(refresh)

        content.addWidget(sidebar, 1)

        main_panel, main_layout = self.panel()
        table_title = QLabel("PLANNED ACTIONS")
        table_title.setObjectName("section")
        main_layout.addWidget(table_title)

        self.schedule_table = QTableWidget(0, 4)
        self.schedule_table.setHorizontalHeaderLabels(
            ["Device", "IP Address", "Action", "Time"]
        )
        self.schedule_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.schedule_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.schedule_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        main_layout.addWidget(self.schedule_table, 1)

        buttons = QHBoxLayout()

        remove = QPushButton("Remove Selected")
        remove.setObjectName("secondary")
        remove.clicked.connect(self.remove_schedule)
        buttons.addWidget(remove)

        save = QPushButton("Save Schedule")
        save.clicked.connect(self.save_schedule)
        buttons.addWidget(save)

        self.upload_button = QPushButton("Upload to ESP")
        self.upload_button.clicked.connect(self.upload_schedule)
        buttons.addWidget(self.upload_button)

        main_layout.addLayout(buttons)
        content.addWidget(main_panel, 3)

        layout.addLayout(content, 1)
        self.pages.addWidget(self.schedule_page)

    # -------------------- ESP SETUP PAGE --------------------

    def build_setup_page(self):
        self.setup_page = QWidget()
        layout = QVBoxLayout(self.setup_page)
        layout.addStretch()

        panel, form_layout = self.panel()
        panel.setMaximumWidth(600)

        title = QLabel("Connect your SAMS controller")
        title.setObjectName("hero")
        form_layout.addWidget(title)

        info = QLabel(
            "Enter the ESP32 hub's network address. This setting is saved "
            "for future launches. The app verifies the hub API before "
            "allowing schedule uploads."
        )
        info.setObjectName("muted")
        info.setWordWrap(True)
        form_layout.addWidget(info)

        self.setup_ip = QLineEdit(self.hub_ip or "192.168.1.13")
        self.setup_ip.setPlaceholderText("ESP32 hub IP address")
        form_layout.addWidget(QLabel("Controller IP address"))
        form_layout.addWidget(self.setup_ip)

        buttons = QHBoxLayout()

        detect = QPushButton("Discover Network Devices")
        detect.setObjectName("secondary")
        detect.clicked.connect(self.scan_network)
        buttons.addWidget(detect)

        connect = QPushButton("Verify & Continue")
        connect.clicked.connect(self.connect_to_hub)
        buttons.addWidget(connect)

        form_layout.addLayout(buttons)

        self.setup_message = QLabel(
            "Enter the ESP32 address, then verify the connection."
        )
        self.setup_message.setObjectName("muted")
        self.setup_message.setWordWrap(True)
        form_layout.addWidget(self.setup_message)

        back = QPushButton("Continue Without Hub")
        back.setObjectName("secondary")
        back.clicked.connect(self.continue_without_hub)
        form_layout.addWidget(back)

        wrapper = QHBoxLayout()
        wrapper.addStretch()
        wrapper.addWidget(panel)
        wrapper.addStretch()
        layout.addLayout(wrapper)
        layout.addStretch()

        self.pages.addWidget(self.setup_page)

    # -------------------- SETTINGS AND FILES --------------------

    def load_settings(self):
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            self.hub_ip = str(data.get("hub_ip", "")).strip()
        except (OSError, ValueError):
            self.hub_ip = ""

        self.devices[DEFAULT_TV["ip"]] = dict(DEFAULT_TV)

    def save_settings(self):
        data = {"hub_ip": self.hub_ip}
        SETTINGS_FILE.write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )

    def load_schedule(self):
        try:
            data = json.loads(SCHEDULE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                self.schedules = data
        except (OSError, ValueError):
            self.schedules = []

    def save_schedule(self):
        try:
            SCHEDULE_FILE.write_text(
                json.dumps(self.schedules, indent=2),
                encoding="utf-8",
            )
            self.log_message(f"Saved {len(self.schedules)} schedule action(s).")
            QMessageBox.information(
                self, "Schedule saved",
                f"Saved locally to {SCHEDULE_FILE.name}."
            )
        except OSError as error:
            QMessageBox.warning(self, "Save failed", str(error))

    # -------------------- NAVIGATION --------------------

    def show_home_page(self):
        self.pages.setCurrentWidget(self.home_page)
        self.refresh_device_lists()

    def show_schedule_page(self):
        self.pages.setCurrentWidget(self.schedule_page)
        self.refresh_device_lists()
        self.refresh_schedule_table()

    def show_setup(self):
        self.pages.setCurrentWidget(self.setup_page)
        self.setup_ip.setText(self.hub_ip or "192.168.1.13")

    def continue_without_hub(self):
        self.pages.setCurrentWidget(self.home_page)
        self.refresh_device_lists()
        self.log_message("Continuing without a configured ESP32.")

    # -------------------- DEVICE LISTS --------------------

    def refresh_device_lists(self):
        self.device_list.clear()
        self.schedule_device_list.clear()

        for host in sorted(
            self.devices,
            key=lambda value: tuple(int(part) for part in value.split("."))
        ):
            device = self.devices[host]
            name = device["name"]
            label = f"{name}\n{host}  •  {device.get('type', 'Network device')}"

            self.device_list.addItem(QListWidgetItem(label))

            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(5, 4, 5, 4)

            name_label = QLabel(f"{name}\n{host}")
            name_label.setWordWrap(True)
            row_layout.addWidget(name_label, 1)

            plus = QPushButton("+")
            plus.setFixedWidth(38)
            plus.setToolTip(f"Add an action for {name}")
            plus.clicked.connect(
                lambda checked=False, address=host: self.add_schedule(address)
            )
            row_layout.addWidget(plus)

            list_item = QListWidgetItem()
            list_item.setSizeHint(row.sizeHint())
            self.schedule_device_list.addItem(list_item)
            self.schedule_device_list.setItemWidget(list_item, row)

        self.device_count.setText(
            f"{len(self.devices)} device{'s' if len(self.devices) != 1 else ''}"
        )

        if hasattr(self, "schedule_summary"):
            count = len(self.schedules)
            self.schedule_summary.setText(
                f"{count} scheduled action{'s' if count != 1 else ''}."
            )

    def add_device(self, ip, names=None, services=None, source="Discovery"):
        names = names or []
        services = services or []

        existing = self.devices.get(ip, {})
        combined = names + services

        if ip == DEFAULT_TV["ip"]:
            name = DEFAULT_TV["name"]
            device_type = "Android TV"
        elif existing.get("name") and existing.get("source") == "Manual":
            name = existing["name"]
            device_type = existing.get("type", "Network device")
        else:
            name = existing.get("name") or (
                names[0] if names else "Unknown device"
            )
            description = " ".join(combined).lower()

            if any(x in description for x in (
                "android tv", "xstream", "technicolor", "googlecast"
            )):
                device_type = "Android TV"
            elif "printer" in description:
                device_type = "Printer"
            elif "airplay" in description:
                device_type = "Media device"
            else:
                device_type = existing.get("type", "Network device")

        self.devices[ip] = {
            "ip": ip,
            "name": name,
            "type": device_type,
            "services": sorted(set(existing.get("services", []) + services)),
            "source": source,
        }

    # -------------------- NETWORK DISCOVERY --------------------

    def scan_network(self):
        if self.discovery_worker and self.discovery_worker.isRunning():
            return

        self.scan_button.setEnabled(False)
        self.log_message("Scanning network with mDNS and SSDP...")
        self.discovery_worker = DiscoveryWorker()
        self.discovery_worker.finished_result.connect(self.on_discovery_result)
        self.discovery_worker.start()

    def on_discovery_result(self, success, message, results):
        self.scan_button.setEnabled(True)
        self.log_message(message)

        if not success:
            QMessageBox.warning(self, "Discovery failed", message)
            return

        for record in results:
            if not isinstance(record, dict):
                continue

            host = str(record.get("ip", "")).strip()
            try:
                ip_address(host)
            except ValueError:
                continue

            self.add_device(
                host,
                record.get("names", []),
                record.get("services", []),
            )

        self.refresh_device_lists()
        self.log_message(
            f"Device list updated. {len(self.devices)} known address(es)."
        )

    def add_manual_device(self):
        host, ok = QInputDialog.getText(
            self, "Add device", "Device IP address:"
        )
        if not ok:
            return

        host = host.strip()
        try:
            ip_address(host)
        except ValueError:
            QMessageBox.warning(
                self, "Invalid IP", "Enter a valid IPv4 address."
            )
            return

        name, ok = QInputDialog.getText(
            self, "Device name", "Give this device a name:"
        )
        if not ok or not name.strip():
            return

        self.devices[host] = {
            "ip": host,
            "name": name.strip(),
            "type": "Network device",
            "services": [],
            "source": "Manual",
        }
        self.refresh_device_lists()
        self.log_message(f"Added {name.strip()} at {host}.")

    # -------------------- SCHEDULES --------------------

    def add_schedule(self, host):
        device = self.devices.get(host)
        if not device:
            return

        dialog = AddScheduleDialog(device, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self.schedules.append(dialog.get_schedule(device))
        self.refresh_schedule_table()
        self.refresh_device_lists()
        self.log_message(
            f"Scheduled {dialog.action.currentText()} for "
            f"{device['name']} at {dialog.time.time().toString('HH:mm')}."
        )

    def refresh_schedule_table(self):
        if not hasattr(self, "schedule_table"):
            return

        self.schedule_table.setRowCount(0)

        for schedule in sorted(self.schedules, key=lambda x: x.get("time", "")):
            row = self.schedule_table.rowCount()
            self.schedule_table.insertRow(row)

            values = [
                schedule.get("device", "Unknown"),
                schedule.get("ip", ""),
                schedule.get("action", ""),
                schedule.get("time", ""),
            ]
            for column, value in enumerate(values):
                self.schedule_table.setItem(
                    row, column, QTableWidgetItem(str(value))
                )

        if hasattr(self, "schedule_summary"):
            count = len(self.schedules)
            self.schedule_summary.setText(
                f"{count} scheduled action{'s' if count != 1 else ''}."
            )

    def remove_schedule(self):
        row = self.schedule_table.currentRow()
        if row < 0 or row >= self.schedule_table.rowCount():
            QMessageBox.information(
                self, "Select an action", "Select a schedule row to remove."
            )
            return

        ordered = sorted(
            enumerate(self.schedules),
            key=lambda item: item[1].get("time", ""),
        )
        original_index = ordered[row][0]
        removed = self.schedules.pop(original_index)

        self.refresh_schedule_table()
        self.refresh_device_lists()
        self.log_message(
            f"Removed {removed.get('action')} for {removed.get('device')}."
        )

    def upload_schedule(self):
        if not self.hub_ip:
            QMessageBox.warning(
                self,
                "ESP32 not configured",
                "Open ESP Setup and connect to your Wemos first.",
            )
            return

        if not self.schedules:
            QMessageBox.information(
                self, "No schedules",
                "Create at least one scheduled action first.",
            )
            return

        if self.upload_worker and self.upload_worker.isRunning():
            return

        try:
            SCHEDULE_FILE.write_text(
                json.dumps(self.schedules, indent=2),
                encoding="utf-8",
            )
        except OSError as error:
            QMessageBox.warning(self, "Save failed", str(error))
            return

        self.upload_button.setEnabled(False)
        self.log_message(
            f"Uploading {len(self.schedules)} schedule(s) to {self.hub_ip}..."
        )

        self.upload_worker = ScheduleUploadWorker(
            self.hub_ip, self.schedules
        )
        self.upload_worker.finished_result.connect(
            self.on_schedule_upload_result
        )
        self.upload_worker.start()

    def on_schedule_upload_result(self, success, message, received):
        self.upload_button.setEnabled(True)
        self.log_message(message)

        if not success:
            QMessageBox.warning(self, "Upload failed", message)
            return

        if isinstance(received, list):
            received_schedules = received
        elif isinstance(received, dict):
            received_schedules = received.get("schedules", [])
        else:
            received_schedules = []

        expected_count = len(self.schedules)
        received_count = len(received_schedules)

        profiles_present = all(
            isinstance(item, dict) and isinstance(item.get("profile"), dict)
            for item in received_schedules
        )

        details = json.dumps(received, indent=2)

        if received_count == expected_count and profiles_present:
            QMessageBox.information(
                self,
                "SAMS upload verified",
                f"The ESP32 returned {received_count} schedule(s), "
                "including device profiles.\n\n"
                f"Received data:\n{details}",
            )
        else:
            QMessageBox.warning(
                self,
                "Read-back needs attention",
                f"Expected schedules: {expected_count}\n"
                f"Schedules read back: {received_count}\n"
                f"Profiles preserved: {profiles_present}\n\n"
                f"Received data:\n{details}\n\n"
                "The firmware may need updating to preserve device profiles.",
            )

    # -------------------- ESP CONNECTION --------------------

    def connect_to_hub(self):
        host = self.setup_ip.text().strip()

        try:
            ip_address(host)
        except ValueError:
            QMessageBox.warning(
                self, "Invalid address", "Enter a valid ESP32 IPv4 address."
            )
            return

        self.setup_message.setText(f"Checking hub at {host}...")
        self.hub_worker = HubWorker(host)
        self.hub_worker.finished_result.connect(self.on_hub_result)
        self.hub_worker.start()

    def on_hub_result(self, success, message, data):
        if not success:
            self.setup_message.setText(f"Connection failed: {message}")
            self.log_message(f"ESP connection failed: {message}")
            QMessageBox.warning(
                self,
                "Could not connect",
                "The hub did not respond to /api/v1/status.\n\n"
                "Check the IP and ensure the ESP32 is running its hub API.",
            )
            return

        self.hub_ip = self.setup_ip.text().strip()

        try:
            self.save_settings()
        except OSError as error:
            QMessageBox.warning(
                self, "Settings could not be saved", str(error)
            )
            return

        state = data.get("status", "Connected")
        self.hub_status.setText(f"ESP: {self.hub_ip}")
        self.setup_message.setText(f"Connected. Hub status: {state}")
        self.log_message(f"Connected to SAMS hub at {self.hub_ip}.")
        self.pages.setCurrentWidget(self.home_page)

    # -------------------- TV CONTROL --------------------

    def control_tv(self):
        host = DEFAULT_TV["ip"]
        answer = QMessageBox.question(
            self,
            "TV power",
            f"Send a POWER command to {DEFAULT_TV['name']} ({host})?\n\n"
            "POWER may turn the box on or off depending on its state.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.tv_worker = TVPowerWorker(host)
        self.tv_worker.finished_result.connect(self.on_tv_result)
        self.tv_worker.start()
        self.log_message(f"Sending TV power command to {host}...")

    def on_tv_result(self, success, message):
        self.log_message(message)
        if success:
            QMessageBox.information(self, "TV control", message)
        else:
            QMessageBox.warning(self, "TV control failed", message)

    # -------------------- LOG --------------------

    def log_message(self, message):
        print(f"[{datetime.now():%H:%M:%S}] {message}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SAMSApp()
    window.show()
    sys.exit(app.exec())
