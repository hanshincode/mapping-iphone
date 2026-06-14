/*
  ESP32-C3 Navigation Companion Device
  Receives navigation data over BLE and displays it on a 1.28" TFT GC9A01 screen.
  
  Wiring Map:
  GC9A01 Screen <---> ESP32-C3 SuperMini
  VCC           ---> 3.3V
  GND           ---> GND
  SCL (SCLK)    ---> GPIO 4
  SDA (MOSI)    ---> GPIO 6
  DC            ---> GPIO 2
  CS            ---> GPIO 7
  RST           ---> GPIO 3
*/

#include <Arduino.h>
#include <SPI.h>
#include <Adafruit_GFX.h>
#include <Adafruit_GC9A01A.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include "logo.h"

// Screen Pin Definitions
#define TFT_SCK  4
#define TFT_MOSI 6
#define TFT_MISO -1
#define TFT_CS   7
#define TFT_DC   2
#define TFT_RST  3

// Color Helpers
#ifndef BLACK
#define BLACK 0x0000
#endif
#ifndef WHITE
#define WHITE 0xFFFF
#endif
#ifndef RGB565
#define RGB565(r,g,b) ((((r) & 0xF8) << 8) | (((g) & 0xFC) << 3) | (((b) & 0xF8) >> 3))
#endif

// Official Adafruit GC9A01A Initialization
// This uses the official ESP32 hardware SPI driver, which handles pin routing perfectly
// and frees GPIO 2/3 from the internal WP/HD conflict.
Adafruit_GC9A01A tft(TFT_CS, TFT_DC, TFT_RST);

// BLE Definitions
#define SERVICE_UUID        "FFE0"
#define CHARACTERISTIC_UUID "FFE1"

bool deviceConnected = false;
bool oldDeviceConnected = false;

// Navigation State Variables
int currentTurnType = 0;       // 0: straight, 1: left, 2: right, 3: slight left, 4: slight right, 5: u-turn, 6: roundabout, 7: arrived
String currentDistance = "--";
String currentStreet = "Cho ket noi GMap";
bool needsRedraw = true;

// Custom BLE Server Callbacks
class MyServerCallbacks: public BLEServerCallbacks {
    void onConnect(BLEServer* pServer) {
      deviceConnected = true;
      needsRedraw = true;
    }

    void onDisconnect(BLEServer* pServer) {
      deviceConnected = false;
      needsRedraw = true;
      pServer->getAdvertising()->start();
    }
};

// BLE Characteristic Callback to receive navigation messages
class MyCallbacks: public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic *pCharacteristic) {
      String rxValue = pCharacteristic->getValue();
      if (rxValue.length() > 0) {
        String msg = rxValue;
        Serial.println("Received: " + msg);
        
        int firstSemi = msg.indexOf(';');
        int secondSemi = msg.indexOf(';', firstSemi + 1);
        
        if (firstSemi != -1 && secondSemi != -1) {
          currentTurnType = msg.substring(0, firstSemi).toInt();
          currentDistance = msg.substring(firstSemi + 1, secondSemi);
          currentStreet = msg.substring(secondSemi + 1);
          needsRedraw = true;
        }
      }
    }
};

void drawConnectionStatus() {
  uint16_t color = deviceConnected ? RGB565(0, 255, 255) : RGB565(255, 0, 0); // Cyan or Red
  tft.fillCircle(120, 18, 5, color);
  
  tft.setTextSize(1);
  tft.setTextColor(RGB565(120, 120, 120));
  if (deviceConnected) {
    tft.setCursor(102, 28);
    tft.print("CONNECTED");
  } else {
    tft.setCursor(105, 28);
    tft.print("SCANNING");
  }
}

void drawThickLine(int x1, int y1, int x2, int y2, int thickness, uint16_t color) {
  if (thickness <= 1) {
    tft.drawLine(x1, y1, x2, y2, color);
    return;
  }
  for (int i = -thickness/2; i <= thickness/2; i++) {
    if (abs(x2 - x1) > abs(y2 - y1)) {
      tft.drawLine(x1, y1 + i, x2, y2 + i, color);
    } else {
      tft.drawLine(x1 + i, y1, x2 + i, y2, color);
    }
  }
}

