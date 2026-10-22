import socket
import ssl

HOST = "192.168.1.10"
PORT = 6466

context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
context.minimum_version = ssl.TLSVersion.TLSv1_2
context.maximum_version = ssl.TLSVersion.TLSv1_2
context.check_hostname = False
context.verify_mode = ssl.CERT_NONE

try:
    with socket.create_connection((HOST, PORT), timeout=5) as sock:
        with context.wrap_socket(sock, server_hostname=HOST) as tls:
            print("TLS connection succeeded")
            print("TLS version:", tls.version())
            print("Cipher:", tls.cipher())
except Exception as exc:
    print(type(exc).__name__ + ":", exc)