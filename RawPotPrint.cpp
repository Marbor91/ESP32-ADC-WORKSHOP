#include <Arduino.h>
const int adcPin = 15; // GPIO 15 is ADC2 Channel 3

void setup() {
    Serial.begin(921600);
    analogReadResolution(12);
    analogSetAttenuation(ADC_11db);
}
void loop() 
{
    int rawValue = analogRead(adcPin);
    float voltage = (rawValue/ 4095.0) * 3300; // Convert to voltage
    Serial.print("Raw = ");
    Serial.print(rawValue);
    Serial.print(' ');
    Serial.print("mV = ");
    Serial.println(voltage,1);
    delay(100);
}