
#include <Arduino.h>
#include <WiFi.h>
#include <ESP32Ping.h>

const char* WIFI_SSID = "Kartik";
const char* WIFI_PASSWORD = "9412291479";

WiFiServer server(80);

const int FIRST_HOST = 1;
const int LAST_HOST = 254;
const int MAX_DEVICES = LAST_HOST - FIRST_HOST + 1;

struct Device {
    IPAddress ip;
    bool reachable;
};

Device devices[MAX_DEVICES];
int deviceCount = 0;


void scanDevices() {
    IPAddress localIP = WiFi.localIP();
    IPAddress subnet = WiFi.subnetMask();

    // Calculate the network and broadcast addresses.
    uint32_t ipValue =
        ((uint32_t)localIP[0] << 24) |
        ((uint32_t)localIP[1] << 16) |
        ((uint32_t)localIP[2] << 8) |
        (uint32_t)localIP[3];

    uint32_t maskValue =
        ((uint32_t)subnet[0] << 24) |
        ((uint32_t)subnet[1] << 16) |
        ((uint32_t)subnet[2] << 8) |
        (uint32_t)subnet[3];

    uint32_t networkValue = ipValue & maskValue;
    uint32_t broadcastValue = networkValue | (~maskValue);

    uint32_t hostCount = broadcastValue - networkValue - 1;

    // Avoid impractically large network scans.
    if (hostCount == 0 || hostCount > 1022) {
        Serial.println("Subnet too large or invalid for this scan.");
        return;
    }

    deviceCount = 0;

    Serial.println("\n--- SAMS Automatic Network Discovery ---");
    Serial.print("ESP32 IP: ");
    Serial.println(localIP);
    Serial.print("Subnet Mask: ");
    Serial.println(subnet);
    Serial.print("Network Address: ");

    Serial.println(IPAddress(
        (networkValue >> 24) & 255,
        (networkValue >> 16) & 255,
        (networkValue >> 8) & 255,
        networkValue & 255
    ));

    Serial.print("Broadcast Address: ");
    Serial.println(IPAddress(
        (broadcastValue >> 24) & 255,
        (broadcastValue >> 16) & 255,
        (broadcastValue >> 8) & 255,
        broadcastValue & 255
    ));

    Serial.print("Scanning ");
    Serial.print(hostCount);
    Serial.println(" possible host addresses...");

    for (uint32_t host = networkValue + 1;
         host < broadcastValue;
         host++) {

        IPAddress target(
            (host >> 24) & 255,
            (host >> 16) & 255,
            (host >> 8) & 255,
            host & 255
        );

        if (target == localIP) {
            continue;
        }

        Serial.print("Checking ");
        Serial.println(target);

        bool replied = Ping.ping(target, 1);

        if (replied && deviceCount < MAX_DEVICES) {
            devices[deviceCount].ip = target;
            devices[deviceCount].reachable = true;
            deviceCount++;

            Serial.println("  ICMP reply received");
        }

        yield();
    }

    Serial.print("Devices replying to ping: ");
    Serial.println(deviceCount);
    Serial.println("Scan complete.");
}

void sendPage(WiFiClient& client) {
    client.println("HTTP/1.1 200 OK");
    client.println("Content-Type: text/html; charset=utf-8");
    client.println("Connection: close");
    client.println();

    client.println("<!DOCTYPE html><html><head>");
    client.println(
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
    );
    client.println("<title>SAMS Dashboard</title></head>");
    client.println(
        "<body style='font-family:Arial;max-width:700px;"
        "margin:30px auto;padding:16px'>"
    );

    client.println("<h1>SAMS</h1>");
    client.println("<p>Smart Asset Management System</p>");
    client.println("<p><b>Controller:</b> Online</p>");

    client.print("<p><b>ESP32 IP:</b> ");
    client.print(WiFi.localIP());
    client.println("</p>");

    client.println("<hr><h2>Network discovery</h2>");
    client.print("<p>Scanned host range: .");
    client.print(FIRST_HOST);
    client.print(" to .");
    client.print(LAST_HOST);
    client.println("</p>");

    client.print("<p>Devices replying to ping: ");
    client.print(deviceCount);
    client.println("</p>");

    client.println("<ul>");

    for (int i = 0; i < deviceCount; i++) {
        client.print("<li><b>");
        client.print(devices[i].ip);
        client.println("</b> — ICMP reply received</li>");
    }

    client.println("</ul>");
    client.println(
        "<p>Devices that block ping may not appear here, "
        "even when connected.</p>"
    );
    client.println("<p><a href='/scan'>Run scan again</a></p>");
    client.println("</body></html>");
}


void sendJson(WiFiClient& client, const String& body) {
    client.println("HTTP/1.1 200 OK");
    client.println("Content-Type: application/json");
    client.println("Access-Control-Allow-Origin: *");
    client.println("Cache-Control: no-store");
    client.println("Connection: close");
    client.println();
    client.println(body);
}

void sendNotFound(WiFiClient& client) {
    client.println("HTTP/1.1 404 Not Found");
    client.println("Content-Type: application/json");
    client.println("Connection: close");
    client.println();
    client.println("{\"error\":\"endpoint_not_found\"}");
}

void sendApiResponse(WiFiClient& client, const String& path) {
    if (path == "/api/v1/status") {
        String body = "{\"status\":\"online\",\"ip\":\"";
        body += WiFi.localIP().toString();
        body += "\",\"api_version\":1}";
        sendJson(client, body);
        return;
    }

    if (path == "/api/v1/devices") {
        // Registered devices will be stored separately from scan results.
        sendJson(client, "{\"devices\":[]}");
        return;
    }

    sendNotFound(client);
}


void setup() {
    Serial.begin(115200);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    Serial.print("Connecting");

    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }

    Serial.println();
    Serial.print("ESP32 IP: ");
    Serial.println(WiFi.localIP());

    Serial.print("Subnet Mask: ");
    Serial.println(WiFi.subnetMask());

    Serial.print("Gateway: ");
    Serial.println(WiFi.gatewayIP());


    server.begin();
    Serial.println("SAMS dashboard ready.");
}

void loop() {
    WiFiClient client = server.available();

    if (!client) {
        delay(2);
        return;
    }

    client.setTimeout(1000);
    String request = client.readStringUntil('\n');

    while (client.connected()) {
        String line = client.readStringUntil('\n');

        if (line == "\r" || line.length() == 0) {
            break;
        }
    }

        
    if (request.startsWith("GET ")) {
        int firstSpace = request.indexOf(' ');
        int secondSpace = request.indexOf(' ', firstSpace + 1);

        String path = request.substring(firstSpace + 1, secondSpace);

        if (path.startsWith("/api/v1/")) {
            sendApiResponse(client, path);
        } else {
            if (path == "/scan") {
                scanDevices();
            }

            sendPage(client);
        }
    }

    delay(2);
    client.stop();
}
