import Foundation
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
        
        print("Resolved Google Maps URL: \(resolvedURLString)")
        
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
            print("Failed to resolve URL: \(error)")
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
            print("Failed GET fallback: \(error)")
        }
        return shortURLString // Return original if redirect resolving fails
    }
    
    private func extractCoordinates(from urlString: String) -> CLLocationCoordinate2D? {
        // Pattern 1: @lat,lng
        if let regex = try? NSRegularExpression(pattern: "@(-?\\d+\\.\\d+),(-?\\d+\\.\\d+)", options: []),
           let match = regex.firstMatch(in: urlString, options: [], range: NSRange(urlString.startIndex..., in: urlString)) {
            if let latRange = Range(match.range(at: 1), in: urlString),
               let lngRange = Range(match.range(at: 2), in: urlString),
               let lat = Double(urlString[latRange]),
               let lng = Double(urlString[lngRange]) {
                return CLLocationCoordinate2D(latitude: lat, longitude: lng)
            }
        }
        // Pattern 2: dir/Origin/DestinationCoordinates
        if let regex = try? NSRegularExpression(pattern: "/dir/[^/]*/(-?\\d+\\.\\d+),(-?\\d+\\.\\d+)", options: []),
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
            print("Geocoding failed for: \(name). Error: \(error)")
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
                print("Google API Error (\(httpResponse.statusCode)): \(errStr)")
                DispatchQueue.main.async {
                    self.errorMessage = "Google API tra ve loi \(httpResponse.statusCode). Kiem tra lai API Key."
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
            print("Failed to fetch Google route: \(error)")
            DispatchQueue.main.async {
                self.errorMessage = "Loi ket noi mang: \(error.localizedDescription)"
            }
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
        
        let prefix = "\(turnCode);\(distStr);"
        let maxStreetLength = max(1, 20 - prefix.count)
        let strippedStreet = bleSafeText(nextStreet, maxLength: maxStreetLength)
        
        let message = "\(prefix)\(strippedStreet.isEmpty ? "-" : strippedStreet)"
        bleManager?.sendData(message)
    }
    
    private func sendArrivedUpdate() {
        let prefix = "7;Da den;"
        let place = bleSafeText(destinationName, maxLength: max(1, 20 - prefix.count))
        bleManager?.sendData("\(prefix)\(place.isEmpty ? "-" : place)")
    }

    private func bleSafeText(_ text: String, maxLength: Int) -> String {
        let ascii = text.strippingDiacritics
            .replacingOccurrences(of: ";", with: " ")
            .replacingOccurrences(of: "[^A-Za-z0-9 .,/\\-]", with: "", options: .regularExpression)
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
                    print("Off-route count: \(offRouteCount) (distance: \(distToSegment)m)")
                    
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
        print("GPS tracking failed: \(error)")
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
