#include <Arduino.h>
#include <esp_log.h>
#include "esp32-hal-adc.h"

#include "hal_tds.h"
#include "app_def.h"

#define TAG __FILE__
#define TDS_PIN (A1) // TDS sensor pin, change as needed
#define VREF 3.3
#define ADC_RESOLUTION 12
#define ADC_MAX (1 << ADC_RESOLUTION)
#define ADC_SAMPLES 30
#define ADC_SAMPLE_INTERVAL_MS (40)

// ================================================================
// Private functions
// ================================================================
static int getMedianNum(int bArray[], int iFilterLen);

// ================================================================
// Public functions
// ================================================================
void hal_tds_init()
{
    pinMode(TDS_PIN, INPUT);
    analogReadResolution(ADC_RESOLUTION);

    // read the first value
    Serial.println("TDS Analog Read:");
    Serial.println(analogRead(TDS_PIN));
}

void hal_tds_deinit()
{
}

float hal_tds_read(float temperature)
{
    int sample[ADC_SAMPLES];
    for (int i = 0; i < ADC_SAMPLES; i++)
    {
        sample[i] = analogRead(TDS_PIN);
        delay(ADC_SAMPLE_INTERVAL_MS);
    }
    float avg_val = getMedianNum(sample, ADC_SAMPLES) * (VREF / (float)ADC_MAX);
    Serial.printf("TDS Analog Read AVG: %f\n", avg_val);
    float compensation_coeff = 1.0 + 0.02 * (temperature - 25.0);

    // compensation voltage
    float compensation_volt = avg_val / compensation_coeff;
    Serial.printf("TDS Compensation Volt: %.2f\n", compensation_volt);

    // convert voltage value to tds value
    float tds = (133.42 * compensation_volt * compensation_volt * compensation_volt - 255.86 * compensation_volt * compensation_volt + 857.39 * compensation_volt) * 0.5;

    delay(5000);
    return tds;
}

// median filtering algorithm
static int getMedianNum(int bArray[], int iFilterLen)
{
    int bTab[iFilterLen];
    for (byte i = 0; i < iFilterLen; i++)
        bTab[i] = bArray[i];
    int i, j, bTemp;
    for (j = 0; j < iFilterLen - 1; j++)
    {
        for (i = 0; i < iFilterLen - j - 1; i++)
        {
            if (bTab[i] > bTab[i + 1])
            {
                bTemp = bTab[i];
                bTab[i] = bTab[i + 1];
                bTab[i + 1] = bTemp;
            }
        }
    }
    if ((iFilterLen & 1) > 0)
    {
        bTemp = bTab[(iFilterLen - 1) / 2];
    }
    else
    {
        bTemp = (bTab[iFilterLen / 2] + bTab[iFilterLen / 2 - 1]) / 2;
    }
    return bTemp;
}