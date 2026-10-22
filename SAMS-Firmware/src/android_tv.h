#pragma once

#include <Arduino.h>

// Initialise the Android TV control module.
void androidTvBegin();

// Send a power-toggle command.
// Returns true if the command was accepted for sending.
bool androidTvTogglePower();