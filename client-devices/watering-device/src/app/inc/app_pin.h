#pragma once

#include "Arduino.h"

// ================================================================
// Port definitions
// ================================================================

// Legacy temperature sensor. Not used by the current WTR cycle.
#define TEMP_SENSOR_PIN A0

// Legacy TDS sensor. Not used by the current WTR cycle.
#define TDS_SENSOR_PIN A1

// Soil moisture sensor (XIAO A2 shares the physical pin with D2)
#define SOIL_SENSOR_PIN A2

// Watering control
#define WATERING_PIN D4
