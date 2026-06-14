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
        
        let strippedStreet = nextStreet.strippingDiacritics
        
        let message = "\\(turnCode);\\(distStr);\\(strippedStreet)"
        bleManager?.sendData(message)
    }
    
    private func sendArrivedUpdate() {
        bleManager?.sendData("7;Da den;\\(destinationName.strippingDiacritics)")
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

struct ContentView: View {
    @StateObject private var bleManager = BLEManager()
    @StateObject private var navManager: NavigationManager
    
    @State private var googleAPIKey: String = ""
    @State private var inputDestination: String = ""
    @State private var showSettings = false
    @State private var showBLEScanner = false
    @State private var clipboardLink = ""
    @State private var showClipboardPrompt = false
    
    init() {
        let ble = BLEManager()
        _bleManager = StateObject(wrappedValue: ble)
        _navManager = StateObject(wrappedValue: NavigationManager(bleManager: ble))
    }
    
    var body: some View {
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
				4A4A00101A1A1A1A00000006 /* Products */,
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
		4A4A00101A1A1A1A00000006 /* Products */ = {
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
			productRefGroup = 4A4A00101A1A1A1A00000006 /* Products */;
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
