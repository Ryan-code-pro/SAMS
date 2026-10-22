#include "android_tv.h"
#include <WiFi.h>

void androidTvBegin() {
    Serial.println("[SAMS TV] Android TV module initialised.");

    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[SAMS TV] Wi-Fi is not connected.");
        return;
    }

    Serial.print("[SAMS TV] Ready to connect to the TV at ");
    Serial.println("192.168.1.10");
}

bool androidTvTogglePower() {
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[SAMS TV] Cannot send command: Wi-Fi offline.");
        return false;
    }

    Serial.println(
        "[SAMS TV] Power control protocol is not implemented yet."
    );

    // Placeholder: no command is sent to the TV yet.
    return false;
}