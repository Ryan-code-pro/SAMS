
from wsdiscovery.discovery import ThreadedWSDiscovery

def main():
    discovery = ThreadedWSDiscovery()
    discovery.start()

    try:
        print("Searching for ONVIF-compatible devices...")
        devices = discovery.searchServices()

        if not devices:
            print("No ONVIF devices discovered.")
            return

        for index, device in enumerate(devices, start=1):
            print(f"\nDevice {index}")
            print("Address:", device.getXAddrs())
            print("Types:", device.getTypes())
            print("Scopes:", device.getScopes())
            print("Endpoint:", device.getEPR())

    except Exception as exc:
        print("Discovery error:", exc)

    finally:
        discovery.stop()

if __name__ == "__main__":
    main()
