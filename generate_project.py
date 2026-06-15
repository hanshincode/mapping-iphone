import os

def create_directory_structure():
    directories = [
        "MapNavigationApp",
        "MapNavigationApp.xcodeproj",
        "MapNavigationApp.xcodeproj/xcshareddata/xcschemes"
    ]
    for d in directories:
        os.makedirs(d, exist_ok=True)
        print(f"Created directory: {d}")

def write_app_swift():
    content = """import SwiftUI

@main
struct MapNavigationAppApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}
"""
    with open("MapNavigationApp/MapNavigationAppApp.swift", "w", encoding="utf-8") as f:
        f.write(content)
    print("Wrote MapNavigationAppApp.swift")

def write_ble_manager():
    content = r"""import Foundation
import CoreBluetooth

@MainActor
class BLEManager: NSObject, ObservableObject, CBCentralManagerDelegate, CBPeripheralDelegate {
    @Published var isConnected = false
    @Published var isScanning = false
    @Published var discoveredPeripherals: [CBPeripheral] = []
    @Published var connectedPeripheral: CBPeripheral?
    
    private var centralManager: CBCentralManager!
    private var writeCharacteristic: CBCharacteristic?
    
    let serviceUUID = CBUUID(string: "FFE0")
    let characteristicUUID = CBUUID(string: "FFE1")
    
    override init() {
        super.init()
        centralManager = CBCentralManager(delegate: self, queue: nil)
    }
    
    func startScanning() {
        guard centralManager.state == .poweredOn else { return }
        isScanning = true
        discoveredPeripherals.removeAll()
        centralManager.scanForPeripherals(withServices: nil, options: nil)
        
        // Auto-stop scanning after 15 seconds
        Task {
            try? await Task.sleep(nanoseconds: 15_000_000_000)
            guard !Task.isCancelled else { return }
            self.stopScanning()
        }
    }
    
    func stopScanning() {
        isScanning = false
        centralManager.stopScan()
    }
    
    func connect(to peripheral: CBPeripheral) {
        stopScanning()
        connectedPeripheral = peripheral
        connectedPeripheral?.delegate = self
        centralManager.connect(peripheral, options: nil)
    }
    
    func disconnect() {
        if let peripheral = connectedPeripheral {
            centralManager.cancelPeripheralConnection(peripheral)
        }
    }
    
    func sendData(_ string: String) {
        guard isConnected, let peripheral = connectedPeripheral, let characteristic = writeCharacteristic else {
            return
        }
        if let data = string.data(using: .utf8) {
            let writeType: CBCharacteristicWriteType = characteristic.properties.contains(.writeWithoutResponse) ? .withoutResponse : .withResponse
            peripheral.writeValue(data, for: characteristic, type: writeType)
            print("Sent BLE: \(string)")
        }
    }
    
    // MARK: - CBCentralManagerDelegate
    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        if central.state == .poweredOn {
            startScanning()
        } else {
            isConnected = false
            isScanning = false
        }
    }
    
    func centralManager(_ central: CBCentralManager, didDiscover peripheral: CBPeripheral, advertisementData: [String : Any], rssi RSSI: NSNumber) {
        if !discoveredPeripherals.contains(where: { $0.identifier == peripheral.identifier }) {
            if let name = peripheral.name, !name.isEmpty {
                discoveredPeripherals.append(peripheral)
            }
        }
    }
    
    func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        isConnected = true
        peripheral.discoverServices([serviceUUID])
    }
    
    func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral, error: Error?) {
        isConnected = false
        connectedPeripheral = nil
    }
    
    func centralManager(_ central: CBCentralManager, didDisconnectPeripheral peripheral: CBPeripheral, error: Error?) {
        isConnected = false
        connectedPeripheral = nil
        writeCharacteristic = nil
        startScanning() // Restart scanning to reconnect
    }
    
    // MARK: - CBPeripheralDelegate
    func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        guard let services = peripheral.services else { return }
        for service in services {
            if service.uuid == serviceUUID {
                peripheral.discoverCharacteristics([characteristicUUID], for: service)
            }
        }
    }
    
    func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?) {
        guard let characteristics = service.characteristics else { return }
        for characteristic in characteristics {
            if characteristic.uuid == characteristicUUID {
                writeCharacteristic = characteristic
                print("Found write characteristic FFE1")
            }
        }
    }
}
"""
    with open("MapNavigationApp/BLEManager.swift", "w", encoding="utf-8") as f:
        f.write(content)
    print("Wrote BLEManager.swift")

