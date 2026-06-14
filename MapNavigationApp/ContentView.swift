import SwiftUI
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
                                
                                Text("Sap vao: \(navManager.nextStreet)")
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
                navManager.errorMessage = "Loi tim kiem: \(error.localizedDescription)"
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
                        List(bleManager.discoveredPeripherals, id: \.identifier) { peripheral in
                            HStack {
                                VStack(alignment: .leading) {
                                    Text(peripheral.name ?? "Thiet bi khong ten")
                                        .font(.headline)
                                        .foregroundColor(.white)
                                    Text("UUID: \(peripheral.identifier.uuidString.prefix(12))...")
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
