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
    content = """import Foundation
import CoreBluetooth

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
        centralManager.scanForPeripherals(withServices: [serviceUUID], options: nil)
        
        // Auto-stop scanning after 15 seconds
        DispatchQueue.main.asyncAfter(deadline: .now() + 15.0) { [weak self] in
            self?.stopScanning()
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
            let writeType: CBPeripheralWriteType = characteristic.properties.contains(.writeWithoutResponse) ? .writeWithoutResponse : .withResponse
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
            discoveredPeripherals.append(peripheral)
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
            DispatchQueue.main.async {
                self.errorMessage = "Khong lay duoc vi tri GPS hien tai."
            }
            return
        }
        
        let success = await fetchGoogleMotorbikeRoute(from: userLoc.coordinate, to: destination, apiKey: apiKey)
        if success {
            DispatchQueue.main.async {
                self.isNavigating = true
                self.currentStepIndex = 0
                self.locationManager.startUpdatingLocation()
                self.errorMessage = nil
                self.processCurrentStep()
            }
        }
    }
    
    func stopNavigation() {
        DispatchQueue.main.async {
            self.isNavigating = false
            self.locationManager.stopUpdatingLocation()
            self.routeSteps = nil
            self.currentInstruction = "Da dung chi duong"
            self.nextStreet = "..."
            self.distanceToNextTurn = 0.0
            
            // Send turnType = 0 (straight/idle)
            self.bleManager?.sendData("0;--;Dung dan duong")
        }
    }
    
    // Resolves Google Maps link and starts navigation
    func handleGoogleMapsURL(_ urlString: String, apiKey: String) async {
        DispatchQueue.main.async {
            self.isResolvingURL = true
            self.errorMessage = nil
        }
        
        // 1. Resolve redirect to get the long URL
        guard let resolvedURLString = await resolveShortenedURL(urlString) else {
            DispatchQueue.main.async {
                self.isResolvingURL = false
                self.errorMessage = "Khong the giai ma link Google Maps."
            }
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
        
        DispatchQueue.main.async {
            self.isResolvingURL = false
        }
        
        if let coord = destinationCoord {
            await startNavigation(destination: coord, name: name, apiKey: apiKey)
        } else {
            DispatchQueue.main.async {
                self.errorMessage = "Khong tim thay toa do diem den."
            }
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
                DispatchQueue.main.async {
                    self.errorMessage = "Google API tra ve loi \\(httpResponse.statusCode). Kiem tra lai API Key."
                }
                return false
            }
            
            let decoder = JSONDecoder()
            let routeResponse = try decoder.decode(RouteResponse.self, from: data)
            
            guard let steps = routeResponse.routes?.first?.legs?.first?.steps, !steps.isEmpty else {
                DispatchQueue.main.async {
                    self.errorMessage = "Khong tim thay cac buoc huong dan tuyen duong."
                }
                return false
            }
            
            DispatchQueue.main.async {
                self.routeSteps = steps
            }
            return true
            
        } catch {
            print("Failed to fetch Google route: \\(error)")
            DispatchQueue.main.async {
                self.errorMessage = "Loi ket noi mang: \\(error.localizedDescription)"
            }
            return false
        }
    }
    
    private func processCurrentStep() {
        guard let steps = routeSteps, currentStepIndex < steps.count else { return }
        let step = steps[currentStepIndex]
        
        // Extract instructions and street name
        let instructionText = step.navigationInstruction?.instructions ?? "Di thang"
        let maneuver = step.navigationInstruction?.maneuver ?? "STRAIGHT"
        
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
                DispatchQueue.main.async {
                    self.currentStepIndex = 0
                    self.errorMessage = nil
                    self.processCurrentStep()
                }
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
                            
                            DispatchQueue.main.async {
                                self.currentInstruction = "Di sai duong, dang tinh lai..."
                                self.nextStreet = "..."
                                self.bleManager?.sendData("0;--;Dang tinh lai...")
                            }
                            
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
                
                DispatchQueue.main.async {
                    self.distanceToNextTurn = distance
                    
                    if distance < 15.0 {
                        self.currentStepIndex = nextStepIndex
                        self.processCurrentStep()
                    } else {
                        self.sendBLEUpdate()
                    }
                }
            }
        } else {
            // Last step: Heading to final destination
            if let destLat = destinationCoordinate?.latitude,
               let destLng = destinationCoordinate?.longitude {
                let destLocation = CLLocation(latitude: destLat, longitude: destLng)
                let distance = userLoc.distance(from: destLocation)
                
                DispatchQueue.main.async {
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
                        .scrollContentBackground(.hidden)
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
            DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
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
</dict>
</plist>
"""
    with open("MapNavigationApp/Info.plist", "w", encoding="utf-8") as f:
        f.write(content)
    print("Wrote Info.plist")

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
/* End PBXBuildFile section */

/* Begin PBXFileReference section */
		4A4A00011A1A1A1A00000001 /* MapNavigationAppApp.swift */ = {isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = MapNavigationAppApp.swift; sourceTree = "<group>"; };
		4A4A00031A1A1A1A00000002 /* ContentView.swift */ = {isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = ContentView.swift; sourceTree = "<group>"; };
		4A4A00051A1A1A1A00000003 /* BLEManager.swift */ = {isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = BLEManager.swift; sourceTree = "<group>"; };
		4A4A00071A1A1A1A00000004 /* NavigationManager.swift */ = {isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = NavigationManager.swift; sourceTree = "<group>"; };
		4A4A00091A1A1A1A00000005 /* Info.plist */ = {isa = PBXFileReference; lastKnownFileType = text.plist.xml; path = Info.plist; sourceTree = "<group>"; };
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
				CODE_SIGN_STYLE = Automatic;
				CURRENT_PROJECT_VERSION = 1;
				GENERATE_INFOPLIST_FILE = NO;
				INFOPLIST_FILE = MapNavigationApp/Info.plist;
				LD_RUNPATH_SEARCH_PATHS = (
					"$(inherited)",
					"@executable_path/Frameworks",
				);
				MARKETING_VERSION = 1.0;
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
				CODE_SIGN_STYLE = Automatic;
				CURRENT_PROJECT_VERSION = 1;
				GENERATE_INFOPLIST_FILE = NO;
				INFOPLIST_FILE = MapNavigationApp/Info.plist;
				LD_RUNPATH_SEARCH_PATHS = (
					"$(inherited)",
					"@executable_path/Frameworks",
				);
				MARKETING_VERSION = 1.0;
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
    write_xcodeproj()
    write_scheme()
    print("All files generated successfully!")
