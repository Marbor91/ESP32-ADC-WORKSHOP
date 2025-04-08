#include <Arduino.h>

// Настройки сигнала
const float signalFreq = 1000.0;   // Частота синусоиды (1 кГц)
const float samplingFreq = 1000.0; // Частота дискретизации АЦП (1 кГц)
const int dacPin = 25;             // ЦАП (DAC1 на GPIO25)
const int adcPin = 35;        

// Буферы для данных
const int bufferSize = 200;        // Размер буфера для графиков
int dacValues[bufferSize];       // Буфер значений ЦАП
int adcValues[bufferSize];       // Буфер значений АЦП
int bufferIndex = 0;               // Текущий индекс буфера

// Время для управления частотой
unsigned long prevMicros = 0;
float sampleInterval = 1000000.0 / samplingFreq; // Интервал в микросекундах

void setup() {
  Serial.begin(921600);
  analogReadResolution(12);         // Разрешение АЦП (0-4095)
  analogSetAttenuation(ADC_11db);   // Установка усиления АЦП
  pinMode(adcPin, INPUT);           // Настройка АЦП
}

void loop() {
  unsigned long currentMicros = micros();

  // Генерация и чтение сигнала с заданной частотой дискретизации
  if (currentMicros - prevMicros >= sampleInterval) {
    prevMicros = currentMicros;

    // Генерация синусоиды (0-255 для 8-битного ЦАП)
    float time = currentMicros / 1000000.0;
    float sineValue = sin(2 * PI * signalFreq * time);
    uint8_t dacValue = 128 + 127 * sineValue; // 0-255
    dacWrite(dacPin, dacValue);

    // Чтение АЦП (0-4095 → масштабируем в 0-255 для сравнения)
    int adcValue = analogRead(adcPin);
    adcValue = map(adcValue, 0, 4095, 0, 255);

    // Запись в буферы
    if (bufferIndex < bufferSize) {
      dacValues[bufferIndex] = dacValue;
      adcValues[bufferIndex] = adcValue;
      bufferIndex++;
    }

    // Вывод данных при заполнении буфера
    if (bufferIndex >= bufferSize) {
      for (int i = 0; i < bufferSize; i++) {
        Serial.print("DAC ");
        Serial.print(dacValues[i]);
        Serial.print(" ADC ");
        Serial.println(adcValues[i]);
      }
      bufferIndex = 0; // Сброс индекса
    }
  }
}