# Hướng Dẫn Lắp Đặt & Cài Đặt Thiết Bị Chỉ Đường Xe Máy (GMap BLE Companion)

Dự án này giúp bạn chế tạo thiết bị hiển thị chỉ đường thời gian thực (mũi tên rẽ, khoảng cách, tên đường) gắn trên xe máy. Thiết bị sử dụng **ESP32-C3 SuperMini** và màn hình tròn **GC9A01 1.28" TFT**. Hành trình xe máy được đồng bộ trực tiếp từ ứng dụng **Google Maps** chính thức trên iPhone thông qua Bluetooth Low Energy (BLE).

Do bạn sử dụng máy tính Windows, dự án cung cấp sẵn công cụ tự động tạo Xcode project trên Windows và bộ tích hợp **GitHub Actions** giúp bạn biên dịch ứng dụng iOS thành file `.ipa` từ xa miễn phí, sau đó cài đặt lên iPhone bằng **SideStore**.

---

## 1. Đấu Dây Phần Cứng (Hardware Wiring)

Hãy kết nối màn hình tròn **1.28" TFT GC9A01** với board **ESP32-C3 SuperMini** theo sơ đồ sau:

| Tên chân màn hình GC9A01 | Chân kết nối trên ESP32-C3 SuperMini | Chức năng |
| :--- | :--- | :--- |
| **VCC** | **3.3V** | Cấp nguồn 3.3V |
| **GND** | **GND** | Chân đất (Ground) |
| **SCL (SCLK)** | **GPIO 4** | SPI Clock |
| **SDA (MOSI)** | **GPIO 6** | SPI Data (MOSI) |
| **DC** | **GPIO 2** | Data/Command Control |
| **CS** | **GPIO 7** | SPI Chip Select |
| **RST** | **GPIO 3** | Reset |

*Lưu ý: Bạn có thể cắm test trên breadboard trước khi hàn cứng để đảm bảo kết nối hoạt động tốt.*

---

## 2. Nạp Code Cho ESP32-C3 SuperMini

1. Tải và cài đặt **Arduino IDE** trên Windows (nếu chưa có).
2. Mở Arduino IDE, vào mục **File > Preferences** và dán link này vào ô *Additional Boards Manager URLs*:
   `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
3. Vào **Tools > Board > Boards Manager**, tìm kiếm `esp32` và bấm **Install** để cài đặt bộ thư viện các chip ESP32.
4. Tiếp tục vào **Tools > Manage Libraries...** (hoặc nhấn `Ctrl+Shift+I`), tìm kiếm và cài đặt thư viện:
   - **GFX Library for Arduino** (bởi *Lobo* hoặc *MoonOnOurNation* - thư viện vẽ đồ họa hiệu suất cao).
5. Mở file [esp32_navigation_device.ino](file:///c:/code/ios/mapping-iphone/esp32_navigation_device/esp32_navigation_device.ino) trong thư mục dự án bằng Arduino IDE.
6. Cắm cáp USB-C từ máy tính vào ESP32-C3 SuperMini:
   - Trong Tools, chọn board: **ESP32C3 Dev Module** (hoặc *Generic ESP32-C3*).
   - Chọn đúng cổng **COM Port** nhận thiết bị.
7. Bấm nút **Upload** (Mũi tên sang phải) để nạp code.
8. Sau khi nạp thành công, màn hình tròn sẽ sáng lên hiển thị dòng chữ chào mừng, sau đó chuyển sang trạng thái **"SCANNING"** với một chấm màu **ĐỎ** ở phía trên.

---

## 3. Tạo Mã Nguồn và Build Ứng Dụng iPhone (iOS App)

Do iOS yêu cầu hệ điều hành macOS (Xcode) để biên dịch, chúng ta sẽ sử dụng server đám mây của GitHub (miễn phí) để build file cài đặt `.ipa` chỉ với vài click chuột:

### Bước 3.1: Tạo thư mục dự án iOS trên Windows
Mở terminal trên Windows (PowerShell/CMD) tại thư mục dự án và chạy lệnh sau để tự động tạo toàn bộ cấu trúc dự án Xcode và các file mã nguồn Swift:
```powershell
python generate_project.py
```
*Sau khi chạy, bạn sẽ thấy thư mục `MapNavigationApp` và `MapNavigationApp.xcodeproj` xuất hiện.*

### Bước 3.2: Đưa code lên GitHub cá nhân
1. Tạo một tài khoản GitHub (nếu chưa có).
2. Tạo mới một repository (kho lưu trữ), bạn nên để chế độ **Private** (Riêng tư) để bảo mật thông tin cá nhân.
3. Đẩy toàn bộ thư mục code này lên GitHub của bạn:
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin <LINK_GITHUB_REPO_CUA_BAN>
   git push -u origin main
   ```