def write_navigation_manager():
    content = """import Foundation
import CoreLocation
import MapKit

// API Response Models
struct RouteResponse: Codable {
    let routes: [Route]?
}

struct Route: Codable {
    let legs: [Leg]?
    let distanceMeters: Int?
    let duration: String?
}

struct Leg: Codable {
    let steps: [Step]?
}

struct Step: Codable {
    let distanceMeters: Int?
    let navigationInstruction: NavigationInstruction?
    let startLocation: LocationWrapper?
    let endLocation: LocationWrapper?
}

struct NavigationInstruction: Codable {
    let maneuver: String?
    let instructions: String?
}

struct LocationWrapper: Codable {
    let latLng: LatLng?
}

struct LatLng: Codable {
    let latitude: Double?
    let longitude: Double?
}

@MainActor
class NavigationManager: NSObject, ObservableObject, CLLocationManagerDelegate {
    @Published var isNavigating = false
    @Published var currentInstruction = "Chua bat dau"
    @Published var nextStreet = "..."
    @Published var distanceToNextTurn: Double = 0.0 // in meters
    @Published var routeSteps: [Step]?
    @Published var currentStepIndex = 0
    @Published var destinationName = ""
    
    @Published var isResolvingURL = false
    @Published var errorMessage: String? = nil
    
    private var locationManager: CLLocationManager!
    private var bleManager: BLEManager?
    private var destinationCoordinate: CLLocationCoordinate2D?
    private var lastSentTime: Date = Date.distantPast
    
    private var apiKey: String = ""
    private var offRouteCount = 0
    private var lastRecalculateTime: Date = Date.distantPast
    
    init(bleManager: BLEManager) {
        super.init()
        self.bleManager = bleManager
        self.locationManager = CLLocationManager()
        self.locationManager.delegate = self
        self.locationManager.desiredAccuracy = kCLLocationAccuracyBestForNavigation
        self.locationManager.distanceFilter = 2.0 // updates every 2 meters
        
        self.locationManager.requestWhenInUseAuthorization()
        self.locationManager.requestAlwaysAuthorization()
    }
    
    func startNavigation(destination: CLLocationCoordinate2D, name: String, apiKey: String) async {
        self.destinationCoordinate = destination
        self.destinationName = name
        self.apiKey = apiKey
        self.offRouteCount = 0
        
        guard let userLoc = locationManager.location else {
            self.errorMessage = "Khong lay duoc vi tri GPS hien tai."
            return
        }
        
        let success = await fetchGoogleMotorbikeRoute(from: userLoc.coordinate, to: destination, apiKey: apiKey)
        if success {
            self.isNavigating = true
            self.currentStepIndex = 0
            self.locationManager.startUpdatingLocation()
            self.errorMessage = nil
            self.processCurrentStep()
        }
    }
    
    func stopNavigation() {
        self.isNavigating = false
        self.locationManager.stopUpdatingLocation()
        self.routeSteps = nil
        self.currentInstruction = "Da dung chi duong"
        self.nextStreet = "..."
        self.distanceToNextTurn = 0.0
        
        // Send turnType = 0 (straight/idle)
        self.bleManager?.sendData("0;--;Dung dan duong")
    }
    
    // Resolves Google Maps link and starts navigation
    func handleGoogleMapsURL(_ urlString: String, apiKey: String) async {
        self.isResolvingURL = true
        self.errorMessage = nil
        
        // 1. Resolve redirect to get the long URL
        guard let resolvedURLString = await resolveShortenedURL(urlString) else {
            self.isResolvingURL = false
            self.errorMessage = "Khong the giai ma link Google Maps."
            return
        }
        
        print("Resolved Google Maps URL: \\(resolvedURLString)")
        
        // 2. Parse Coordinates directly from URL
        var destinationCoord = extractCoordinates(from: resolvedURLString)
        var name = "Diem den tu GMap"
        
        // 3. Fallback: Parse place name and geocode
        if destinationCoord == nil {
            if let placeName = extractPlaceName(from: resolvedURLString) {
                name = placeName
                destinationCoord = await geocodePlaceName(placeName)
            }
        }
        
        self.isResolvingURL = false
        
        if let coord = destinationCoord {
            await startNavigation(destination: coord, name: name, apiKey: apiKey)
        } else {
            self.errorMessage = "Khong tim thay toa do diem den."
        }
    }
    
    // MARK: - Private Helpers
    
    private func resolveShortenedURL(_ shortURLString: String) async -> String? {
        guard let url = URL(string: shortURLString.trimmingCharacters(in: .whitespacesAndNewlines)) else { return nil }
        var request = URLRequest(url: url)
        request.httpMethod = "HEAD"
        do {
            let (_, response) = try await URLSession.shared.data(for: request)
            if let httpResponse = response as? HTTPURLResponse {
                return httpResponse.url?.absoluteString
            }
        } catch {
            print("Failed to resolve URL: \\(error)")
        }
        
        // Fallback with GET if HEAD fails
        var getRequest = URLRequest(url: url)
        getRequest.httpMethod = "GET"
        do {
            let (_, response) = try await URLSession.shared.data(for: getRequest)
            if let httpResponse = response as? HTTPURLResponse {
                return httpResponse.url?.absoluteString
            }
        } catch {
            print("Failed GET fallback: \\(error)")
        }
        return shortURLString // Return original if redirect resolving fails
    }
    
    private func extractCoordinates(from urlString: String) -> CLLocationCoordinate2D? {
        // Pattern 1: @lat,lng
        if let regex = try? NSRegularExpression(pattern: "@(-?\\\\d+\\\\.\\\\d+),(-?\\\\d+\\\\.\\\\d+)", options: []),
           let match = regex.firstMatch(in: urlString, options: [], range: NSRange(urlString.startIndex..., in: urlString)) {
            if let latRange = Range(match.range(at: 1), in: urlString),
               let lngRange = Range(match.range(at: 2), in: urlString),
               let lat = Double(urlString[latRange]),
               let lng = Double(urlString[lngRange]) {
                return CLLocationCoordinate2D(latitude: lat, longitude: lng)
            }
        }
        // Pattern 2: dir/Origin/DestinationCoordinates
        if let regex = try? NSRegularExpression(pattern: "/dir/[^/]*/(-?\\\\d+\\\\.\\\\d+),(-?\\\\d+\\\\.\\\\d+)", options: []),
           let match = regex.firstMatch(in: urlString, options: [], range: NSRange(urlString.startIndex..., in: urlString)) {
            if let latRange = Range(match.range(at: 1), in: urlString),
               let lngRange = Range(match.range(at: 2), in: urlString),
               let lat = Double(urlString[latRange]),
               let lng = Double(urlString[lngRange]) {
                return CLLocationCoordinate2D(latitude: lat, longitude: lng)
            }
        }
        return nil
    }
    
    private func extractPlaceName(from urlString: String) -> String? {
        // Extract string between "/place/" and next "/" or "?"
        guard let range = urlString.range(of: "/place/") else { return nil }
        let subStr = urlString[range.upperBound...]
        let endIdx = subStr.firstIndex(of: "/") ?? subStr.firstIndex(of: "?") ?? subStr.endIndex
        let rawName = String(subStr[..<endIdx])
        
        // URL Decode
        return rawName.removingPercentEncoding?.replacingOccurrences(of: "+", with: " ")
    }
    
    private func geocodePlaceName(_ name: String) async -> CLLocationCoordinate2D? {
        let geocoder = CLGeocoder()
        do {
            let placemarks = try await geocoder.geocodeAddressString(name)
            return placemarks.first?.location?.coordinate
        } catch {
            print("Geocoding failed for: \\(name). Error: \\(error)")
            return nil
        }
    }
    
    private func fetchGoogleMotorbikeRoute(from origin: CLLocationCoordinate2D, to dest: CLLocationCoordinate2D, apiKey: String) async -> Bool {
        let url = URL(string: "https://routes.googleapis.com/directions/v2:computeRoutes")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(apiKey, forHTTPHeaderField: "X-Goog-Api-Key")
        request.setValue("routes.legs.steps,routes.distanceMeters,routes.duration", forHTTPHeaderField: "X-Goog-FieldMask")
        
        let jsonBody: [String: Any] = [
            "origin": [
                "location": [
                    "latLng": [
                        "latitude": origin.latitude,
                        "longitude": origin.longitude
                    ]
                ]
            ],
            "destination": [
                "location": [
                    "latLng": [
                        "latitude": dest.latitude,
                        "longitude": dest.longitude
                    ]
                ]
            ],
            "travelMode": "TWO_WHEELER",
            "routingPreference": "TRAFFIC_AWARE",
            "languageCode": "vi-VN"
        ]
        
        do {
            let bodyData = try JSONSerialization.data(withJSONObject: jsonBody, options: [])
            request.httpBody = bodyData
            
            let (data, response) = try await URLSession.shared.data(for: request)
            
            if let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode != 200 {
                let errStr = String(data: data, encoding: .utf8) ?? "Unknown error"
                print("Google API Error (\\(httpResponse.statusCode)): \\(errStr)")
                self.errorMessage = "Google API tra ve loi \\(httpResponse.statusCode). Kiem tra lai API Key."
                return false
            }
            
            let decoder = JSONDecoder()
            let routeResponse = try decoder.decode(RouteResponse.self, from: data)
            
            guard let steps = routeResponse.routes?.first?.legs?.first?.steps, !steps.isEmpty else {
                self.errorMessage = "Khong tim thay cac buoc huong dan tuyen duong."
                return false
            }
            
            self.routeSteps = steps
            return true
            
        } catch {
            print("Failed to fetch Google route: \\(error)")
            self.errorMessage = "Loi ket noi mang: \\(error.localizedDescription)"
            return false
        }
    }
    
    private func processCurrentStep() {
        guard let steps = routeSteps, currentStepIndex < steps.count else { return }
        let step = steps[currentStepIndex]
        
        // Extract instructions and street name
        let instructionText = step.navigationInstruction?.instructions ?? "Di thang"
        
        self.currentInstruction = instructionText
        self.nextStreet = extractStreetName(from: instructionText)
        
        sendBLEUpdate()
    }
    
    private func extractStreetName(from instruction: String) -> String {
        let lowercase = instruction.lowercased()
        let prefixes = ["tai duong ", "vao duong ", "tai ", "vao ", "huong ve "]
        
        for prefix in prefixes {
            if let range = lowercase.range(of: prefix) {
                let street = instruction[range.upperBound...]
                return String(street).trimmingCharacters(in: .whitespacesAndNewlines)
            }
        }
        return instruction
    }
    
    private func parseManeuver(_ maneuver: String) -> Int {
        switch maneuver {
        case "TURN_LEFT", "TURN_SHARP_LEFT":
            return 1
        case "TURN_RIGHT", "TURN_SHARP_RIGHT":
            return 2
        case "TURN_SLIGHT_LEFT":
            return 3
        case "TURN_SLIGHT_RIGHT":
            return 4
        case "UTURN_LEFT", "UTURN_RIGHT":
            return 5
        case "ROUNDABOUT", "ROUNDABOUT_LEFT", "ROUNDABOUT_RIGHT", "RAMP_LEFT", "RAMP_RIGHT":
            return 6
        case "ARRIVE":
            return 7
        default:
            return 0
        }
    }
    
    private func sendBLEUpdate(isLastStep: Bool = false) {
        let now = Date()
        guard isLastStep || now.timeIntervalSince(lastSentTime) >= 1.0 else { return }
        lastSentTime = now
        
        guard let steps = routeSteps, currentStepIndex < steps.count else { return }
        let step = steps[currentStepIndex]
        
        let maneuver = isLastStep ? "ARRIVE" : (step.navigationInstruction?.maneuver ?? "STRAIGHT")
        let turnCode = parseManeuver(maneuver)
        
        let distStr: String
        if distanceToNextTurn >= 1000.0 {
            distStr = String(format: "%.1fkm", distanceToNextTurn / 1000.0)
        } else {
            distStr = String(format: "%.0fm", distanceToNextTurn)
        }
        
        let prefix = "\\(turnCode);\\(distStr);"
        let maxStreetLength = max(1, 20 - prefix.count)
        let strippedStreet = bleSafeText(nextStreet, maxLength: maxStreetLength)
        
        let message = "\\(prefix)\\(strippedStreet.isEmpty ? "-" : strippedStreet)"
        bleManager?.sendData(message)
    }
    
    private func sendArrivedUpdate() {
        let prefix = "7;Da den;"
        let place = bleSafeText(destinationName, maxLength: max(1, 20 - prefix.count))
        bleManager?.sendData("\\(prefix)\\(place.isEmpty ? "-" : place)")
    }

    private func bleSafeText(_ text: String, maxLength: Int) -> String {
        let ascii = text.strippingDiacritics
            .replacingOccurrences(of: ";", with: " ")
            .replacingOccurrences(of: "[^A-Za-z0-9 .,/\\\\-]", with: "", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return String(ascii.prefix(maxLength))
    }
    
    private func recalculateRoute() {
        guard let dest = destinationCoordinate, !apiKey.isEmpty else { return }
        guard let userLoc = locationManager.location else { return }
        
        Task {
            let success = await fetchGoogleMotorbikeRoute(from: userLoc.coordinate, to: dest, apiKey: apiKey)
            if success {
                self.currentStepIndex = 0
                self.errorMessage = nil
                self.processCurrentStep()
            }
        }
    }
    
    private func distanceToSegment(p: CLLocationCoordinate2D, a: CLLocationCoordinate2D, b: CLLocationCoordinate2D) -> Double {
        let latMid = (a.latitude + b.latitude) / 2.0
        let mPerDegLat = 111139.0
        let mPerDegLon = 111139.0 * cos(latMid * .pi / 180.0)
        
        let ax = 0.0
        let ay = 0.0
        
        let bx = (b.longitude - a.longitude) * mPerDegLon
        let by = (b.latitude - a.latitude) * mPerDegLat
        
        let px = (p.longitude - a.longitude) * mPerDegLon
        let py = (p.latitude - a.latitude) * mPerDegLat
        
        let dx = bx - ax
        let dy = by - ay
        
        let segmentLengthSquared = dx*dx + dy*dy
        if segmentLengthSquared == 0 {
            return sqrt(px*px + py*py)
        }
        
        var t = ((px - ax) * dx + (py - ay) * dy) / segmentLengthSquared
        t = max(0.0, min(1.0, t))
        
        let closestX = ax + t * dx
        let closestY = ay + t * dy
        
        let distanceX = px - closestX
        let distanceY = py - closestY
        
        return sqrt(distanceX*distanceX + distanceY*distanceY)
    }
    
    // MARK: - CLLocationManagerDelegate
    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard isNavigating, let userLoc = locations.last, let steps = routeSteps else { return }
        
        // 1. Off-Route Check
        if currentStepIndex < steps.count {
            let currentStep = steps[currentStepIndex]
            if let startLat = currentStep.startLocation?.latLng?.latitude,
               let startLng = currentStep.startLocation?.latLng?.longitude,
               let endLat = currentStep.endLocation?.latLng?.latitude,
               let endLng = currentStep.endLocation?.latLng?.longitude {
                
                let startCoord = CLLocationCoordinate2D(latitude: startLat, longitude: startLng)
                let endCoord = CLLocationCoordinate2D(latitude: endLat, longitude: endLng)
                let distToSegment = distanceToSegment(p: userLoc.coordinate, a: startCoord, b: endCoord)
                
                if distToSegment > 65.0 {
                    offRouteCount += 1
                    print("Off-route count: \\(offRouteCount) (distance: \\(distToSegment)m)")
                    
                    if offRouteCount >= 3 {
                        let now = Date()
                        if now.timeIntervalSince(lastRecalculateTime) > 15.0 {
                            lastRecalculateTime = now
                            offRouteCount = 0
                            
                            self.currentInstruction = "Di sai duong, dang tinh lai..."
                            self.nextStreet = "..."
                            self.bleManager?.sendData("0;--;Dang tinh lai...")
                            
                            recalculateRoute()
                            return
                        }
                    }
                } else {
                    offRouteCount = 0
                }
            }
        }
        
        // 2. Step Progression
        let nextStepIndex = currentStepIndex + 1
        if nextStepIndex < steps.count {
            let nextStep = steps[nextStepIndex]
            if let turnLat = nextStep.startLocation?.latLng?.latitude,
               let turnLng = nextStep.startLocation?.latLng?.longitude {
                
                let turnLocation = CLLocation(latitude: turnLat, longitude: turnLng)
                let distance = userLoc.distance(from: turnLocation)
                
                self.distanceToNextTurn = distance
                
                if distance < 15.0 {
                    self.currentStepIndex = nextStepIndex
                    self.processCurrentStep()
                } else {
                    self.sendBLEUpdate()
                }
            }
        } else {
            // Last step: Heading to final destination
            if let destLat = destinationCoordinate?.latitude,
               let destLng = destinationCoordinate?.longitude {
                let destLocation = CLLocation(latitude: destLat, longitude: destLng)
                let distance = userLoc.distance(from: destLocation)
                
                self.distanceToNextTurn = distance
                
                if distance < 20.0 {
                    self.stopNavigation()
                    self.sendArrivedUpdate()
                } else {
                    self.sendBLEUpdate(isLastStep: true)
                }
            }
        }
    }
    
    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        print("GPS tracking failed: \\(error)")
    }
}

extension String {
    var strippingDiacritics: String {
        let mutableString = NSMutableString(string: self) as CFMutableString
        CFStringTransform(mutableString, nil, kCFStringTransformStripDiacritics, false)
        var result = mutableString as String
        result = result.replacingOccurrences(of: "đ", with: "d")
        result = result.replacingOccurrences(of: "Đ", with: "D")
        return result
    }
}
"""
    with open("MapNavigationApp/NavigationManager.swift", "w", encoding="utf-8") as f:
        f.write(content)
    print("Wrote NavigationManager.swift")

