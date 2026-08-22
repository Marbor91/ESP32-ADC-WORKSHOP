#include <Arduino.h>
#include "driver/adc.h"

// ------------------- НАСТРОЙКИ -------------------
#define BAUD_RATE 921600
#define ADC_PIN   ADC1_CHANNEL_7 // 35
#define MAX_SAMPLES 1000

// Переменные (изменяемые)
uint32_t sampleRate = 1000;
uint32_t samplesPerBatch = 500;
uint32_t postPause = 1000;

// Буферы (статичные)
static uint16_t buffer1[MAX_SAMPLES];
static uint16_t buffer2[MAX_SAMPLES];
uint16_t* currentBuffer = buffer1;
uint16_t* sendBuffer = nullptr;
volatile uint32_t sampleCount = 0;
volatile bool bufferReady = false;

hw_timer_t* timer = nullptr;

// ------------------- СОСТОЯНИЯ АВТОМАТА -------------------
enum States {
    IDLE,           // ожидание заполнения буфера
    SENDING_DATA,   // отправка данных (занимает несколько циклов)
    PAUSE,          // пауза после отправки
    SENDING_RST     // отправка PLOT_RST
};
States state = IDLE;
uint32_t pauseStart = 0;

// ------------------- ПРИЁМ КОМАНД -------------------
String inputString = "";
bool commandReady = false;

void processCommand(String cmd) {
    cmd.trim();
    if (cmd.startsWith("sampleRate = ")) {
        int val = cmd.substring(strlen("sampleRate = ")).toInt();
        if (val > 0) {
            sampleRate = val;
            // Переустановка таймера
            timerAlarmDisable(timer);
            uint32_t period_us = 1000000 / sampleRate;
            timerAlarmWrite(timer, period_us, true);
            timerAlarmEnable(timer);
            Serial.println("OK");
        } else {
            Serial.println("ERROR: sampleRate must be > 0");
        }
    }
    else if (cmd.startsWith("samplesPerBatch = ")) {
        int val = cmd.substring(strlen("samplesPerBatch = ")).toInt();
        if (val > 0 && val <= MAX_SAMPLES) {
            samplesPerBatch = val;
            // Сбрасываем текущий сбор, чтобы не было путаницы
            noInterrupts();
            sampleCount = 0;
            bufferReady = false;
            currentBuffer = buffer1;   // начинаем с первого
            sendBuffer = nullptr;
            interrupts();
            Serial.println("OK");
        } else {
            Serial.println("ERROR: value out of range (1..MAX_SAMPLES)");
        }
    }
    else if (cmd.startsWith("postPause = ")) {
        int val = cmd.substring(strlen("postPause = ")).toInt();
        if (val >= 0) {
            postPause = val;
            Serial.println("OK");
        } else {
            Serial.println("ERROR: postPause must be >= 0");
        }
    }
    else {
        Serial.println("ERROR: unknown command");
    }
}

// ------------------- ПРЕРЫВАНИЕ ТАЙМЕРА -------------------
void IRAM_ATTR onTimer() {
    uint16_t val = adc1_get_raw(ADC1_CHANNEL_7);
    if (sampleCount < samplesPerBatch) {
        currentBuffer[sampleCount] = val;
        sampleCount++;
        if (sampleCount == samplesPerBatch) {
            sendBuffer = currentBuffer;
            currentBuffer = (currentBuffer == buffer1) ? buffer2 : buffer1;
            sampleCount = 0;
            bufferReady = true;
        }
    }
}

// ------------------- SETUP -------------------
void setup() {
    Serial.begin(BAUD_RATE);

    adc1_config_width(ADC_WIDTH_BIT_12);
    adc1_config_channel_atten(ADC1_CHANNEL_7, ADC_ATTEN_DB_12);

    timer = timerBegin(0, 80, true);
    uint32_t period_us = 1000000 / sampleRate;
    timerAlarmWrite(timer, period_us, true);
    timerAttachInterrupt(timer, &onTimer, true);
    timerAlarmEnable(timer);

    state = IDLE;
}

// ------------------- LOOP -------------------
void loop() {
    // ---- 1. Приём команд ----
    while (Serial.available()) {
        char c = Serial.read();
        if (c == '\r' || c == '\n') {
            if (inputString.length() > 0) {
                commandReady = true;
                break;
            }
        } else {
            inputString += c;
        }
    }
    if (commandReady) {
        processCommand(inputString);
        inputString = "";
        commandReady = false;
    }

    // ---- 2. Автомат состояний ----
    switch (state) {
        case IDLE:
            if (bufferReady) {
                bufferReady = false;
                // Переходим к отправке данных
                state = SENDING_DATA;
                // sendBuffer уже установлен в прерывании
            }
            break;

        case SENDING_DATA:
            // Отправляем все отсчёты
            for (uint32_t i = 0; i < samplesPerBatch; i++) {
                Serial.print("|ADC = ");
                Serial.print(sendBuffer[i]);
                Serial.print("|\r\n");
            }
            Serial.print("|PLOT_END|\r\n");

            // Переходим в паузу
            pauseStart = millis();
            state = PAUSE;
            break;

        case PAUSE:
            if (millis() - pauseStart >= postPause) {
                // Отправляем команду сброса
                Serial.print("|PLOT_RST|\r\n");
                state = IDLE;   // готовы к новому пакету
            }
            break;

        default:
            state = IDLE;
            break;
    }

    // Небольшая задержка для стабильности (не блокирует приём)
    delay(1);
}