
#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <Preferences.h>
#include <ArduinoJson.h>
#include <time.h>

// Keep your Wi-Fi credentials private and set them locally.
const char* WIFI_SSID = "Kartik";
const char* WIFI_PASSWORD = "9412291479";

WebServer server(80);
Preferences preferences;

static const int MAX_SCHEDULES = 12;
static const long GMT_OFFSET_SECONDS = 19800; // India: UTC+5:30
static const int DAYLIGHT_OFFSET_SECONDS = 0;

String schedulesJson = "{\"schedules\":[]}";
bool clockReady = false;


// -------------------- TIME HELPERS --------------------

String todayKey() {
    struct tm t;
    if (!getLocalTime(&t, 20)) return "";

    char date[11];
    strftime(date, sizeof(date), "%Y-%m-%d", &t);
    return String(date);
}

String currentTimeKey() {
    struct tm t;
    if (!getLocalTime(&t, 20)) return "";

    char timeText[6];
    strftime(timeText, sizeof(timeText), "%H:%M", &t);
    return String(timeText);
}


// -------------------- HTTP HELPERS --------------------

void sendJson(int status, const String& body) {
    server.sendHeader("Access-Control-Allow-Origin", "*");
    server.sendHeader("Access-Control-Allow-Headers", "Content-Type");
    server.sendHeader(
        "Access-Control-Allow-Methods",
        "GET, POST, DELETE, OPTIONS"
    );
    server.sendHeader("Cache-Control", "no-store");
    server.send(status, "application/json", body);
}

void handleStatus() {
    JsonDocument doc;

    doc["status"] = "online";
    doc["ip"] = WiFi.localIP().toString();
    doc["api_version"] = 1;
    doc["clock_synced"] = clockReady;

    String body;
    serializeJson(doc, body);
    sendJson(200, body);
}

void handleSchedulesGet() {
    sendJson(200, schedulesJson);
}


// -------------------- SERIAL DISPLAY --------------------

void printScheduleJson(const String& json, const char* heading) {
    Serial.println();
    Serial.println("========================================");
    Serial.println(heading);
    Serial.println("========================================");

    JsonDocument doc;
    DeserializationError error = deserializeJson(doc, json);

    if (error) {
        Serial.print("Could not parse schedule JSON: ");
        Serial.println(error.c_str());
        Serial.println("========================================");
        return;
    }

    serializeJsonPretty(doc, Serial);
    Serial.println();
    Serial.println("========================================");
}

void printDeviceProfile(JsonObject profile) {
    Serial.println("  Device profile:");
    Serial.printf(
        "    Name:     %s\n",
        profile["name"] | "Unknown"
    );
    Serial.printf(
        "    IP:       %s\n",
        profile["ip"] | "Unknown"
    );
    Serial.printf(
        "    Type:     %s\n",
        profile["type"] | "Unknown"
    );
    Serial.printf(
        "    Source:   %s\n",
        profile["source"] | "Unknown"
    );

    Serial.print("    Services: ");

    JsonArray services = profile["services"].as<JsonArray>();

    if (services.isNull() || services.size() == 0) {
        Serial.println("(none recorded)");
    } else {
        for (JsonVariant service : services) {
            if (service != services[0]) {
                Serial.print(", ");
            }
            Serial.print(service.as<const char*>());
        }
        Serial.println();
    }
}

void printStoredSchedules() {
    JsonDocument doc;

    DeserializationError error = deserializeJson(doc, schedulesJson);
    if (error) {
        Serial.println("Could not read stored schedule JSON.");
        return;
    }

    JsonArray items = doc["schedules"].as<JsonArray>();

    Serial.printf(
        "\nRestored %u schedule(s) from flash.\n",
        static_cast<unsigned>(items.size())
    );

    for (JsonObject item : items) {
        Serial.printf("Device: %s\n", item["device"] | "Unknown");
        Serial.printf("IP:     %s\n", item["ip"] | "Unknown");
        Serial.printf("Action: %s\n", item["action"] | "Unknown");
        Serial.printf("Time:   %s\n", item["time"] | "Unknown");

        if (item["profile"].is<JsonObject>()) {
            printDeviceProfile(item["profile"].as<JsonObject>());
        }

        Serial.println("----------------------------------------");
    }
}


// -------------------- PROFILE STORAGE --------------------

void copyDeviceProfile(
    JsonObject destination,
    JsonObject source,
    const char* device,
    const char* ip
) {
    // Fill in missing profile fields from the schedule entry.
    destination["name"] = source["name"] | device;
    destination["ip"] = source["ip"] | ip;
    destination["type"] = source["type"] | "Network device";
    destination["source"] = source["source"] | "Unknown";

    JsonArray outputServices = destination["services"].to<JsonArray>();
    JsonArray inputServices = source["services"].as<JsonArray>();

    if (!inputServices.isNull()) {
        for (JsonVariant service : inputServices) {
            if (service.is<const char*>()) {
                outputServices.add(service.as<const char*>());
            }
        }
    }
}


// -------------------- RECEIVE SCHEDULES --------------------

