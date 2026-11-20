# WFS Remote Workspaces

> Pemulihan dari catatan chat proyek wawanwfs/RDP. Bukan clone source lama dan tidak membawa riwayat commit, workflow, atau pengaturan runner lama.

Panduan koneksi dan diagnosis untuk mesin yang Anda miliki atau kelola. Gunakan jaringan privat Tailscale atau jaringan internal yang tepercaya. Jangan meneruskan port RDP, VNC, atau SSH langsung ke internet. Kredensial dan auth key tidak disimpan di repo.

| Platform | Jalur koneksi | Catatan pemulihan |
| --- | --- | --- |
| Windows | Remote Desktop atau MSTSC ke nama MagicDNS/IP Tailscale | Installer lama tidak tersedia. Regresi penanganan timeout pernah dilaporkan lulus, bukan bukti login RDP. |
| Linux | XRDP dengan sesi Xorg/Xfce. Akses web merupakan opsi historis. | Hostname pilihan sebelumnya rdp-runner. Dokumentasi lama pernah menyebut rdp, tetapi koreksi terakhir menggunakan RDP pada setup lama. Periksa nama akun yang benar di mesin sekarang. |
| macOS | SSH untuk diagnostik dan Apple Screen Sharing untuk desktop | SSH dan preview desktop pernah terlihat bekerja. Kontrol desktop TigerVNC belum terbukti dan layar hitam masih menjadi masalah terbuka. |

## Cara koneksi

### Windows

1. Pada host Windows yang mendukung Remote Desktop, aktifkan Remote Desktop melalui Settings dan izinkan akun yang akan dipakai.
2. Pastikan host dan klien terhubung ke jaringan privat yang sama, serta aturan jaringan dan firewall mengizinkan TCP 3389 hanya dari sumber yang diizinkan.
3. Dari klien Windows, buka **Remote Desktop Connection** dan masukkan nama MagicDNS atau IP Tailscale host. Layar penuh bisa dipilih dari tab Display.
4. Jika instalasi aplikasi gagal, catat status per aplikasi dan periksa koneksi RDP secara terpisah. MetaTrader, OmniRoute, dan installer lain belum diuji ulang di repo ini.

Referensi: [Windows RDP melalui Tailscale](https://tailscale.com/docs/solutions/access-remote-desktops-using-windows-rdp)

### Linux

1. Pada host Debian yang dikelola sendiri, siapkan XRDP, xorgxrdp, dan desktop Xfce dari repositori distro. Pastikan terdapat akun lokal non-root dan PAM dapat mengautentikasinya.
2. Cek akun menggunakan `getent passwd RDP` atau `getent passwd rdp` sesuai nama yang dibuat. Nama akun peka huruf besar/kecil. Jangan mencoba mengganti kapitalisasi tanpa memastikan akun itu memang ada.
3. Hubungkan klien RDP ke nama host privat, gunakan sesi **Xorg**, lalu login dengan akun lokal. Jika login berhasil tetapi desktop hitam, cek konfigurasi Xfce dan log layanan `xrdp` serta `xrdp-sesman`.
4. Chromium adalah pilihan browser yang tercatat. Riwayat juga mencantumkan Cookie-Editor dan GoFullPage. Mode akses web dan pemasangan ekstensi otomatis belum dipulihkan.

### macOS

1. Pada host milik Anda, gunakan **System Settings → General → Sharing**. Aktifkan Remote Login atau Screen Sharing sesuai kebutuhan dan batasi ke pengguna yang diizinkan. Jika Remote Management dipakai, ikuti opsi akses yang dikelola di sana.
2. Uji konektivitas dengan `ssh NAMA_AKUN@HOST_PRIVAT`. Contoh akun dari riwayat adalah `wfsremote`.
3. Dari Mac klien, coba **Screen Sharing** ke host privat. Port yang merespons atau autentikasi yang berhasil bukan bukti desktop dapat terlihat dan dikontrol.
4. Bila layar hitam atau hanya kursor yang terlihat, cek siapa pengguna konsol, apakah domain GUI tersedia, dan apakah Finder serta Dock berjalan. Jangan menganggap preview browser sebagai bukti kontrol VNC.

## Batas pemulihan

- Tidak menjalankan installer atau sesi remote otomatis dari GitHub Actions.
- Tidak ada bukti pengujian ulang koneksi Windows, Linux, atau macOS pada repo baru.
- Tidak ada public tunnel atau Cloudflare keep-alive yang dipulihkan.
- File workflow lama dan daftar aplikasi lengkap tidak tersedia dalam bahan yang berhasil ditemukan.
