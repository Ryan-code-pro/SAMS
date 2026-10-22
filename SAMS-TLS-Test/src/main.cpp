#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <LittleFS.h>

// Fill these in locally. Don't share your password.
const char* WIFI_SSID = "Kartik";
const char* WIFI_PASSWORD = "9412291479";

const char* TV_IP = "192.168.1.10";
const uint16_t TV_PORT = 6466;

void setup() {
    Serial.begin(115200);
    delay(1000);

    Serial.println("\n[SAMS TV] TLS test starting");

    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    Serial.print("[Wi-Fi] Connecting");
    unsigned long start = millis();

    while (WiFi.status() != WL_CONNECTED &&
           millis() - start < 20000) {
        Serial.print(".");
        delay(500);
    }

    Serial.println();

    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[ERROR] Wi-Fi connection failed.");
        return;
    }

    Serial.print("[Wi-Fi] IP: ");
    Serial.println(WiFi.localIP());

    if (!LittleFS.begin(false)) {
        Serial.println("[ERROR] LittleFS mount failed.");
        return;
    }

    File certFile = LittleFS.open("/sams_tv_cert.pem", "r");
    File keyFile = LittleFS.open("/sams_tv_key.pem", "r");

    if (!certFile || !keyFile) {
        Serial.println("[ERROR] Certificate or key missing.");
        Serial.println("Upload the LittleFS data folder first.");
        return;
    }

    String cert = certFile.readString();
    String key = keyFile.readString();

    certFile.close();
    keyFile.close();

    WiFiClientSecure client;

    // Diagnostic test: disable server certificate verification.
    client.setInsecure();

    Serial.printf("[TLS] Certificate bytes: %u\n", cert.length());
    Serial.printf("[TLS] Private-key bytes: %u\n", key.length());

    client.setCertificate(cert.c_str());
    client.setPrivateKey(key.c_str());

    Serial.println("[TLS] Client certificate and key configured.");

    Serial.printf("[TLS] Certificate header: %s\n",
                cert.startsWith("-----BEGIN CERTIFICATE-----") ? "OK" : "INVALID");

    Serial.printf("[TLS] Private-key header: %s\n",
                key.startsWith("-----BEGIN RSA PRIVATE KEY-----") ||
                key.startsWith("-----BEGIN PRIVATE KEY-----") ? "OK" : "INVALID");
    client.setCertificate(cert.c_str());
    client.setPrivateKey(key.c_str());

    Serial.printf("[TLS] Connecting to %s:%u ...\n",
                  TV_IP, TV_PORT);
    Serial.println("[TLS] Starting handshake with TV...");
    if (!client.connect("192.168.1.10", 6466)) {
    Serial.println("[TLS] Connection failed.");

    char errorBuffer[256] = {0};
    int errorCode = client.lastError(errorBuffer, sizeof(errorBuffer));

    Serial.printf("[TLS] Error code: %d\n", errorCode);
    Serial.printf("[TLS] Error detail: %s\n", errorBuffer);

    return;
}

    Serial.println("[TLS] Connection successful!");

    Serial.println("[TLS] Connection established!");
    Serial.println(
        "[INFO] TLS succeeded; remote protocol not tested yet.");

    delay(1000);
    client.stop();
}

void loop() {
    delay(1000);
}