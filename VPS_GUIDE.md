# Cara Menjalankan Bot & Proxy di VPS (Linux/Ubuntu)

Panduan ini berasumsi Anda menggunakan VPS dengan sistem operasi **Ubuntu 20.04/22.04**.

---

### 1. Update Sistem & Instal Dependensi Utama
Pastikan sistem anda terupdate dan memiliki peralatan yang diperlukan.

```bash
# Update sistem
sudo apt update && sudo apt upgrade -y

# Instal Python & Pip
sudo apt install python3 python3-pip python3-venv -y

# Instal Node.js & NPM
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt install -y nodejs

# Instal FFmpeg (Sangat penting untuk download & merge video)
sudo apt install ffmpeg -y
```

### 2. Persiapkan Folder Proyek
Upload file anda ke VPS (via SCP, FTP, atau Git), lalu masuk ke foldernya.

### 3. Konfigurasi Bot (Python) & Proxy (Node.js)
```bash
# Instal pustaka Python
pip3 install -r requirements.txt

# Instal pustaka Node.js
npm install
```

### 4. Menjalankan di Background dengan PM2
Agar bot dan proxy tetap berjalan meskipun anda keluar dari terminal.

```bash
# Instal PM2 secara global
sudo npm install -g pm2

# Jalankan Proxy Node.js
pm2 start proxy.js --name "hls-proxy"

# Jalankan Bot Python
pm2 start main.py --name "drama-bot" --interpreter python3

# Agar PM2 otomatis berjalan saat VPS restart
pm2 save
pm2 startup
```

### 5. File .env
Pastikan file `.env` anda sudah berisi `API_ID`, `API_HASH`, dan `BOT_TOKEN` yang benar di VPS.

---

### Perintah Berguna PM2:
*   `pm2 list`: Melihat status semua aplikasi.
*   `pm2 logs drama-bot`: Melihat log/error dari bot.
*   `pm2 logs hls-proxy`: Melihat log dari proxy.
*   `pm2 restart all`: Memulai ulang semua layanan.
