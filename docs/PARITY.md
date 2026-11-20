# Matriks fitur lama dan rebuild

Baseline yang dipakai adalah `RDP-main.zip` kiriman pengguna, revisi ekspor `13329659b69300f279a70feea6077f9e52323697`, ditambah README asli terverifikasi dan patch PR #6 yang masih tersedia. ZIP lama hanya memuat enam YAML lama dan bukan source lengkap terbaru. Tiga workflow ini adalah implementasi baru.

| Area | Yang dibawa ke rebuild | Apa yang masih perlu dibuktikan |
| --- | --- | --- |
| Operasi | Tiga YAML manual saja, pilihan 1/3/6 jam, default hostname dan username, opsi unik, mode secret/per-run, Summary, cleanup dan perintah diagnosis | Koneksi eksternal dan cleanup di runner masing-masing |
| Windows | RDP NLA, noVNC dengan VNC password, pilihan keduanya, Serve TCP/HTTPS fallback, scaling browser, wallpaper VNC tidak dipaksa hilang, fallback dari installer opsional, shortcut tetap bernama sama | Firewall/Task Scheduler/TightVNC asli, console framebuffer dan keyboard/mouse, noVNC melalui Serve penuh |
| Aplikasi Windows | Chrome, Cookie-Editor, GoFullPage, WinRAR, Node, VS Code, Antigravity, CapCut, Shotcut, MT4/MT5, ArtCraft, semua router dan coding/AI agents yang tercatat | Versi paket, deteksi hasil aktual dan login non-otomatis. Instalasi user-scoped bisa disiapkan saat logon atau melalui shortcut |
| Linux | Ubuntu KDE default, pilihan distro/desktop, XRDP X11, Webtop Selkies, both, fallback private TCP, mode password dan kapitalisasi RDP, Chromium/ekstensi, bundle, ISO IGOS | Matriks kombinasi distro dan keberhasilan login Xorg. IGOS hanya lab eksperimen. MT4/5 via Wine dapat memerlukan interaksi sehingga tidak diklaim terpasang otomatis |
| macOS | Runner Apple ARM/Intel, SSH port 2222, opsi VNC, screenshot terpisah port 6081, autentikasi preview, console/WindowServer diagnosis, caffeinate dan opsi aplikasi | Screen Recording dan login GUI. Tidak memakai bypass TCC. Apple VNC yang menjawab RFB belum terbukti kendali penuh |
| Validasi | Cek YAML, pilihan konfigurasi, RFB/RDP, timeout, batas tailnet, autentikasi dan cooldown preview, bridge noVNC. Tes PowerShell dari PR #6 diadaptasi ke pengujian manual | Jalankan mode `validation_only` di native lab. Paket diuji secara lokal tanpa GitHub deployment |
| Fitur khusus lama | Tidak mempertahankan workflow duplikat Windows/MT5/Multi-OS. Path fungsi MT4/MT5 ada di installer baru. Opsi akses resmi macOS tetap tersedia | Controller Apple VNC Windows khusus dan worker ScreenCaptureKit dari repo terbaru tidak tersedia sebagai file asli, dan tidak diklaim direplikasi. Browser macOS hanya screenshot read-only |

## Perubahan yang disengaja

- Shell tidak menerjemahkan input user langsung sebagai kode. Nilai konfigurasi divalidasi dan passphrase tidak ditulis dalam dashboard.
- Layanan remote diuji dan diumumkan sebelum installer yang lambat. Kali ini paket npm dipisahkan per prefix agar kegagalan OmniRoute tidak menghapus CLI yang sudah berhasil.
- Windows RDP memakai akun standar sementara dan NLA. Tidak mematikan antivirus, Windows Firewall, atau batas keamanan OS.
- Tidak ada public forwarding, Cloudflare, atau loop yang memperpanjang sesi melewati timeout Actions.
- SSH macOS diikat ke loopback dengan host key per run. Port publik tidak dibuka dan permission GUI tetap mengikuti Apple.
