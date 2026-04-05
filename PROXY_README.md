# HLS Proxy Server (Node.js)

Proxy server ini dirancang untuk menangani streaming **HLS (.m3u8 dan .ts)** dengan melakukan bypass pada pembatasan CDR (CORS/Referer).

### Cara Kerja Utama:

1.  **CORS Middleware**: Menggunakan library `cors()` agar manifest `.m3u8` dan data `.ts` dapat diakses oleh player web (seperti Video.js atau HLS.js) dari domain mana pun tanpa error 'Blocked by CORS'.
2.  **Manifest Rewriting (.m3u8)**: 
    *   Setiap baris divalidasi.
    *   Jika baris berisi path relatif atau URL segmen, sistem akan mengubahnya menjadi **Absolute URL** dan membungkusnya kembali ke endpoint `/proxy`.
    *   Ini memastikan browser akan terus meminta segmen video (`.ts`) melalui proxy kita, bukan langsung ke CDN yang memblokir akses.
3.  **Binary Streaming (.ts)**:
    *   Untuk file media, data ditarik menggunakan `responseType: 'stream'`.
    *   Data ditarik secara binary untuk menghindari korupsi data.
4.  **Static Headers Bypass**:
    *   Setiap permintaan ke CDN menyertakan `Referer`, `Origin`, dan `User-Agent` statis (iPhone Safari) untuk mengelabui sistem proteksi CDN.

### Cara Instalasi:
1.  Buka terminal/PowerShell di folder proyek.
2.  Instal library:
    ```powershell
    npm install
    ```
3.  Jalankan server proxy:
    ```powershell
    node proxy.js
    ```

### Contoh Penggunaan:
`http://localhost:3000/proxy?url=https://secure-content.cdn.com/playlist.m3u8`
