# Cara Menjalankan Bot & Proxy di Windows VPS

Panduan ini untuk menjalankan bot di **Windows Server VPS**.

---

### 1. Instalasi Runtime Dasar
Download dan instal program berikut secara manual di VPS Anda:

1.  **Python 3.10+**: Download dari [python.org](https://www.python.org/downloads/windows/). 
    *   **Penting**: Centang kotak **"Add Python to PATH"** saat instalasi.
2.  **Node.js**: Download dari [nodejs.org](https://nodejs.org/). Pilih versi LTS.
3.  **FFMPEG**:
    *   Download build statis Windows dari [gyan.dev](https://www.gyan.dev/ffmpeg/builds/ffmpeg-git-full.7z).
    *   Ekstrak folder `bin` (isi terminal: `ffmpeg.exe`, `ffprobe.exe`).
    *   Masukkan path folder `bin` tersebut ke dalam **System Environment Variables (PATH)** agar bisa dipanggil dari CMD/PowerShell mana saja.

---

### 2. Persiapan Folder Proyek
Upload semua file proyek ke folder di VPS (misal: `C:\MyBot`).

Buka **CMD** atau **PowerShell** sebagai Administrator dalam folder tersebut.

### 3. Instalasi Pustaka (Dependencies)
Jalankan perintah ini di dalam folder proyek:

```powershell
# Instal pustaka Python
pip install -r requirements.txt

# Instal pustaka Node.js
npm install
```

### 4. Menjalankan Layanan (PM2)
Untuk manajemen proses agar bot tidak tertutup saat RDP disconnect, gunakan **PM2**.

```powershell
# Instal PM2 secara global
npm install -g pm2

# Jalankan Proxy Node.js
pm2 start proxy.js --name "hls-proxy"

# Jalankan Bot Python
pm2 start main.py --name "drama-bot" --interpreter python

# Agar PM2 otomatis berjalan saat VPS restart (khusus Windows)
npm install -g pm2-windows-startup
pm2-startup install
pm2 save
```

### 5. Konfigurasi Firewall
Pastikan port proxy Anda (default: 3000) terbuka di **Windows Firewall** jika ingin diakses dari luar:
1. Buka `Windows Defender Firewall with Advanced Security`.
2. Klik `Inbound Rules` -> `New Rule`.
3. Pilih `Port`, pilih `TCP`, masukkan `3000`.
4. Pilih `Allow the connection`, beri nama "HLS Proxy".

---

### Tips Berguna:
*   **Logs**: Gunakan `pm2 logs` untuk melihat apakah bot berjalan dengan benar.
*   **FFMPEG**: Jika bot error "ffmpeg not found", pastikan Anda sudah me-restart CMD/PowerShell setelah mengatur PATH lingkungan (Environment Variables).
*   **Idle**: Pastikan VPS Anda tidak masuk ke mode *Sleep* demi menjaga bot tetap aktif 24/7.
