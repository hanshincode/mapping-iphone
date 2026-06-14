/*
  ESP32-C3 Navigation Companion Device
  Receives navigation data over BLE and displays it on a 1.28" TFT GC9A01 screen.
  
  Wiring Map:
  GC9A01 Screen <---> ESP32-C3 SuperMini
  VCC           ---> 3.3V
  GND           ---> GND
  SCL (SCLK)    ---> GPIO 4 (Hardware SCK)
  SDA (MOSI)    ---> GPIO 6 (Hardware MOSI)
  DC            ---> GPIO 2
  CS            ---> GPIO 7
  RST           ---> GPIO 3
*/

#include <Arduino.h>
#include <Arduino_GFX_Library.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

// Screen Pin Definitions
#define TFT_SCK  4
#define TFT_MOSI 6
#define TFT_MISO -1
#define TFT_CS   7
#define TFT_DC   2
#define TFT_RST  3

// GFX Initialization
Arduino_DataBus *bus = new Arduino_ESP32SPI(TFT_DC, TFT_CS, TFT_SCK, TFT_MOSI, TFT_MISO);
Arduino_GFX *gfx = new Arduino_GC9A01(bus, TFT_RST, 0 /* rotation */, true /* IPS */);

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
      // Restart advertising immediately
      pServer->getAdvertising()->start();
    }
};