### Bước 3.3: Tải file cài đặt `.ipa`
1. Truy cập vào trang GitHub repository bạn vừa tạo trên trình duyệt.
2. Click vào tab **Actions**. Bạn sẽ thấy một tiến trình build tự động có tên **Build Unsigned iOS IPA** đang chạy.
3. Chờ khoảng 2-3 phút cho tiến trình hiện tích xanh lá cây hoàn thành.
4. Nhấn vào kết quả build, cuộn xuống phần **Artifacts** và tải file **MapNavigationApp-Unsigned-IPA** về máy tính (hoặc tải trực tiếp về iPhone của bạn).
5. Giải nén file zip tải về, bạn sẽ nhận được file `MapNavigationApp.ipa` sẵn sàng để cài đặt.

---

## 4. Ký và Cài Đặt Lên iPhone Bằng SideStore

SideStore là giải pháp tuyệt vời để cài đặt file `.ipa` trực tiếp trên iPhone bằng tài khoản Apple ID miễn phí của bạn mà không cần máy tính sau lần cài đặt đầu tiên.

1. Chuyển file `MapNavigationApp.ipa` vào ứng dụng **Tệp (Files)** trên iPhone của bạn.
2. Mở ứng dụng **SideStore** trên iPhone.
3. Chọn tab **My Apps**, nhấn dấu **+** ở góc trên bên trái.
4. Chọn file `MapNavigationApp.ipa` bạn đã chuẩn bị.
5. Nhập tài khoản Apple ID và mật khẩu ứng dụng (App-specific password) của bạn để SideStore bắt đầu tự động ký số và cài đặt ứng dụng vào máy.
6. Sau khi cài đặt xong, icon ứng dụng **GMap BLE Companion** sẽ xuất hiện trên màn hình chính của iPhone.
7. Trước khi mở app, vào **Cài đặt hệ thống > Cài đặt chung > Quản lý VPN & Thiết bị** trên iPhone, chọn nhà phát triển (tài khoản Apple ID của bạn) và nhấn **Tin cậy (Trust)**.

---

## 5. Hướng Dẫn Sử Dụng & Kết Nối Chỉ Đường

### Bước 5.1: Đăng ký Google Maps API Key (Miễn phí)
Để ứng dụng có thể lấy dữ liệu dẫn đường xe máy chuẩn xác của Google Maps, bạn cần có một khóa API:
1. Truy cập [Google Cloud Console](https://console.cloud.google.com/) và đăng nhập bằng tài khoản Google.
2. Tạo một Project mới.
3. Kích hoạt tính năng thanh toán (Billing) cho tài khoản Google Cloud của bạn. 
   *(Yên tâm: Google luôn tặng miễn phí **200 USD** mỗi tháng cho mỗi tài khoản, tương đương hàng chục ngàn lượt dẫn đường mỗi tháng. Bạn sẽ không bao giờ bị tính phí trừ khi dùng vượt mức cực lớn cho mục đích thương mại).*
4. Vào mục **API & Services > Library**, tìm kiếm và kích hoạt (Enable) API sau:
   - **Routes API** (Rất quan trọng - dùng để tính toán lộ trình xe máy).
5. Vào mục **API & Services > Credentials**, nhấn **Create Credentials > API Key** để tạo một khóa bí mật. Hãy copy khóa API này.

### Bước 5.2: Bắt đầu dẫn đường
1. Cấp nguồn cho thiết bị gắn trên xe máy.
2. Mở ứng dụng **GMap BLE Companion** trên iPhone.
3. Nhấp vào biểu tượng **Bánh răng cài đặt (Gear icon)** ở góc trên bên phải, dán **Google API Key** của bạn vào rồi bấm **Lưu cài đặt**.
4. Nhấn nút **Kết Nối** trên giao diện chính, chọn thiết bị `ESP32_Nav_Companion` trong danh sách hiển thị. Khi kết nối thành công, chấm trên màn hình xe máy sẽ chuyển sang màu **XANH DƯƠNG**.
5. Mở ứng dụng **Google Maps** gốc của Google lên.
6. Tìm kiếm đường đi như bình thường, chọn chế độ **Đi xe máy**.
7. Nhấn nút **Chia sẻ lộ trình (Share)** $\rightarrow$ Chọn **Sao chép liên kết (Copy Link)**.
8. Quay lại app **GMap BLE Companion** của chúng ta.
   *   App sẽ tự động phát hiện link bạn vừa copy và hiển thị bảng hỏi: **"Phát hiện liên kết Google Maps! Bạn có muốn bắt đầu lộ trình không?"**.
   *   Nhấn **Đồng ý**.
9. Nhấn nút **Bắt đầu chỉ đường**. Bạn có thể cất điện thoại vào túi quần. Màn hình tròn trên xe máy sẽ hiển thị hướng rẽ, đếm ngược số mét và tên đường thực tế theo thời gian thực khi bạn di chuyển!