def write_content_view():
    content = """import SwiftUI
import CoreBluetooth
import CoreLocation
import UIKit

@MainActor
struct ContentView: View {
    @StateObject private var bleManager = BLEManager()
    @StateObject private var navManager: NavigationManager
    
    @State private var googleAPIKey: String = ""
    @State private var inputDestination: String = ""
    @State private var showSettings = false
    @State private var showBLEScanner = false
    @State private var clipboardLink = ""
    @State private var showClipboardPrompt = false
    @State private var showSplash = true
    
    init() {
        let ble = BLEManager()
        _bleManager = StateObject(wrappedValue: ble)
        _navManager = StateObject(wrappedValue: NavigationManager(bleManager: ble))
    }
    
    var body: some View {
        ZStack {
            if showSplash {
                SplashView(showSplash: $showSplash)
                    .transition(.opacity)
            } else {
                NavigationView {
                    ZStack {
                        Color(red: 0.08, green: 0.09, blue: 0.12)
                            .ignoresSafeArea()
                
                VStack(spacing: 20) {
                    HStack {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Thiet Bi Chi Duong")
                                .font(.headline)
                                .foregroundColor(.white)
                            
                            HStack {
                                Circle()
                                    .fill(bleManager.isConnected ? Color.green : Color.red)
                                    .frame(width: 8, height: 8)
                                Text(bleManager.isConnected ? "Da ket noi BLE" : "Mat ket noi")
                                    .font(.subheadline)
                                    .foregroundColor(.gray)
                            }
                        }
                        
                        Spacer()
                        
                        Button(action: {
                            showBLEScanner = true
                            bleManager.startScanning()
                        }) {
                            Text(bleManager.isConnected ? "Doi Thiet Bi" : "Ket Noi")
                                .font(.subheadline)
                                .bold()
                                .foregroundColor(.white)
                                .padding(.horizontal, 16)
                                .padding(.vertical, 8)
                                .background(
                                    RoundedRectangle(cornerRadius: 15)
                                        .fill(bleManager.isConnected ? Color.blue.opacity(0.3) : Color.blue)
                                )
                        }
                    }
                    .padding()
                    .background(
                        RoundedRectangle(cornerRadius: 20)
                            .fill(Color(red: 0.14, green: 0.16, blue: 0.22))
                    )
                    
                    VStack(spacing: 16) {
                        if navManager.isNavigating {
                            Text("DANG DAN DUONG XE MAY")
                                .font(.caption)
                                .bold()
                                .foregroundColor(.blue)
                                .padding(.horizontal, 12)
                                .padding(.vertical, 4)
                                .background(Capsule().fill(Color.blue.opacity(0.15)))
                            
                            VStack(spacing: 12) {
                                Image(systemName: getArrowSystemName(navManager.currentInstruction))
                                    .font(.system(size: 60, weight: .bold))
                                    .foregroundColor(.blue)
                                    .transition(.scale)
                                
                                Text(String(format: "Con %.0f met", navManager.distanceToNextTurn))
                                    .font(.system(size: 32, weight: .bold))
                                    .foregroundColor(.white)
                                
                                Text(navManager.currentInstruction)
                                    .font(.title3)
                                    .multilineTextAlignment(.center)
                                    .foregroundColor(.white)
                                    .padding(.horizontal)
                                
                                Text("Sap vao: \\(navManager.nextStreet)")
                                    .font(.headline)
                                    .foregroundColor(.gray)
                            }
                            .padding(.vertical)
                            
                            Button(action: {
                                navManager.stopNavigation()
                            }) {
                                HStack {
                                    Image(systemName: "stop.fill")
                                    Text("Dung dan duong")
                                }
                                .font(.headline)
                                .foregroundColor(.white)
                                .frame(maxWidth: .infinity)
                                .padding()
                                .background(RoundedRectangle(cornerRadius: 15).fill(Color.red))
                            }
                            .padding(.horizontal)
                        } else {
                            VStack(spacing: 15) {
                                Image(systemName: "map.fill")
                                    .font(.system(size: 50))
                                    .foregroundColor(.gray.opacity(0.6))
                                
                                Text("San sang dan duong")
                                    .font(.title3)
                                    .bold()
                                    .foregroundColor(.white)
                                
                                Text("Hay tim kiem dia diem ben duoi, hoac copy link tu Google Maps de dong bo.")
                                    .font(.subheadline)
                                    .foregroundColor(.gray)
                                    .multilineTextAlignment(.center)
                                    .padding(.horizontal)
                            }
                            .padding(.vertical, 40)
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .background(
                        RoundedRectangle(cornerRadius: 24)
                            .fill(Color(red: 0.12, green: 0.13, blue: 0.18))
                    )
                    
                    VStack(spacing: 12) {
                        HStack {
                            Image(systemName: "magnifyingglass")
                                .foregroundColor(.gray)
                            TextField("Tim dia diem hoac dan link GMap...", text: $inputDestination)
                                .foregroundColor(.white)
                                .keyboardType(.default)
                                .autocapitalization(.none)
                            
                            if !inputDestination.isEmpty {
                                Button(action: { inputDestination = "" }) {
                                    Image(systemName: "xmark.circle.fill")
                                        .foregroundColor(.gray)
                                }
                            }
                        }
                        .padding()
                        .background(RoundedRectangle(cornerRadius: 16).fill(Color(red: 0.14, green: 0.16, blue: 0.22)))
                        
                        Button(action: {
                            Task {
                                await startManualRouting()
                            }
                        }) {
                            Text("Tinh Toan Lo Trinh Xe May")
                                .font(.headline)
                                .foregroundColor(.white)
                                .frame(maxWidth: .infinity)
                                .padding()
                                .background(
                                    RoundedRectangle(cornerRadius: 16)
                                        .fill(inputDestination.isEmpty ? Color.gray.opacity(0.3) : Color.blue)
                                )
                        }
                        .disabled(inputDestination.isEmpty)
                    }
                    
                    if navManager.isResolvingURL {
                        ProgressView("Dang giai ma link Google Maps...")
                            .progressViewStyle(CircularProgressViewStyle(tint: .white))
                            .foregroundColor(.white)
                    }
                    
                    if let error = navManager.errorMessage {
                        Text(error)
                            .font(.caption)
                            .foregroundColor(.red)
                            .multilineTextAlignment(.center)
                            .padding()
                    }
                    
                    Spacer()
                }
                .padding()
            }
            .navigationTitle("GMap BLE Companion")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(action: { showSettings = true }) {
                        Image(systemName: "gearshape.fill")
                            .foregroundColor(.white)
                    }
                }
            }
            .onAppear {
                loadAPIKey()
                checkClipboardForGoogleMapsLink()
            }
            .sheet(isPresented: $showSettings) {
                SettingsView(googleAPIKey: $googleAPIKey, showSettings: $showSettings)
            }
            .sheet(isPresented: $showBLEScanner) {
                BLEScannerView(bleManager: bleManager, isPresented: $showBLEScanner)
            }
            .alert(isPresented: $showClipboardPrompt) {
                Alert(
                    title: Text("Phat Hien Link Google Maps"),
                    message: Text("Ban co muon bat dau lo trinh xe may den dia diem nay tu khay nho tam?"),
                    primaryButton: .default(Text("Dong Y")) {
                        Task {
                            await navManager.handleGoogleMapsURL(clipboardLink, apiKey: googleAPIKey)
                        }
                    },
                    secondaryButton: .cancel(Text("Bo qua"))
                )
            }
        }
        .preferredColorScheme(.dark)
        .onOpenURL { url in
            handleIncomingURL(url)
        }
        }
    }
}
    
    private func loadAPIKey() {
        googleAPIKey = UserDefaults.standard.string(forKey: "google_api_key") ?? ""
    }
    
    private func checkClipboardForGoogleMapsLink() {
        if let clipboardString = UIPasteboard.general.string {
            if clipboardString.contains("maps.app.goo.gl") || clipboardString.contains("google.com/maps") {
                clipboardLink = clipboardString
                showClipboardPrompt = true
                UIPasteboard.general.string = ""
            }
        }
    }
    
    private func handleIncomingURL(_ url: URL) {
        let urlString = url.absoluteString
        let prefix = "mapnavcomp://"
        guard urlString.hasPrefix(prefix) else { return }
        
        var targetLink = String(urlString.dropFirst(prefix.count))
        if targetLink.hasPrefix("url?link=") {
            targetLink = String(targetLink.dropFirst("url?link=".count))
        }
        
        guard let decodedLink = targetLink.removingPercentEncoding?.trimmingCharacters(in: .whitespacesAndNewlines) else { return }
        
        var finalLink = decodedLink
        if !finalLink.hasPrefix("http://") && !finalLink.hasPrefix("https://") {
            finalLink = "https://" + finalLink
        }
        
        if finalLink.contains("maps.app.goo.gl") || finalLink.contains("google.com/maps") {
            Task {
                await navManager.handleGoogleMapsURL(finalLink, apiKey: googleAPIKey)
            }
        }
    }
    
    private func startManualRouting() async {
        if googleAPIKey.isEmpty {
            navManager.errorMessage = "Vui long nhap Google API Key trong phan Cai Dat."
            return
        }
        
        if inputDestination.contains("maps.app.goo.gl") || inputDestination.contains("google.com/maps") {
            await navManager.handleGoogleMapsURL(inputDestination, apiKey: googleAPIKey)
        } else {
            let geocoder = CLGeocoder()
            do {
                let placemarks = try await geocoder.geocodeAddressString(inputDestination)
                if let coord = placemarks.first?.location?.coordinate {
                    await navManager.startNavigation(destination: coord, name: inputDestination, apiKey: googleAPIKey)
                } else {
                    navManager.errorMessage = "Khong tim thay vi tri cua dia chi nay."
                }
            } catch {
                navManager.errorMessage = "Loi tim kiem: \\(error.localizedDescription)"
            }
        }
    }
    
    private func getArrowSystemName(_ instruction: String) -> String {
        let lowercase = instruction.lowercased()
        if lowercase.contains("trai") || lowercase.contains("left") {
            return "arrow.turn.up.left"
        } else if lowercase.contains("phai") || lowercase.contains("right") {
            return "arrow.turn.up.right"
        } else if lowercase.contains("quay dau") || lowercase.contains("u-turn") {
            return "arrow.uturn.left"
        } else if lowercase.contains("vong xuyen") || lowercase.contains("roundabout") {
            return "arrow.3.trianglepath"
        } else {
            return "arrow.up"
        }
    }
}

@MainActor
struct SettingsView: View {
    @Binding var googleAPIKey: String
    @Binding var showSettings: Bool
    
    var body: some View {
        NavigationView {
            ZStack {
                Color(red: 0.08, green: 0.09, blue: 0.12).ignoresSafeArea()
                
                VStack(spacing: 20) {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Google Maps API Key")
                            .font(.headline)
                            .foregroundColor(.white)
                        
                        TextField("Nhap API Key cua ban...", text: $googleAPIKey)
                            .padding()
                            .background(RoundedRectangle(cornerRadius: 12).fill(Color(red: 0.14, green: 0.16, blue: 0.22)))
                            .foregroundColor(.white)
                            .autocapitalization(.none)
                            .disableAutocorrection(true)
                        
                        Text("Ban can dang ky API Key tren Google Cloud Console va bat dich vu Routes API de su dung che do dan duong xe may.")
                            .font(.caption)
                            .foregroundColor(.gray)
                    }
                    
                    Button(action: {
                        UserDefaults.standard.set(googleAPIKey, forKey: "google_api_key")
                        showSettings = false
                    }) {
                        Text("Luu Cai Dat")
                            .font(.headline)
                            .foregroundColor(.white)
                            .frame(maxWidth: .infinity)
                            .padding()
                            .background(RoundedRectangle(cornerRadius: 15).fill(Color.blue))
                    }
                    
                    Spacer()
                }
                .padding()
            }
            .navigationTitle("Cai Dat App")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Huy") {
                        showSettings = false
                    }
                    .foregroundColor(.white)
                }
            }
        }
    }
}

@MainActor
struct BLEScannerView: View {
    @ObservedObject var bleManager: BLEManager
    @Binding var isPresented: Bool
    
    var body: some View {
        NavigationView {
            ZStack {
                Color(red: 0.08, green: 0.09, blue: 0.12).ignoresSafeArea()
                
                VStack {
                    if bleManager.discoveredPeripherals.isEmpty {
                        VStack(spacing: 15) {
                            ProgressView()
                                .progressViewStyle(CircularProgressViewStyle(tint: .white))
                            Text("Dang quet cac thiet bi BLE lan can...")
                                .foregroundColor(.gray)
                        }
                        .padding(.top, 40)
                    } else {
                        List(bleManager.discoveredPeripherals, id: \\.identifier) { peripheral in
                            HStack {
                                VStack(alignment: .leading) {
                                    Text(peripheral.name ?? "Thiet bi khong ten")
                                        .font(.headline)
                                        .foregroundColor(.white)
                                    Text("UUID: \\(peripheral.identifier.uuidString.prefix(12))...")
                                        .font(.caption)
                                        .foregroundColor(.gray)
                                }
                                Spacer()
                                
                                Button(action: {
                                    bleManager.connect(to: peripheral)
                                    isPresented = false
                                }) {
                                    Text("Ket Noi")
                                        .font(.subheadline)
                                        .bold()
                                        .foregroundColor(.white)
                                        .padding(.horizontal, 14)
                                        .padding(.vertical, 6)
                                        .background(Capsule().fill(Color.blue))
                                }
                            }
                            .listRowBackground(Color(red: 0.14, green: 0.16, blue: 0.22))
                        }
                        .background(Color.clear)
                        .hideScrollBackground()
                    }
                    Spacer()
                }
                .padding()
            }
            .navigationTitle("Quet Bluetooth")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Dong") {
                        bleManager.stopScanning()
                        isPresented = false
                    }
                    .foregroundColor(.white)
                }
            }
        }
    }
}

@MainActor
struct SplashView: View {
    @Binding var showSplash: Bool
    
    var body: some View {
        ZStack {
            Color(red: 0.08, green: 0.09, blue: 0.12)
                .ignoresSafeArea()
            
            VStack(spacing: 20) {
                if let uiImage = decodeBase64Image(brandLogoBase64) {
                    Image(uiImage: uiImage)
                        .resizable()
                        .scaledToFit()
                        .frame(width: 120, height: 120)
                        .clipShape(Circle())
                        .shadow(color: .green.opacity(0.6), radius: 15)
                } else {
                    Image(systemName: "eye.fill")
                        .font(.system(size: 80))
                        .foregroundColor(.green)
                }
                
                Text("GMap Navi Companion")
                    .font(.title3)
                    .bold()
                    .foregroundColor(.white)
            }
        }
        .onAppear {
            Task {
                try? await Task.sleep(nanoseconds: 2_000_000_000)
                guard !Task.isCancelled else { return }
                withAnimation(.easeOut(duration: 0.5)) {
                    showSplash = false
                }
            }
        }
    }
    
    private func decodeBase64Image(_ base64String: String) -> UIImage? {
        guard let data = Data(base64Encoded: base64String) else { return nil }
        return UIImage(data: data)
    }
}

extension View {
    @ViewBuilder
    func hideScrollBackground() -> some View {
        if #available(iOS 16.0, *) {
            self.scrollContentBackground(.hidden)
        } else {
            self
        }
    }
}

let brandLogoBase64 = "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"
"""
    with open("MapNavigationApp/ContentView.swift", "w", encoding="utf-8") as f:
        f.write(content)
    print("Wrote ContentView.swift")

