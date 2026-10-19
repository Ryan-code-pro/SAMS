
import socket
import time

MULTICAST_GROUP = "239.255.255.250"
PORT = 1900

message = (
    'M-SEARCH * HTTP/1.1\r\n'
    f'HOST: {MULTICAST_GROUP}:{PORT}\r\n'
    'MAN: "ssdp:discover"\r\n'
    'MX: 3\r\n'
    'ST: ssdp:all\r\n'
    '\r\n'
)

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
sock.settimeout(1)

try:
    sock.sendto(message.encode(), (MULTICAST_GROUP, PORT))
    print("Searching for UPnP/SSDP devices for 10 seconds...")

    deadline = time.time() + 10

    while time.time() < deadline:
        try:
            data, address = sock.recvfrom(4096)
            print(f"\nResponse from {address}:")
            print(data.decode(errors="replace"))
        except socket.timeout:
            continue

    print("\nDiscovery finished.")
finally:
    sock.close()