void drawNavigationArrow(int type) {
  int cx = 120;
  int cy = 90;
  uint16_t arrowColor = RGB565(0, 180, 255); // Premium blue
  
  tft.fillRect(50, 45, 140, 90, BLACK);
  
  switch(type) {
    case 0: // Go Straight
      drawThickLine(cx, cy + 30, cx, cy - 30, 8, arrowColor);
      tft.fillTriangle(cx, cy - 32, cx - 20, cy - 10, cx + 20, cy - 10, arrowColor);
      break;
      
    case 1: // Turn Left
      drawThickLine(cx + 25, cy + 20, cx + 25, cy, 8, arrowColor);
      drawThickLine(cx + 25, cy, cx - 20, cy, 8, arrowColor);
      tft.fillTriangle(cx - 22, cy, cx - 5, cy - 15, cx - 5, cy + 15, arrowColor);
      break;
      
    case 2: // Turn Right
      drawThickLine(cx - 25, cy + 20, cx - 25, cy, 8, arrowColor);
      drawThickLine(cx - 25, cy, cx + 20, cy, 8, arrowColor);
      tft.fillTriangle(cx + 22, cy, cx + 5, cy - 15, cx + 5, cy + 15, arrowColor);
      break;
      
    case 3: // Slight Left
      drawThickLine(cx + 15, cy + 20, cx - 15, cy - 15, 8, arrowColor);
      tft.fillTriangle(cx - 17, cy - 17, cx - 18, cy + 3, cx, cy - 15, arrowColor);
      break;
      
    case 4: // Slight Right
      drawThickLine(cx - 15, cy + 20, cx + 15, cy - 15, 8, arrowColor);
      tft.fillTriangle(cx + 17, cy - 17, cx, cy - 15, cx + 18, cy + 3, arrowColor);
      break;
      
    case 5: // U-Turn
      drawThickLine(cx + 15, cy + 25, cx + 15, cy - 15, 8, arrowColor);
      drawThickLine(cx + 15, cy - 15, cx - 15, cy - 15, 8, arrowColor);
      drawThickLine(cx - 15, cy - 15, cx - 15, cy + 15, 8, arrowColor);
      tft.fillTriangle(cx - 15, cy + 20, cx - 30, cy + 3, cx, cy + 3, arrowColor);
      break;
      
    case 6: // Roundabout
      tft.drawCircle(cx, cy, 22, arrowColor);
      tft.drawCircle(cx, cy, 21, arrowColor);
      tft.drawCircle(cx, cy, 20, arrowColor);
      drawThickLine(cx, cy + 35, cx, cy + 20, 6, arrowColor);
      drawThickLine(cx + 20, cy, cx + 35, cy, 6, arrowColor);
      tft.fillTriangle(cx + 37, cy, cx + 27, cy - 10, cx + 27, cy + 10, arrowColor);
      break;
      
    case 7: // Arrived
      drawThickLine(cx - 15, cy + 25, cx - 15, cy - 25, 4, RGB565(200, 200, 200));
      tft.fillRect(cx - 13, cy - 25, 15, 10, WHITE);
      tft.fillRect(cx + 2, cy - 25, 15, 10, BLACK);
      tft.fillRect(cx - 13, cy - 15, 15, 10, BLACK);
      tft.fillRect(cx + 2, cy - 15, 15, 10, WHITE);
      tft.drawRect(cx - 13, cy - 25, 30, 20, WHITE);
      break;
      
    default:
      drawThickLine(cx, cy + 30, cx, cy - 30, 8, arrowColor);
      tft.fillTriangle(cx, cy - 32, cx - 20, cy - 10, cx + 20, cy - 10, arrowColor);
      break;
  }
}

void drawCenteredString(String text, int y, int size, uint16_t color) {
  // Calculate maximum safe width at this Y coordinate on a 240-diameter circular screen
  int dy = abs(y + (size * 8) / 2 - 120);
  int maxWidth = 220;
  if (dy < 120) {
    maxWidth = 2 * sqrt(120 * 120 - dy * dy) - 16; // 8px margin on each side
  }
  if (maxWidth < 20) maxWidth = 20;

  // Dynamically reduce font size if the text is too wide for this line
  int currentSize = size;
  int charWidth = 6 * currentSize;
  int textWidth = text.length() * charWidth;
  
  if (textWidth > maxWidth && currentSize > 1) {
    currentSize--;
    charWidth = 6 * currentSize;
    textWidth = text.length() * charWidth;
  }
  
  // If still too wide, truncate the text and append "..."
  if (textWidth > maxWidth) {
    while (text.length() > 3 && textWidth > maxWidth) {
      text = text.substring(0, text.length() - 1);
      textWidth = (text.length() + 3) * charWidth;
    }
    text += "...";
    textWidth = text.length() * charWidth;
  }
  
  int x = 120 - (textWidth / 2);
  
  // Clear only the drawing area of this line to prevent screen-wide flickering
  tft.fillRect(120 - maxWidth/2 - 4, y, maxWidth + 8, currentSize * 8, BLACK);
  
  tft.setTextSize(currentSize);
  tft.setTextColor(color);
  tft.setCursor(x, y);
  tft.print(text);
}