// BLE Characteristic Callback to receive navigation messages
class MyCallbacks: public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic *pCharacteristic) {
      std::string rxValue = pCharacteristic->getValue();
      if (rxValue.length() > 0) {
        String msg = String(rxValue.c_str());
        Serial.println("Received: " + msg);
        
        // Parse message format: "turnType;distanceString;streetName"
        // E.g. "1;150m;Nguyen Trai"
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
  // Draw small LED dot at the top center
  uint16_t color = deviceConnected ? RGB565(0, 255, 255) : RGB565(255, 0, 0); // Cyan if connected, Red if scanning
  gfx->fillCircle(120, 18, 5, color);
  
  gfx->setTextSize(1);
  gfx->setTextColor(RGB565(120, 120, 120));
  if (deviceConnected) {
    gfx->setCursor(102, 28);
    gfx->print("CONNECTED");
  } else {
    gfx->setCursor(105, 28);
    gfx->print("SCANNING");
  }
}

// Draw a bold line by drawing overlapping pixels or offset lines
void drawThickLine(int x1, int y1, int x2, int y2, int thickness, uint16_t color) {
  if (thickness <= 1) {
    gfx->drawLine(x1, y1, x2, y2, color);
    return;
  }
  for (int i = -thickness/2; i <= thickness/2; i++) {
    if (abs(x2 - x1) > abs(y2 - y1)) {
      gfx->drawLine(x1, y1 + i, x2, y2 + i, color);
    } else {
      gfx->drawLine(x1 + i, y1, x2 + i, y2, color);
    }
  }
}

// Function to draw arrow icon based on turnType
void drawNavigationArrow(int type) {
  int cx = 120;
  int cy = 90;
  uint16_t arrowColor = RGB565(0, 180, 255); // Premium blue
  
  // Clear the arrow area (bounding box y: 45 to 135)
  gfx->fillRect(50, 45, 140, 90, BLACK);
  
  switch(type) {
    case 0: // Go Straight / Up
      drawThickLine(cx, cy + 30, cx, cy - 30, 8, arrowColor);
      // Arrow head pointing UP
      gfx->fillTriangle(cx, cy - 32, cx - 20, cy - 10, cx + 20, cy - 10, arrowColor);
      break;
      
    case 1: // Turn Left
      drawThickLine(cx + 25, cy + 20, cx + 25, cy, 8, arrowColor); // stem up
      drawThickLine(cx + 25, cy, cx - 20, cy, 8, arrowColor);      // stem left
      // Arrow head pointing LEFT
      gfx->fillTriangle(cx - 22, cy, cx - 5, cy - 15, cx - 5, cy + 15, arrowColor);
      break;
      
    case 2: // Turn Right
      drawThickLine(cx - 25, cy + 20, cx - 25, cy, 8, arrowColor); // stem up
      drawThickLine(cx - 25, cy, cx + 20, cy, 8, arrowColor);      // stem right
      // Arrow head pointing RIGHT
      gfx->fillTriangle(cx + 22, cy, cx + 5, cy - 15, cx + 5, cy + 15, arrowColor);
      break;
      
    case 3: // Slight Left (diagonally top-left)
      // Angle drawing
      drawThickLine(cx + 15, cy + 20, cx - 15, cy - 15, 8, arrowColor);
      // Arrow head pointing top-left
      gfx->fillTriangle(cx - 17, cy - 17, cx - 18, cy + 3, cx, cy - 15, arrowColor);
      break;
      
    case 4: // Slight Right (diagonally top-right)
      // Angle drawing
      drawThickLine(cx - 15, cy + 20, cx + 15, cy - 15, 8, arrowColor);
      // Arrow head pointing top-right
      gfx->fillTriangle(cx + 17, cy - 17, cx, cy - 15, cx + 18, cy + 3, arrowColor);
      break;
      
    case 5: // U-Turn
      // Draw a U-hook pointing downwards on the left side
      // Stem right
      drawThickLine(cx + 15, cy + 25, cx + 15, cy - 15, 8, arrowColor);
      // Top horizontal bridge
      drawThickLine(cx + 15, cy - 15, cx - 15, cy - 15, 8, arrowColor);
      // Stem left down
      drawThickLine(cx - 15, cy - 15, cx - 15, cy + 15, 8, arrowColor);
      // Arrow head pointing DOWN
      gfx->fillTriangle(cx - 15, cy + 20, cx - 30, cy + 3, cx, cy + 3, arrowColor);
      break;
      
    case 6: // Roundabout
      // Circle outline
      gfx->drawCircle(cx, cy, 22, arrowColor);
      gfx->drawCircle(cx, cy, 21, arrowColor);
      gfx->drawCircle(cx, cy, 20, arrowColor);
      
      // Vertical entry stem
      drawThickLine(cx, cy + 35, cx, cy + 20, 6, arrowColor);
      // Arrow head exiting at 3 o'clock (Right)
      drawThickLine(cx + 20, cy, cx + 35, cy, 6, arrowColor);
      gfx->fillTriangle(cx + 37, cy, cx + 27, cy - 10, cx + 27, cy + 10, arrowColor);
      break;
      
    case 7: // Arrived (Finish Checkered Flag)
      // Flagpole
      drawThickLine(cx - 15, cy + 25, cx - 15, cy - 25, 4, RGB565(200, 200, 200));
      // Flag banners
      gfx->fillRect(cx - 13, cy - 25, 15, 10, WHITE);
      gfx->fillRect(cx + 2, cy - 25, 15, 10, BLACK);
      gfx->fillRect(cx - 13, cy - 15, 15, 10, BLACK);
      gfx->fillRect(cx + 2, cy - 15, 15, 10, WHITE);
      gfx->drawRect(cx - 13, cy - 25, 30, 20, WHITE);
      break;
      
    default: // Unknown / Straight fallback
      drawThickLine(cx, cy + 30, cx, cy - 30, 8, arrowColor);
      gfx->fillTriangle(cx, cy - 32, cx - 20, cy - 10, cx + 20, cy - 10, arrowColor);
      break;
  }
}

// Center text print utility
void drawCenteredString(String text, int y, int size, uint16_t color) {
  int charWidth = 6 * size; // Default font is 6x8 pixels per char at size 1
  int x = 120 - (text.length() * charWidth / 2);
  
  // Clean background for this specific text row to prevent ghosting
  gfx->fillRect(10, y, 220, size * 8, BLACK);
  
  gfx->setTextSize(size);
  gfx->setTextColor(color);
  gfx->setCursor(x, y);
  gfx->print(text);
}

void updateDisplay() {
  gfx->startWrite();
  
  // 1. Connection indicator & label
  drawConnectionStatus();
  
  // 2. Outer decorative ring
  gfx->drawCircle(120, 120, 117, RGB565(30, 50, 80)); // Sleek premium border ring
  
  // 3. Draw arrow representation
  if (deviceConnected) {
    drawNavigationArrow(currentTurnType);
  } else {
    // BLE scanning state placeholder
    gfx->fillRect(50, 45, 140, 90, BLACK);
    // Draw a bluetooth logo lookalike in the center
    int bx = 120, by = 90;
    gfx->drawLine(bx, by - 25, bx, by + 25, RGB565(100, 100, 100));
    gfx->drawLine(bx, by - 25, bx + 15, by - 12, RGB565(100, 100, 100));
    gfx->drawLine(bx + 15, by - 12, bx - 15, by + 12, RGB565(100, 100, 100));
    gfx->drawLine(bx - 15, by + 12, bx, by + 25, RGB565(100, 100, 100));
    gfx->drawLine(bx, by + 25, bx + 15, by + 12, RGB565(100, 100, 100));
    gfx->drawLine(bx + 15, by + 12, bx - 15, by - 12, RGB565(100, 100, 100));
  }
  
  // 4. Draw distance
  if (deviceConnected) {
    drawCenteredString(currentDistance, 148, 3, WHITE); // Large bold distance
  } else {
    drawCenteredString("--", 148, 3, RGB565(100, 100, 100));
  }
  
  // 5. Draw street name
  if (deviceConnected) {
    drawCenteredString(currentStreet, 185, 2, RGB565(0, 230, 180)); // Minty cyan street name
  } else {
    drawCenteredString("Mo app dien thoai", 185, 2, RGB565(150, 150, 150));
  }
  
  gfx->endWrite();
}

void setup() {
  Serial.begin(115200);
  
  // Initialize TFT screen
  gfx->begin();
  gfx->fillScreen(BLACK);
  
  // Welcome boot screen
  drawCenteredString("GMap Navi Device", 80, 2, WHITE);
  drawCenteredString("Khoi dong BLE...", 120, 2, RGB565(0, 180, 255));
  delay(1500);
  gfx->fillScreen(BLACK);
  
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
                                         BLECharacteristic::PROPERTY_WRITE_NO_RESPONSE
                                       );
                                       
  pCharacteristic->setCallbacks(new MyCallbacks());
  pCharacteristic->addDescriptor(new BLE2902());
  
  pService->start();
  
  BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
  pAdvertising->addServiceUUID(SERVICE_UUID);
  pAdvertising->setScanResponse(true);
  pAdvertising->setMinPreferred(0x06);  // helper for iPhone connections
  pAdvertising->setMinPreferred(0x12);
  
  BLEDevice::startAdvertising();
  Serial.println("BLE Advertising Started! Search for 'ESP32_Nav_Companion'");
  
  needsRedraw = true;
}

void loop() {
  // Only update display if state changes, avoiding screen flicker
  if (needsRedraw) {
    needsRedraw = false;
    updateDisplay();
  }
  
  // Check for connection/disconnection changes to trigger prints or screen modifications
  if (!deviceConnected && oldDeviceConnected) {
    delay(500); // give the bluetooth stack the chance to get ready
    oldDeviceConnected = deviceConnected;
    Serial.println("Disconnected!");
  }
  if (deviceConnected && !oldDeviceConnected) {
    oldDeviceConnected = deviceConnected;
    Serial.println("Connected!");
  }
  
  delay(50);
}