def write_info_plist():
    content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleDevelopmentRegion</key>
	<string>$(DEVELOPMENT_LANGUAGE)</string>
	<key>CFBundleExecutable</key>
	<string>$(EXECUTABLE_NAME)</string>
	<key>CFBundleIdentifier</key>
	<string>$(PRODUCT_BUNDLE_IDENTIFIER)</string>
	<key>CFBundleInfoDictionaryVersion</key>
	<string>6.0</string>
	<key>CFBundleName</key>
	<string>$(PRODUCT_NAME)</string>
	<key>CFBundlePackageType</key>
	<string>$(PRODUCT_BUNDLE_PACKAGE_TYPE)</string>
	<key>CFBundleShortVersionString</key>
	<string>1.0</string>
	<key>CFBundleVersion</key>
	<string>1</string>
	<key>LSRequiresIPhoneOS</key>
	<true/>
	<key>NSBluetoothAlwaysUsageDescription</key>
	<string>Ung dung can su dung Bluetooth de gui thong tin chi duong toi thiet bi gan tren xe may.</string>
	<key>NSBluetoothPeripheralUsageDescription</key>
	<string>Ung dung can su dung Bluetooth de ket noi voi thiet bi gan tren xe.</string>
	<key>NSLocationWhenInUseUsageDescription</key>
	<string>Ung dung can su dung vi tri GPS cua ban de cap nhat khoang cach va huong di chuyen theo thoi gian thuc.</string>
	<key>NSLocationAlwaysAndWhenInUseUsageDescription</key>
	<string>Ung dung can truy cap vi tri nen de tiep tuc chi duong khi ban bo dien thoai vao tui quan.</string>
	<key>UIBackgroundModes</key>
	<array>
		<string>location</string>
		<string>bluetooth-central</string>
	</array>
	<key>UIApplicationSceneManifest</key>
	<dict>
		<key>UIApplicationSupportsMultipleScenes</key>
		<false/>
	</dict>
	<key>UILaunchScreen</key>
	<dict/>
	<key>UISupportedInterfaceOrientations</key>
	<array>
		<string>UIInterfaceOrientationPortrait</string>
	</array>
	<key>CFBundleURLTypes</key>
	<array>
		<dict>
			<key>CFBundleURLSchemes</key>
			<array>
				<string>mapnavcomp</string>
			</array>
			<key>CFBundleURLName</key>
			<string>com.hanshincode.mapnavigationapp</string>
		</dict>
	</array>