void handleSchedulesPost() {
    JsonDocument incoming;

    DeserializationError error =
        deserializeJson(incoming, server.arg("plain"));

    if (error) {
        sendJson(400, "{\"error\":\"invalid_json\"}");
        return;
    }

    // Accept both formats:
    // 1. {"schedules": [...]}
    // 2. [...]
    JsonArray input;

    if (incoming.is<JsonArray>()) {
        input = incoming.as<JsonArray>();
    } else {
        input = incoming["schedules"].as<JsonArray>();
    }

    if (input.isNull() || input.size() > MAX_SCHEDULES) {
        sendJson(
            400,
            "{\"error\":\"schedules_required_or_limit_exceeded\"}"
        );
        return;
    }

    JsonDocument clean;
    JsonArray output = clean["schedules"].to<JsonArray>();

    // Validate every entry before writing anything to flash.
    for (JsonVariant value : input) {
        if (!value.is<JsonObject>()) {
            sendJson(400, "{\"error\":\"invalid_schedule_entry\"}");
            return;
        }

        JsonObject item = value.as<JsonObject>();

        const char* device = item["device"] | "";
        const char* ip = item["ip"] | "";
        const char* action = item["action"] | "";
        const char* timeText = item["time"] | "";

        IPAddress parsedIP;

        if (
            strlen(device) == 0 ||
            strlen(device) > 64 ||
            !parsedIP.fromString(ip) ||
            (strcmp(action, "ON") != 0 &&
             strcmp(action, "OFF") != 0) ||
            strlen(timeText) != 5 ||
            timeText[2] != ':' ||
            !isDigit(timeText[0]) ||
            !isDigit(timeText[1]) ||
            !isDigit(timeText[3]) ||
            !isDigit(timeText[4])
        ) {
            sendJson(400, "{\"error\":\"invalid_schedule_entry\"}");
            return;
        }

        int hour = (timeText[0] - '0') * 10 + (timeText[1] - '0');
        int minute = (timeText[3] - '0') * 10 + (timeText[4] - '0');

        if (hour > 23 || minute > 59) {
            sendJson(400, "{\"error\":\"invalid_time\"}");
            return;
        }

        JsonObject entry = output.add<JsonObject>();

        entry["device"] = device;
        entry["ip"] = ip;
        entry["action"] = action;
        entry["time"] = timeText;

        // A newly uploaded schedule has not run today.
        entry["lastRunDate"] = "";

        // Preserve the complete device profile.
        JsonObject savedProfile = entry["profile"].to<JsonObject>();

        if (item["profile"].is<JsonObject>()) {
            copyDeviceProfile(
                savedProfile,
                item["profile"].as<JsonObject>(),
                device,
                ip
            );
        } else {
            // Compatibility with older app schedules without profiles.
            JsonObject emptyProfile;
            copyDeviceProfile(
                savedProfile,
                emptyProfile,
                device,
                ip
            );
        }
    }

    String candidate;
    serializeJson(clean, candidate);

    // Persist to ESP32 non-volatile storage.
    if (!preferences.begin("sams", false)) {
        sendJson(500, "{\"error\":\"storage_unavailable\"}");
        return;
    }

    size_t written = preferences.putString("schedule", candidate);
    preferences.end();

    if (written == 0) {
        sendJson(500, "{\"error\":\"storage_write_failed\"}");
        return;
    }

    schedulesJson = candidate;

    // Show exactly what the ESP32 accepted and saved.
    printScheduleJson(
        schedulesJson,
        "SCHEDULE AND DEVICE PROFILES RECEIVED"
    );

    // Print the profiles in a readable form as well.
    JsonDocument received;
    deserializeJson(received, schedulesJson);

    JsonArray savedItems = received["schedules"].as<JsonArray>();

    Serial.printf(
        "SAMS received and saved %u schedule(s).\n",
        static_cast<unsigned>(savedItems.size())
    );

    for (JsonObject savedItem : savedItems) {
        Serial.printf(
            "\nDevice: %s | Action: %s | Time: %s\n",
            savedItem["device"] | "Unknown",
            savedItem["action"] | "Unknown",
            savedItem["time"] | "Unknown"
        );

        if (savedItem["profile"].is<JsonObject>()) {
            printDeviceProfile(savedItem["profile"].as<JsonObject>());
        }
    }

    JsonDocument response;
    response["saved"] = true;
    response["count"] = savedItems.size();

    String responseBody;
    serializeJson(response, responseBody);
    sendJson(200, responseBody);
}


// -------------------- CLEAR SCHEDULES --------------------

void handleSchedulesDelete() {
    String empty = "{\"schedules\":[]}";

    if (!preferences.begin("sams", false)) {
        sendJson(500, "{\"error\":\"storage_unavailable\"}");
        return;
    }

    size_t written = preferences.putString("schedule", empty);
    preferences.end();

    if (written == 0) {
        sendJson(500, "{\"error\":\"storage_write_failed\"}");
        return;
    }

    schedulesJson = empty;

    Serial.println("All SAMS schedules cleared from flash.");

    sendJson(200, "{\"cleared\":true}");
}


