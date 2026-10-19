
import socket
import threading
import time

from zeroconf import Zeroconf, ServiceBrowser, ServiceListener


class DiscoveryResults(ServiceListener):
    """Collect devices advertising services through mDNS/DNS-SD."""

    def __init__(self, results, lock):
        self.results = results
        self.lock = lock

    def add_service(self, zeroconf, service_type, name):
        try:
            info = zeroconf.get_service_info(service_type, name, timeout=1500)
            if not info:
                return

            addresses = [
                socket.inet_ntoa(address)
                for address in info.addresses
                if len(address) == 4
            ]

            with self.lock:
                for ip in addresses:
                    device = self.results.setdefault(
                        ip,
                        {
                            "ip": ip,
                            "names": set(),
                            "services": set(),
                            "sources": set(),
                        },
                    )
                    device["names"].add(name)
                    device["services"].add(service_type)
                    device["sources"].add("mDNS")

        except Exception as error:
            print(f"mDNS service lookup failed: {error}")

    def update_service(self, zeroconf, service_type, name):
        self.add_service(zeroconf, service_type, name)

    def remove_service(self, zeroconf, service_type, name):
        # Keep previously discovered results for this scan.
        pass


def discover_ssdp(results, lock, duration=4):
    """Listen for devices that answer SSDP/UPnP discovery."""

    message = (
        "M-SEARCH * HTTP/1.1\r\n"
        "HOST: 239.255.255.250:1900\r\n"
        'MAN: "ssdp:discover"\r\n'
        "MX: 2\r\n"
        "ST: ssdp:all\r\n\r\n"
    ).encode("ascii")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(0.5)

    try:
        sock.bind(("", 0))
        sock.sendto(message, ("239.255.255.250", 1900))

        deadline = time.monotonic() + duration

        while time.monotonic() < deadline:
            try:
                data, sender = sock.recvfrom(8192)
            except socket.timeout:
                continue

            text = data.decode("utf-8", errors="replace")
            headers = {}

            for line in text.splitlines()[1:]:
                if ":" in line:
                    key, value = line.split(":", 1)
                    headers[key.strip().lower()] = value.strip()

            ip = sender[0]

            with lock:
                device = results.setdefault(
                    ip,
                    {
                        "ip": ip,
                        "names": set(),
                        "services": set(),
                        "sources": set(),
                    },
                )
                device["sources"].add("SSDP")

                if headers.get("server"):
                    device["names"].add(headers["server"])

                if headers.get("st"):
                    device["services"].add(headers["st"])

                if headers.get("location"):
                    device["services"].add(
                        "Description: " + headers["location"]
                    )

    except OSError as error:
        print(f"SSDP discovery error: {error}")

    finally:
        sock.close()


def discover_devices(duration=5):
    """Run mDNS and SSDP discovery and merge results by IP address."""

    results = {}
    lock = threading.Lock()
    zeroconf = Zeroconf()
    listener = DiscoveryResults(results, lock)
    browsers = []

    try:
        # Discover advertised DNS-SD service types.
        browsers.append(
            ServiceBrowser(
                zeroconf,
                "_services._dns-sd._udp.local.",
                listener,
            )
        )

        # Common TV/media service types.
        for service_type in (
            "_googlecast._tcp.local.",
            "_airplay._tcp.local.",
            "_mediaremotetv._tcp.local.",
            "_androidtvremote2._tcp.local.",
            "_http._tcp.local.",
        ):
            browsers.append(
                ServiceBrowser(zeroconf, service_type, listener)
            )

        ssdp_thread = threading.Thread(
            target=discover_ssdp,
            args=(results, lock, duration),
            daemon=True,
        )
        ssdp_thread.start()

        time.sleep(duration)
        ssdp_thread.join(timeout=1)

        with lock:
            output = []

            for device in results.values():
                output.append(
                    {
                        "ip": device["ip"],
                        "names": sorted(device["names"]),
                        "services": sorted(device["services"]),
                        "sources": sorted(device["sources"]),
                    }
                )

            return sorted(output, key=lambda item: item["ip"])

    finally:
        for browser in browsers:
            browser.cancel()
        zeroconf.close()