</dict>
</plist>
"""
    with open("MapNavigationApp/Info.plist", "w", encoding="utf-8") as f:
        f.write(content)
    print("Wrote Info.plist")

def write_assets():
    import os
    os.makedirs("MapNavigationApp/Assets.xcassets/AppIcon.appiconset", exist_ok=True)
    content = """{
  "images" : [
    {
      "idiom" : "universal",
      "platform" : "ios",
      "size" : "1024x1024",
      "filename" : "icon_1024.png",
      "scale" : "1x"
    }
  ],
  "info" : {
    "author" : "xcode",
    "version" : 1
  }
}"""
    with open("MapNavigationApp/Assets.xcassets/AppIcon.appiconset/Contents.json", "w", encoding="utf-8") as f:
        f.write(content)
    print("Wrote Assets.xcassets")

def write_xcodeproj():
    content = """// !$*UTF8*$!
{
	archiveVersion = 1;
	classes = {
	};
	objectVersion = 56;
	objects = {

/* Begin PBXBuildFile section */
		4A4A00021A1A1A1A00000001 /* MapNavigationAppApp.swift in Sources */ = {isa = PBXBuildFile; fileRef = 4A4A00011A1A1A1A00000001 /* MapNavigationAppApp.swift */; };
		4A4A00041A1A1A1A00000002 /* ContentView.swift in Sources */ = {isa = PBXBuildFile; fileRef = 4A4A00031A1A1A1A00000002 /* ContentView.swift */; };
		4A4A00061A1A1A1A00000003 /* BLEManager.swift in Sources */ = {isa = PBXBuildFile; fileRef = 4A4A00051A1A1A1A00000003 /* BLEManager.swift */; };
		4A4A00081A1A1A1A00000004 /* NavigationManager.swift in Sources */ = {isa = PBXBuildFile; fileRef = 4A4A00071A1A1A1A00000004 /* NavigationManager.swift */; };
		4A4A00221A1A1A1A00000005 /* Assets.xcassets in Resources */ = {isa = PBXBuildFile; fileRef = 4A4A00211A1A1A1A00000005 /* Assets.xcassets */; };
/* End PBXBuildFile section */

/* Begin PBXFileReference section */
		4A4A00011A1A1A1A00000001 /* MapNavigationAppApp.swift */ = {isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = MapNavigationAppApp.swift; sourceTree = "<group>"; };
		4A4A00031A1A1A1A00000002 /* ContentView.swift */ = {isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = ContentView.swift; sourceTree = "<group>"; };
		4A4A00051A1A1A1A00000003 /* BLEManager.swift */ = {isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = BLEManager.swift; sourceTree = "<group>"; };
		4A4A00071A1A1A1A00000004 /* NavigationManager.swift */ = {isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = NavigationManager.swift; sourceTree = "<group>"; };
		4A4A00091A1A1A1A00000005 /* Info.plist */ = {isa = PBXFileReference; lastKnownFileType = text.plist.xml; path = Info.plist; sourceTree = "<group>"; };
		4A4A00211A1A1A1A00000005 /* Assets.xcassets */ = {isa = PBXFileReference; lastKnownFileType = folder.assetcatalog; path = Assets.xcassets; sourceTree = "<group>"; };
		4A4A00101A1A1A1A00000006 /* MapNavigationApp.app */ = {isa = PBXFileReference; explicitFileType = wrapper.application; includeInIndex = 0; path = MapNavigationApp.app; sourceTree = BUILT_PRODUCTS_DIR; };
/* End PBXFileReference section */

/* Begin PBXFrameworksBuildPhase section */
		4A4A00201A1A1A1A00000007 /* Frameworks */ = {
			isa = PBXFrameworksBuildPhase;
			buildActionMask = 2147483647;
			files = (
			);
			runOnlyForDeploymentPostprocessing = 0;
		};
/* End PBXFrameworksBuildPhase section */

/* Begin PBXGroup section */
		4A4A00301A1A1A1A00000008 = {
			isa = PBXGroup;
			children = (
				4A4A00401A1A1A1A00000009 /* MapNavigationApp */,
				4A4A00101A1A1A1A0000000A /* Products */,
			);
			sourceTree = "<group>";
		};
		4A4A00401A1A1A1A00000009 /* MapNavigationApp */ = {
			isa = PBXGroup;
			children = (
				4A4A00011A1A1A1A00000001 /* MapNavigationAppApp.swift */,
				4A4A00031A1A1A1A00000002 /* ContentView.swift */,
				4A4A00051A1A1A1A00000003 /* BLEManager.swift */,
				4A4A00071A1A1A1A00000004 /* NavigationManager.swift */,
				4A4A00091A1A1A1A00000005 /* Info.plist */,
				4A4A00211A1A1A1A00000005 /* Assets.xcassets */,
			);
			path = MapNavigationApp;
			sourceTree = "<group>";
		};
		4A4A00101A1A1A1A0000000A /* Products */ = {
			isa = PBXGroup;
			children = (
				4A4A00101A1A1A1A00000006 /* MapNavigationApp.app */,
			);
			name = Products;
			sourceTree = "<group>";
		};
/* End PBXGroup section */

/* Begin PBXNativeTarget section */
		4A4A00501A1A1A1A00000010 /* MapNavigationApp */ = {
			isa = PBXNativeTarget;
			buildConfigurationList = 4A4A00601A1A1A1A00000011 /* Build configuration list for PBXNativeTarget "MapNavigationApp" */;
			buildPhases = (
				4A4A00701A1A1A1A00000012 /* Sources */,
				4A4A00201A1A1A1A00000007 /* Frameworks */,
				4A4A00801A1A1A1A00000013 /* Resources */,
			);
			buildRules = (
			);
			dependencies = (
			);
			name = MapNavigationApp;
			productName = MapNavigationApp;
			productReference = 4A4A00101A1A1A1A00000006 /* MapNavigationApp.app */;
			productType = "com.apple.product-type.application";
		};
/* End PBXNativeTarget section */

/* Begin PBXProject section */
		4A4A00901A1A1A1A00000014 /* Project object */ = {
			isa = PBXProject;
			attributes = {
				LastSwiftUpdateCheck = 1400;
				LastUpgradeCheck = 1400;
				TargetAttributes = {
					4A4A00501A1A1A1A00000010 = {
						CreatedOnToolsVersion = 14.0;
					};
				};
			};
			buildConfigurationList = 4A4A00A01A1A1A1A00000015 /* Build configuration list for PBXProject "MapNavigationApp" */;
			compatibilityVersion = "Xcode 14.0";
			developmentRegion = en;
			hasScannedForEncodings = 0;
			knownRegions = (
				en,
				Base,
			);
			mainGroup = 4A4A00301A1A1A1A00000008;
			productRefGroup = 4A4A00101A1A1A1A0000000A /* Products */;
			projectDirPath = "";
			projectRoot = "";
			targets = (
				4A4A00501A1A1A1A00000010 /* MapNavigationApp */,
			);
		};
/* End PBXProject section */

/* Begin PBXResourcesBuildPhase section */
		4A4A00801A1A1A1A00000013 /* Resources */ = {
			isa = PBXResourcesBuildPhase;
			buildActionMask = 2147483647;
			files = (
				4A4A00221A1A1A1A00000005 /* Assets.xcassets in Resources */,
			);
			runOnlyForDeploymentPostprocessing = 0;
		};
/* End PBXResourcesBuildPhase section */

/* Begin PBXSourcesBuildPhase section */
		4A4A00701A1A1A1A00000012 /* Sources */ = {
			isa = PBXSourcesBuildPhase;
			buildActionMask = 2147483647;
			files = (
				4A4A00021A1A1A1A00000001 /* MapNavigationAppApp.swift in Sources */,
				4A4A00041A1A1A1A00000002 /* ContentView.swift in Sources */,
				4A4A00061A1A1A1A00000003 /* BLEManager.swift in Sources */,
				4A4A00081A1A1A1A00000004 /* NavigationManager.swift in Sources */,
			);
			runOnlyForDeploymentPostprocessing = 0;
		};
/* End PBXSourcesBuildPhase section */

/* Begin XCBuildConfiguration section */
		4A4A00B01A1A1A1A00000016 /* Debug */ = {
			isa = XCBuildConfiguration;
			buildSettings = {
				ALWAYS_SEARCH_USER_PATHS = NO;
				CLANG_ANALYZER_NONNULL = YES;
				CLANG_ANALYZER_NUMBER_OBJECT_CONVERSION = YES_AGGRESSIVE;
				CLANG_CXX_LANGUAGE_STANDARD = "gnu++20";
				CLANG_CXX_LIBRARY = "libc++";
				CLANG_ENABLE_MODULES = YES;
				CLANG_ENABLE_OBJC_ARC = YES;
				CLANG_ENABLE_OBJC_WEAK = YES;
				CLANG_WARN_BLOCK_CAPTURE_AUTORELEASING = YES;
				CLANG_WARN_BOOL_CONVERSION = YES;
				CLANG_WARN_COMMA = YES;
				CLANG_WARN_CONSTANT_CONVERSION = YES;
				CLANG_WARN_DEPRECATED_OBJC_IMPLEMENTATIONS = YES;
				CLANG_WARN_DIRECT_OBJC_PREPARATIONS = YES_OR_NO;
				CLANG_WARN_DOCUMENTATION_COMMENTS = YES;
				CLANG_WARN_EMPTY_BODY = YES;
				CLANG_WARN_ENUM_CONVERSION = YES;
				CLANG_WARN_INFINITE_RECURSION = YES;
				CLANG_WARN_INT_CONVERSION = YES;
				CLANG_WARN_NON_LITERAL_NULL_CONVERSION = YES;
				CLANG_WARN_OBJC_IMPLICIT_RETAIN_SELF = YES;
				CLANG_WARN_OBJC_LITERAL_CONVERSION = YES;
				CLANG_WARN_OBJC_ROOT_CLASS = YES_ERROR;
				CLANG_WARN_QUOTED_INCLUDE_IN_FRAMEWORK_HEADER = YES;
				CLANG_WARN_RANGE_LOOP_ANALYSIS = YES;
				CLANG_WARN_STRICT_PROTOTYPES = YES;
				CLANG_WARN_SUSPICIOUS_MOVE = YES;
				CLANG_WARN_UNGUARDED_AVAILABILITY = YES_AGGRESSIVE;
				CLANG_WARN_UNREACHABLE_CODE = YES;
				COPY_PHASE_STRIP = NO;
				DEBUG_INFORMATION_FORMAT = dwarf;
				ENABLE_STRICT_OBJC_MSGSEND = YES;
				ENABLE_TESTABILITY = YES;
				GCC_C_LANGUAGE_STANDARD = gnu11;
				GCC_DYNAMIC_NO_PIC = NO;
				GCC_NO_COMMON_BLOCKS = YES;
				GCC_OPTIMIZATION_LEVEL = 0;
				GCC_PREPROCESSOR_DEFINITIONS = (
					"DEBUG=1",
					"$(inherited)",
				);
				GCC_WARN_64_TO_32_BIT_CONVERSION = YES;
				GCC_WARN_ABOUT_RETURN_TYPE = YES_ERROR;
				GCC_WARN_UNDECLARED_SELECTOR = YES;
				GCC_WARN_UNINITIALIZED_ACTUAL = YES_AGGRESSIVE;
				GCC_WARN_UNUSED_FUNCTION = YES;
				GCC_WARN_UNUSED_VARIABLE = YES;
				IPHONEOS_DEPLOYMENT_TARGET = 15.0;
				MTL_ENABLE_DEBUG_INFO = INCLUDE_SOURCE;
				MTL_FAST_MATH = YES;
				ONLY_ACTIVE_ARCH = YES;
				SDKROOT = iphoneos;
				SWIFT_ACTIVE_COMPILATION_CONDITIONS = DEBUG;
				SWIFT_OPTIMIZATION_LEVEL = "-Onone";
			};
			name = Debug;
		};
		4A4A00B01A1A1A1A00000017 /* Release */ = {
			isa = XCBuildConfiguration;
			buildSettings = {
				ALWAYS_SEARCH_USER_PATHS = NO;
				CLANG_ANALYZER_NONNULL = YES;
				CLANG_ANALYZER_NUMBER_OBJECT_CONVERSION = YES_AGGRESSIVE;
				CLANG_CXX_LANGUAGE_STANDARD = "gnu++20";
				CLANG_CXX_LIBRARY = "libc++";
				CLANG_ENABLE_MODULES = YES;
				CLANG_ENABLE_OBJC_ARC = YES;
				CLANG_ENABLE_OBJC_WEAK = YES;
				CLANG_WARN_BLOCK_CAPTURE_AUTORELEASING = YES;
				CLANG_WARN_BOOL_CONVERSION = YES;
				CLANG_WARN_COMMA = YES;
				CLANG_WARN_CONSTANT_CONVERSION = YES;
				CLANG_WARN_DEPRECATED_OBJC_IMPLEMENTATIONS = YES;
				CLANG_WARN_DIRECT_OBJC_PREPARATIONS = YES_OR_NO;
				CLANG_WARN_DOCUMENTATION_COMMENTS = YES;
				CLANG_WARN_EMPTY_BODY = YES;
				CLANG_WARN_ENUM_CONVERSION = YES;
				CLANG_WARN_INFINITE_RECURSION = YES;
				CLANG_WARN_INT_CONVERSION = YES;
				CLANG_WARN_NON_LITERAL_NULL_CONVERSION = YES;
				CLANG_WARN_OBJC_IMPLICIT_RETAIN_SELF = YES;
				CLANG_WARN_OBJC_LITERAL_CONVERSION = YES;
				CLANG_WARN_OBJC_ROOT_CLASS = YES_ERROR;
				CLANG_WARN_QUOTED_INCLUDE_IN_FRAMEWORK_HEADER = YES;
				CLANG_WARN_RANGE_LOOP_ANALYSIS = YES;
				CLANG_WARN_STRICT_PROTOTYPES = YES;
				CLANG_WARN_SUSPICIOUS_MOVE = YES;
				CLANG_WARN_UNGUARDED_AVAILABILITY = YES_AGGRESSIVE;
				CLANG_WARN_UNREACHABLE_CODE = YES;
				COPY_PHASE_STRIP = YES;
				DEBUG_INFORMATION_FORMAT = "dwarf-with-dsym";
				ENABLE_NS_ASSERTIONS = NO;
				ENABLE_STRICT_OBJC_MSGSEND = YES;
				GCC_C_LANGUAGE_STANDARD = gnu11;
				GCC_NO_COMMON_BLOCKS = YES;
				GCC_WARN_64_TO_32_BIT_CONVERSION = YES;
				GCC_WARN_ABOUT_RETURN_TYPE = YES_ERROR;
				GCC_WARN_UNDECLARED_SELECTOR = YES;
				GCC_WARN_UNINITIALIZED_ACTUAL = YES_AGGRESSIVE;
				GCC_WARN_UNUSED_FUNCTION = YES;
				GCC_WARN_UNUSED_VARIABLE = YES;
				IPHONEOS_DEPLOYMENT_TARGET = 15.0;
				MTL_ENABLE_DEBUG_INFO = NO;
				MTL_FAST_MATH = YES;
				SDKROOT = iphoneos;
				SWIFT_COMPILATION_MODE = wholemodule;
				SWIFT_OPTIMIZATION_LEVEL = "-O";
				VALIDATE_PRODUCT = YES;
			};
			name = Release;
		};
		4A4A00C01A1A1A1A00000018 /* Debug */ = {
			isa = XCBuildConfiguration;
			buildSettings = {
				CODE_SIGN_STYLE = Manual;
				CODE_SIGNING_ALLOWED = NO;
				CODE_SIGNING_REQUIRED = NO;
				CODE_SIGN_IDENTITY = "";
				CURRENT_PROJECT_VERSION = 1;
				GENERATE_INFOPLIST_FILE = NO;
				INFOPLIST_FILE = MapNavigationApp/Info.plist;
				LD_RUNPATH_SEARCH_PATHS = (
					"$(inherited)",
					"@executable_path/Frameworks",
				);
				MARKETING_VERSION = 1.0;
				ASSETCATALOG_COMPILER_APPICON_NAME = AppIcon;
				PRODUCT_BUNDLE_IDENTIFIER = com.antigravity.MapNavigationApp;
				PRODUCT_NAME = "$(TARGET_NAME)";
				SWIFT_EMIT_LOC_STRINGS = YES;
				SWIFT_VERSION = 5.0;
				TARGETED_DEVICE_FAMILY = "1,2";
			};
			name = Debug;
		};
		4A4A00C01A1A1A1A00000019 /* Release */ = {
			isa = XCBuildConfiguration;
			buildSettings = {
				CODE_SIGN_STYLE = Manual;
				CODE_SIGNING_ALLOWED = NO;
				CODE_SIGNING_REQUIRED = NO;
				CODE_SIGN_IDENTITY = "";
				CURRENT_PROJECT_VERSION = 1;
				GENERATE_INFOPLIST_FILE = NO;
				INFOPLIST_FILE = MapNavigationApp/Info.plist;
				LD_RUNPATH_SEARCH_PATHS = (
					"$(inherited)",
					"@executable_path/Frameworks",
				);
				MARKETING_VERSION = 1.0;
				ASSETCATALOG_COMPILER_APPICON_NAME = AppIcon;
				PRODUCT_BUNDLE_IDENTIFIER = com.antigravity.MapNavigationApp;
				PRODUCT_NAME = "$(TARGET_NAME)";
				SWIFT_EMIT_LOC_STRINGS = YES;
				SWIFT_VERSION = 5.0;
				TARGETED_DEVICE_FAMILY = "1,2";
			};
			name = Release;
		};
/* End XCBuildConfiguration section */

/* Begin XCConfigurationList section */
		4A4A00601A1A1A1A00000011 /* Build configuration list for PBXNativeTarget "MapNavigationApp" */ = {
			isa = XCConfigurationList;
			buildConfigurations = (
				4A4A00C01A1A1A1A00000018 /* Debug */,
				4A4A00C01A1A1A1A00000019 /* Release */,
			);
			defaultConfigurationIsVisible = 0;
			defaultConfigurationName = Release;
		};
		4A4A00A01A1A1A1A00000015 /* Build configuration list for PBXProject "MapNavigationApp" */ = {
			isa = XCConfigurationList;
			buildConfigurations = (
				4A4A00B01A1A1A1A00000016 /* Debug */,
				4A4A00B01A1A1A1A00000017 /* Release */,
			);
			defaultConfigurationIsVisible = 0;
			defaultConfigurationName = Release;
		};
/* End XCConfigurationList section */
	};
	rootObject = 4A4A00901A1A1A1A00000014 /* Project object */;
}
"""
    with open("MapNavigationApp.xcodeproj/project.pbxproj", "w", encoding="utf-8") as f:
        f.write(content)
    print("Wrote project.pbxproj")

def write_scheme():
    content = """<?xml version="1.0" encoding="UTF-8"?>