void updateDisplay() {
  drawConnectionStatus();
  tft.drawCircle(120, 120, 117, RGB565(30, 50, 80));
  
  if (deviceConnected) {
    drawNavigationArrow(currentTurnType);
  } else {
    tft.fillRect(50, 45, 140, 90, BLACK);
    int bx = 120, by = 90;
    tft.drawLine(bx, by - 25, bx, by + 25, RGB565(100, 100, 100));
    tft.drawLine(bx, by - 25, bx + 15, by - 12, RGB565(100, 100, 100));
    tft.drawLine(bx + 15, by - 12, bx - 15, by + 12, RGB565(100, 100, 100));
    tft.drawLine(bx - 15, by + 12, bx, by + 25, RGB565(100, 100, 100));
    tft.drawLine(bx, by + 25, bx + 15, by + 12, RGB565(100, 100, 100));
    tft.drawLine(bx + 15, by + 12, bx - 15, by - 12, RGB565(100, 100, 100));
  }
  
  if (deviceConnected) {
    drawCenteredString(currentDistance, 148, 3, WHITE);
  } else {
    drawCenteredString("--", 148, 3, RGB565(100, 100, 100));
  }
  
  if (deviceConnected) {
    drawCenteredString(currentStreet, 185, 2, RGB565(0, 230, 180));
  } else {
    drawCenteredString("Mo app dien thoai", 185, 2, RGB565(150, 150, 150));
  }
}

void setup() {
  Serial.begin(115200);
  
  // Initialize standard hardware SPI with our custom pins
  SPI.begin(TFT_SCK, -1 /* MISO */, TFT_MOSI, TFT_CS);
  
  // Initialize Adafruit GC9A01A display with 8MHz SPI speed for signal stability
  tft.begin(8000000);
  tft.setSPISpeed(8000000);
  
  // Re-establish pin routing since tft.begin() internally overrides them to defaults
  SPI.begin(TFT_SCK, -1 /* MISO */, TFT_MOSI, TFT_CS);
  
  tft.setRotation(0);
  tft.fillScreen(BLACK);
  
  // Welcome boot screen displaying brand logo
  int logoX = (240 - brand_logo_width) / 2;
  int logoY = (240 - brand_logo_height) / 2;
  tft.drawRGBBitmap(logoX, logoY, brand_logo, brand_logo_width, brand_logo_height);
  delay(2000);
  tft.fillScreen(BLACK);
  
  // Initialize BLE
  BLEDevice::init("ESP32_Nav_Companion");
  BLEServer *pServer = BLEDevice::createServer();
  pServer->setCallbacks(new MyServerCallbacks());
  
  BLEService *pService = pServer->createService(SERVICE_UUID);
  
  BLECharacteristic *pCharacteristic = pService->createCharacteristic(
                                         CHARACTERISTIC_UUID,
                                         BLECharacteristic::PROPERTY_READ |
                                         BLECharacteristic::PROPERTY_WRITE |
                                         BLECharacteristic::PROPERTY_NOTIFY |
                                         BLECharacteristic::PROPERTY_WRITE_NR
                                       );
                                       
  pCharacteristic->setCallbacks(new MyCallbacks());
  pCharacteristic->addDescriptor(new BLE2902());
  
  pService->start();
  
  BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
  pAdvertising->addServiceUUID(SERVICE_UUID);
  pAdvertising->setScanResponse(true);
  pAdvertising->setMinPreferred(0x06);
  pAdvertising->setMinPreferred(0x12);
  
  BLEDevice::startAdvertising();
  Serial.println("BLE Advertising Started! Search for 'ESP32_Nav_Companion'");
  
  needsRedraw = true;
}

void loop() {
  if (needsRedraw) {
    needsRedraw = false;
    updateDisplay();
  }
  
  if (!deviceConnected && oldDeviceConnected) {
    delay(500);
    oldDeviceConnected = deviceConnected;
    Serial.println("Disconnected!");
  }
  if (deviceConnected && !oldDeviceConnected) {
    oldDeviceConnected = deviceConnected;
    Serial.println("Connected!");
  }
  
  delay(50);
}