// -------------------- WEB DASHBOARD --------------------

void handleHome() {
    String page =
        "<!doctype html><html><head>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>SAMS Controller</title></head>"
        "<body style='font-family:Arial;max-width:700px;margin:40px auto;"
        "padding:16px;background:#111;color:#fff'>"
        "<h1>SAMS</h1><p>Smart Asset Management System</p>"
        "<p>Controller: ONLINE</p><p>IP: ";

    page += WiFi.localIP().toString();

    page += "</p><p><a style='color:#ff8a00' href='/api/v1/status'>"
            "Check API status</a></p>"
            "<p><a style='color:#ff8a00' href='/api/v1/schedules'>"
            "View saved schedules</a></p></body></html>";

    server.send(200, "text/html", page);
}


// -------------------- SCHEDULE ENGINE --------------------

void executeAction(JsonObject item, const String& date) {
    Serial.println("\n=== SAMS SCHEDULE TRIGGERED ===");
    Serial.printf("Device: %s\n", item["device"] | "");
    Serial.printf("IP:     %s\n", item["ip"] | "");
    Serial.printf("Action: %s\n", item["action"] | "");
    Serial.println("Device-control adapter still required.");
    Serial.println("===============================\n");

    item["lastRunDate"] = date;
}

void checkSchedules() {
    if (!clockReady) return;

    String date = todayKey();
    String now = currentTimeKey();

    if (date.isEmpty() || now.isEmpty()) return;

    JsonDocument doc;
    if (deserializeJson(doc, schedulesJson)) return;

    JsonArray items = doc["schedules"].as<JsonArray>();
    bool changed = false;

    for (JsonObject item : items) {
        const char* scheduledTime = item["time"] | "";
        const char* lastRun = item["lastRunDate"] | "";

        // Run each entry at most once per local calendar day.
        if (now == scheduledTime && date != lastRun) {
            executeAction(item, date);
            changed = true;
        }
    }

    if (changed) {
        String updated;
        serializeJson(doc, updated);

        if (preferences.begin("sams", false)) {
            if (preferences.putString("schedule", updated) > 0) {
                schedulesJson = updated;
            }
            preferences.end();
        }
    }
}


// -------------------- SETUP --------------------

void setup() {
    Serial.begin(115200);
    delay(500);

    Serial.println("\nStarting SAMS controller...");

    if (!preferences.begin("sams", false)) {
        Serial.println("ERROR: Cannot open persistent storage.");
    } else {
        schedulesJson = preferences.getString(
            "schedule",
            "{\"schedules\":[]}"
        );
        preferences.end();
    }

    printStoredSchedules();

    WiFi.mode(WIFI_STA);
    WiFi.setHostname("sams-controller");
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    Serial.print("Connecting to Wi-Fi");

    unsigned long started = millis();

    while (
        WiFi.status() != WL_CONNECTED &&
        millis() - started < 20000
    ) {
        delay(400);
        Serial.print(".");
    }

    Serial.println();

    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("Wi-Fi connection failed. Restart to retry.");
        return;
    }

    Serial.print("ESP32 IP: ");
    Serial.println(WiFi.localIP());

    Serial.print("Gateway: ");
    Serial.println(WiFi.gatewayIP());

    configTime(
        GMT_OFFSET_SECONDS,
        DAYLIGHT_OFFSET_SECONDS,
        "pool.ntp.org",
        "time.google.com"
    );

    struct tm timeInfo;
    clockReady = getLocalTime(&timeInfo, 10000);

    Serial.println(
        clockReady
            ? "Clock synchronized."
            : "Clock not synchronized yet; schedules are waiting."
    );

    server.on("/", HTTP_GET, handleHome);
    server.on("/api/v1/status", HTTP_GET, handleStatus);
    server.on("/api/v1/schedules", HTTP_GET, handleSchedulesGet);
    server.on("/api/v1/schedules", HTTP_POST, handleSchedulesPost);
    server.on("/api/v1/schedules", HTTP_DELETE, handleSchedulesDelete);

    server.on("/api/v1/status", HTTP_OPTIONS, []() {
        sendJson(204, "");
    });

    server.on("/api/v1/schedules", HTTP_OPTIONS, []() {
        sendJson(204, "");
    });

    server.onNotFound([]() {
        sendJson(404, "{\"error\":\"endpoint_not_found\"}");
    });

    server.begin();
    Serial.println("SAMS API ready on port 80.");
}


// -------------------- MAIN LOOP --------------------

void loop() {
    if (WiFi.status() == WL_CONNECTED) {
        server.handleClient();

        static unsigned long lastClockCheck = 0;

        if (millis() - lastClockCheck >= 1000) {
            lastClockCheck = millis();

            if (!clockReady) {
                struct tm t;
                clockReady = getLocalTime(&t, 10);

                if (clockReady) {
                    Serial.println("Clock synchronized.");
                }
            }

            checkSchedules();
        }
    }

    delay(2);
}
