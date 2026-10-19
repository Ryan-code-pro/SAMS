import time
from threading import Lock

from zeroconf import Zeroconf, ServiceBrowser


SERVICE_TYPES = [
    "_services._dns-sd._udp.local.",
]


class DiscoveryListener:
    def __init__(self, zeroconf):
        self.zeroconf = zeroconf
        self.lock = Lock()
        self.found = {}
        self.browsers = []

    def add_service(self, zeroconf, service_type, name):
        # The meta-service lists service types advertised on the LAN.
        if service_type == "_services._dns-sd._udp.local.":
            info = zeroconf.get_service_info(service_type, name)
            if info is None:
                return

            with self.lock:
                if name in self.found:
                    return
                self.found[name] = True

            print(f"Service type found: {name}")

            # Browse each discovered service type.
            self.browsers.append(
                ServiceBrowser(zeroconf, name, self)
            )
            return

        info = zeroconf.get_service_info(service_type, name)
        if info is None:
            return

        addresses = info.parsed_addresses()

        print("\nDevice service discovered")
        print(f"  Name:    {name}")
        print(f"  Service: {service_type}")
        print(f"  Address: {', '.join(addresses) or 'Not provided'}")
        print(f"  Port:    {info.port}")

    def update_service(self, zeroconf, service_type, name):
        self.add_service(zeroconf, service_type, name)

    def remove_service(self, zeroconf, service_type, name):
        print(f"Service disappeared: {name}")


def main():
    zeroconf = Zeroconf()
    listener = DiscoveryListener(zeroconf)

    try:
        print("SAMS app-side mDNS discovery")
        print("Listening for 20 seconds...")
        print("Ensure your PC is on the same local network.")

        browser = ServiceBrowser(
            zeroconf,
            SERVICE_TYPES[0],
            listener,
        )

        time.sleep(20)

        with listener.lock:
            count = len(listener.found)

        print(f"\nDiscovery finished: {count} service type(s) found.")
        print("Note: this is service discovery, not a count of all devices.")

        browser.cancel()

    except KeyboardInterrupt:
        print("\nDiscovery stopped.")

    finally:
        for browser in listener.browsers:
            browser.cancel()
        zeroconf.close()


if __name__ == "__main__":
    main()