#define GRAPH

#include <driver/dac.h>
#include <Arduino.h>
#include <cmath>
#include <esp_adc_cal.h>
#include <driver/adc.h>

const int ADC_RES = 4096;       // 12-битный ADC
const int DAC_RES = 256;        // 8-битный DAC
const int INTERP_STEPS = 16;    // Шагов интерполяции
const int FINE_STEPS = 5;       // Точная интерполяция
const int AVG_COEF = 2;

#define ADC_PIN 35 
//*!< DAC channel 1 is GPIO25(ESP32) / GPIO17(ESP32S2) */
#define BUT_PIN 36 // 5 arduino



float RawData[DAC_RES] = {0};   // Сырые данные (256 точек)
float InterpData[ADC_RES] = {0};// Интерполированные данные (4096 точек)
float FineData[ADC_RES*FINE_STEPS] = {0}; // Высокоточные данные

template <typename A, typename B>
void PrintData (A a, B b)
{
  Serial.print("Data1 ");
  Serial.print((int)a);
  Serial.print(" ");
  Serial.print("Data2 ");
  Serial.println((int)b);
}

void Measure(int cycles) 
{
  for (int c = 0; c < cycles; c++)
  {
    for (int i = 0; i < DAC_RES; i++) {
      dac_output_voltage(DAC_CHANNEL_1, i);
      delayMicroseconds(100); // Увеличенное время стабилизации
      
      // Усреднение измерений
      float sum = 0;
      for (int s = 0; s < AVG_COEF; s++) {
        sum += analogRead(ADC_PIN);
        delayMicroseconds(10);
      }
      float avg = sum / (float)AVG_COEF;
      
      // Экспоненциальное сглаживание
      if (c == 0) RawData[i] = avg;
      else RawData[i] = 0.9f * RawData[i] + 0.1f * avg;
    }
  }
}

void Interpolate() {
  // Основная интерполяция (256 -> 4096 точек)
  for (int i = 0; i < DAC_RES-1; i++) {
    int idx = i * INTERP_STEPS;
    float step = (RawData[i+1] - RawData[i]) / INTERP_STEPS;
    
    for (int j = 0; j < INTERP_STEPS; j++) {
      InterpData[idx+j] = RawData[i] + step * j;
    }
  }
  // Заполняем последние значения
  InterpData[ADC_RES-1] = RawData[DAC_RES-1];
}

void FineInterpolate() {
  //  
  for (int i = 0; i < ADC_RES-1; i++) {
    float step = (InterpData[i+1] - InterpData[i]) / FINE_STEPS;
    for (int j = 0; j < FINE_STEPS; j++) {
      FineData[i*FINE_STEPS+j] = InterpData[i] + step * j;
    }
  }
}

void BuildLUT() {
  // Построение финальной LUT
  for (int i = 0; i < ADC_RES; i++) {
    float min_diff = INFINITY;
    int best_idx = 0;
    
    // Ищем ближайшее значение в FineData
    for (int j = 0; j < (ADC_RES-1)*FINE_STEPS; j++)
    {
      float diff = fabs(i - FineData[j]);
      if (diff < min_diff) {
        min_diff = diff;
        best_idx = j;
      }
    }
    InterpData[i] = best_idx / (float)FINE_STEPS;
  }
}

void setup() {

  Serial.begin(921600);
  dac_output_enable(DAC_CHANNEL_1);
  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);
/*
  // Читаем внутреннюю калибровку ESP32
  Serial.print("esp_adc_cal_check_efuse... ESP_ADC_CAL_VAL_EFUSE_VREF: ");
  Serial.println(esp_adc_cal_check_efuse( ESP_ADC_CAL_VAL_EFUSE_VREF));

  Serial.print("esp_adc_cal_check_efuse... ESP_ADC_CAL_VAL_EFUSE_TP: ");
  Serial.println(esp_adc_cal_check_efuse( ESP_ADC_CAL_VAL_EFUSE_TP));

  Serial.print("esp_adc_cal_check_efuse... ESP_ADC_CAL_VAL_DEFAULT_VREF: ");
  Serial.println(esp_adc_cal_check_efuse( ESP_ADC_CAL_VAL_DEFAULT_VREF));

  esp_adc_cal_characteristics_t adc_chars;
  esp_adc_cal_value_t val_type = esp_adc_cal_characterize(
      ADC_UNIT_1,          // ADC1 или ADC2
      ADC_ATTEN_DB_12,     // Ослабление (0dB, 2.5dB, 6dB, 11dB)
      ADC_WIDTH_BIT_12,     // Разрешение (9-12 бит)
      1100,                // Опорное напряжение (mV), можно 0 для автоматического определения
      &adc_chars           // Структура для хранения калибровочных данных
  );

  if (val_type == ESP_ADC_CAL_VAL_EFUSE_VREF) {
      Serial.println("Калибровка из eFuse (наиболее точная)");
      Serial.print("Значение VREF: ");
      Serial.print(adc_chars.vref);
      Serial.println(" мВ");
  } else if (val_type == ESP_ADC_CAL_VAL_EFUSE_TP) {
      Serial.println("Калибровка из eFuse (по температуре)");
      Serial.print("Значение VREF: ");
      Serial.print(adc_chars.vref);
      Serial.println(" мВ");
  } else {
      Serial.println("Калибровка не найдена, используется приблизительное значение 1100mV");
      Serial.print("Значение VREF: ");
      Serial.print(adc_chars.vref);
      Serial.println(" мВ");
  }
  */

}

void loop() {
  Serial.println("Начало калибровки...");
  // Этап 1: Измерения
  Measure(100);
  Serial.println("Калибровка завершена");
  while(Serial.parseInt() != 1){}
  for(int i = 0; i < DAC_RES; i++) {PrintData(i*16,RawData[i]);}
  
  // Этап 2: Интерполяция
  while(Serial.parseInt() != 1){}
  Serial.println("Основная интерполяция (256 -> 4096 точек)");
  Interpolate();
  //for(int i = 0; i < ADC_RES; i++) {PrintData(i,(uint16_t)InterpData[i]);}
  
  while(Serial.parseInt() != 1){}
  Serial.println("Высокоточная интерполяция (4096 -> 4096*5 точек)");
  FineInterpolate();
  //for(int i = 0; i < (ADC_RES)*FINE_STEPS; i++) {PrintData(i,FineData[i]);}
  
  // Этап 3: Построение LUT
  BuildLUT();

#ifdef GRAPH
  // Режим графиков
  Serial.print("Режим графиков");
  while(Serial.parseInt() != 1){}
  for (int i = 0; i < DAC_RES; i++) {
    dac_output_voltage(DAC_CHANNEL_1, i);
    delay(10);
    int raw = analogRead(ADC_PIN);
    PrintData (i*16, (uint16_t)InterpData[raw]);
  }
  while(1);
#else
  // Вывод LUT таблицы
  Serial.println("const uint16_t ADC_LUT[4096] PROGMEM = {");
  for (int i = 0; i < ADC_RES; i++) {
    Serial.print((uint16_t)round(InterpData[i]));
    if (i < ADC_RES-1) Serial.print(",");
    if (i % 16 == 15) Serial.println();
  }
  Serial.println("};");
  
  while(1);
#endif


}