<Scheme
   LastUpgradeVersion = "1400"
   version = "1.3">
   <BuildAction
      parallelizeBuildables = "YES"
      buildImplicitDependencies = "YES">
      <BuildActionEntries>
         <BuildActionEntry
            buildForTesting = "YES"
            buildForRunning = "YES"
            buildForProfiling = "YES"
            buildForArchiving = "YES"
            buildForAnalyzing = "YES">
            <BuildableReference
               BuildableIdentifier = "primary"
               BlueprintIdentifier = "4A4A00501A1A1A1A00000010"
               BuildableName = "MapNavigationApp.app"
               BlueprintName = "MapNavigationApp"
               ReferencedContainer = "container:MapNavigationApp.xcodeproj">
            </BuildableReference>
         </BuildActionEntry>
      </BuildActionEntries>
   </BuildAction>
   <TestAction
      buildConfiguration = "Debug"
      selectedDebuggerIdentifier = "Xcode.DebuggerFoundation.Debugger.LLDB"
      selectedLauncherIdentifier = "Xcode.DebuggerFoundation.Launcher.LLDB"
      shouldUseLaunchSchemeArgsEnv = "YES">
      <Testables>
      </Testables>
   </TestAction>
   <LaunchAction
      buildConfiguration = "Debug"
      selectedDebuggerIdentifier = "Xcode.DebuggerFoundation.Debugger.LLDB"
      selectedLauncherIdentifier = "Xcode.DebuggerFoundation.Launcher.LLDB"
      launchStyle = "0"
      useLaunchSchemeArgsEnv = "YES"
      ignoresPersistentStateOnLaunch = "NO"
      debugDocumentVersioning = "YES"
      debugServiceExtension = "internal"
      allowLocationSimulation = "YES">
      <BuildableProductRunnable
         runnableDebuggingMode = "0">
         <BuildableReference
            BuildableIdentifier = "primary"
            BlueprintIdentifier = "4A4A00501A1A1A1A00000010"
            BuildableName = "MapNavigationApp.app"
            BlueprintName = "MapNavigationApp"
            ReferencedContainer = "container:MapNavigationApp.xcodeproj">
         </BuildableReference>
      </BuildableProductRunnable>
   </LaunchAction>
   <ProfileAction
      buildConfiguration = "Release"
      shouldUseLaunchSchemeArgsEnv = "YES"
      savedToolIdentifier = ""
      useLaunchSchemeArgsEnv = "YES"
      debugDocumentVersioning = "YES">
      <BuildableProductRunnable
         runnableDebuggingMode = "0">
         <BuildableReference
            BuildableIdentifier = "primary"
            BlueprintIdentifier = "4A4A00501A1A1A1A00000010"
            BuildableName = "MapNavigationApp.app"
            BlueprintName = "MapNavigationApp"
            ReferencedContainer = "container:MapNavigationApp.xcodeproj">
         </BuildableReference>
      </BuildableProductRunnable>
   </ProfileAction>
   <AnalyzeAction
      buildConfiguration = "Debug">
   </AnalyzeAction>
   <ArchiveAction
      buildConfiguration = "Release"
      revealArchiveInOrganizer = "YES">
   </ArchiveAction>
</Scheme>
"""
    with open("MapNavigationApp.xcodeproj/xcshareddata/xcschemes/MapNavigationApp.xcscheme", "w", encoding="utf-8") as f:
        f.write(content)
    print("Wrote MapNavigationApp.xcscheme")

if __name__ == "__main__":
    create_directory_structure()
    write_app_swift()
    write_ble_manager()
    write_navigation_manager()
    write_content_view()
    write_info_plist()
    write_assets()
    write_xcodeproj()
    write_scheme()
    print("All files generated successfully!")
