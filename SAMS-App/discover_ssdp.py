import socket
import time

MULTICAST_ADDRESS = ("239.255.255.250", 1900)

SEARCH_REQUEST = (
    "M-SEARCH * HTTP/1.1\r\n"
    "HOST: 239.255.255.250:1900\r\n"
    'MAN: "ssdp:discover"\r\n'
    "MX: 3\r\n"
    "ST: ssdp:all\r\n"
    "\r\n"
)


def main():
    found = {}

    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM,
        socket.IPPROTO_UDP,
    )
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.settimeout(1)

    try:
        sock.sendto(
            SEARCH_REQUEST.encode("ascii"),
            MULTICAST_ADDRESS,
        )

        print("SAMS SSDP/UPnP discovery")
        print("Listening for responses for 8 seconds...\n")

        deadline = time.monotonic() + 8

        while time.monotonic() < deadline:
            try:
                data, sender = sock.recvfrom(8192)
            except socket.timeout:
                continue

            response = data.decode("utf-8", errors="replace")
            ip = sender[0]

            # Extract useful response headers.
            headers = {}
            for line in response.splitlines()[1:]:
                if ":" in line:
                    key, value = line.split(":", 1)
                    headers[key.strip().lower()] = value.strip()

            key = (
                ip,
                headers.get("usn", ""),
                headers.get("location", ""),
            )

            if key in found:
                continue

            found[key] = True

            print("Device/service response")
            print(f"  IP:       {ip}")
            print(f"  Server:   {headers.get('server', 'Unknown')}")
            print(f"  Type:     {headers.get('st', 'Unknown')}")
            print(f"  Location: {headers.get('location', 'Not provided')}")
            print()

        print(f"Finished. Received {len(found)} unique response(s).")

        if not found:
            print(
                "No SSDP responses received. "
                "This does not mean the network has no devices."
            )

    except OSError as error:
        print(f"Network error: {error}")

    finally:
        sock.close()


if __name__ == "__main__":
    main()