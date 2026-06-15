/*
  ESP32-WROVER-E GC9A01 screen test sketch.
  Used to verify if the screen hardware is functional and if wiring is correct.
  
  Wiring Map:
  GC9A01 Screen <---> ESP32-WROVER-E (DevKitC)
  VCC           ---> 3.3V
  GND           ---> GND
  SCL (SCLK)    ---> GPIO 18 (VSPI SCK)
  SDA (MOSI)    ---> GPIO 23 (VSPI MOSI)
  CS            ---> GPIO 5  (VSPI CS)
  DC            ---> GPIO 21
  RST           ---> GPIO 22
*/

#include <Arduino.h>
#include <SPI.h>
#include <Adafruit_GFX.h>
#include <Adafruit_GC9A01A.h>

// Screen Pin Definitions (ESP32-WROVER-E VSPI Hardware SPI)
#define TFT_SCK  18
#define TFT_MOSI 23
#define TFT_MISO -1
#define TFT_CS   5
#define TFT_DC   21
#define TFT_RST  22

// Solid Color Definitions (16-bit RGB565)
#define COLOR_BLACK   0x0000
#define COLOR_WHITE   0xFFFF
#define COLOR_RED     0xF800
#define COLOR_GREEN   0x07E0
#define COLOR_BLUE    0x001F
#define COLOR_YELLOW  0xFFE0
#define COLOR_MAGENTA 0xF81F
#define COLOR_CYAN    0x07FF

// Initialize display
Adafruit_GC9A01A tft(TFT_CS, TFT_DC, TFT_RST);

void drawTestLabel(const char* label, uint16_t textColor, uint16_t bgColor) {
  // Center label at y = 110
  tft.setTextSize(2);
  tft.setTextColor(textColor, bgColor);
  
  // Standard character width is 6 * size = 12px
  int textWidth = strlen(label) * 12;
  int x = 120 - (textWidth / 2);
  
  tft.setCursor(x, 110);
  tft.print(label);
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("Starting ESP32-WROVER-E GC9A01 Screen Test...");

  // Initialize standard hardware SPI with our custom pins
  SPI.begin(TFT_SCK, -1 /* MISO */, TFT_MOSI, TFT_CS);
  
  // Initialize Adafruit GC9A01A display with a very slow 1MHz SPI speed
  // to ensure 100% signal integrity even with poor wiring.
  tft.begin(1000000);
  tft.setSPISpeed(1000000);
  
  // Re-establish pin routing since tft.begin() internally overrides them to defaults
  SPI.begin(TFT_SCK, -1 /* MISO */, TFT_MOSI, TFT_CS);
  
  tft.setRotation(0);
  tft.fillScreen(COLOR_BLACK);
  
  Serial.println("Screen initialized successfully.");
}

void loop() {
  Serial.println("Red screen test...");
  tft.fillScreen(COLOR_RED);
  drawTestLabel("RED SCREEN", COLOR_WHITE, COLOR_RED);
  delay(2000);

  Serial.println("Green screen test...");
  tft.fillScreen(COLOR_GREEN);
  drawTestLabel("GREEN SCREEN", COLOR_BLACK, COLOR_GREEN);
  delay(2000);

  Serial.println("Blue screen test...");
  tft.fillScreen(COLOR_BLUE);
  drawTestLabel("BLUE SCREEN", COLOR_WHITE, COLOR_BLUE);
  delay(2000);

  Serial.println("White screen test...");
  tft.fillScreen(COLOR_WHITE);
  drawTestLabel("WHITE SCREEN", COLOR_BLACK, COLOR_WHITE);
  delay(2000);

  Serial.println("Black screen test...");
  tft.fillScreen(COLOR_BLACK);
  drawTestLabel("BLACK SCREEN", COLOR_WHITE, COLOR_BLACK);
  delay(2000);

  Serial.println("Shapes and pattern test...");
  tft.fillScreen(COLOR_BLACK);
  
  // Draw circles
  tft.drawCircle(120, 120, 110, COLOR_WHITE);
  tft.drawCircle(120, 120, 90, COLOR_YELLOW);
  tft.drawCircle(120, 120, 70, COLOR_MAGENTA);
  tft.drawCircle(120, 120, 50, COLOR_CYAN);
  
  // Draw crossed lines
  tft.drawLine(20, 120, 220, 120, COLOR_RED);
  tft.drawLine(120, 20, 120, 220, COLOR_GREEN);
  
  // Draw text
  tft.setCursor(55, 95);
  tft.setTextColor(COLOR_WHITE, COLOR_BLACK);
  tft.setTextSize(2);
  tft.print("TEST PATTERN");
  
  tft.setCursor(65, 125);
  tft.setTextColor(COLOR_GREEN, COLOR_BLACK);
  tft.setTextSize(2);
  tft.print("GC9A01 OK!");
  
  delay(5000);
}
