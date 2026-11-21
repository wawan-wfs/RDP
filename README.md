<div align="center">

# WFS Remote Workspaces · Rebuild

**Windows RDP / noVNC · Linux XRDP / Selkies · macOS SSH / Screen Sharing**

Tiga workflow manual, akses melalui tailnet privat, dan status koneksi yang terpisah dari pemasangan aplikasi.

**[Mulai](#mulai)** · **[Windows](#windows)** · **[Linux](#linux)** · **[macos](#macos)** · **[Pengujian](#pengujian)**

</div>

> [!IMPORTANT]
> Ini versi baru yang dibangun dari ZIP historis RDP, dokumentasi, dan catatan pengembangan. Bukan salinan byte-identik dari repo lama. Semua pilihan yang tercatat dipetakan di [matriks fitur](docs/PARITY.md), termasuk yang butuh pengujian runner atau instalasi interaktif.

## Tiga workflow

| Workflow | Default | Akses |
| --- | --- | --- |
| [windows-remote-workspace.yml](.github/workflows/windows-remote-workspace.yml) | Windows 2025 · RDP · 6 jam | RDP asli, noVNC browser, atau keduanya |
| [linux-remote-workspace.yml](.github/workflows/linux-remote-workspace.yml) | Ubuntu · KDE · XRDP · 6 jam | XRDP X11, Selkies Webtop, atau keduanya |
| [macos-remote-workspace.yml](.github/workflows/macos-remote-workspace.yml) | macOS 15 · SSH + coba VNC · 1 jam | SSH, Apple Screen Sharing jika tersedia, screenshot privat |

## Mulai

1. Ekstrak **isi folder** paket ke root repo Anda. Pastikan folder tersembunyi `.github` ikut tersalin. Tiga file YAML membutuhkan direktori `shared/`, `windows/`, `linux/`, dan `macos/`, jadi jangan menyalin hanya ketiga YAML-nya.
2. Pada repo privat, simpan secret yang relevan lewat **Settings → Secrets and variables → Actions**. Koneksi memakai Tailscale dan aturan akses tailnet, bukan IP publik atau Cloudflare.
3. Buka **Actions → WFS [OS] Remote Workspace → Run workflow**. Untuk percobaan pertama pilih satu jam dan opsi aplikasi minimum. Pilih `validation_only=true` untuk memeriksa kode di runner asli tanpa secret atau sesi remote.
4. Buka **Summary** dari run yang aktif. Alamat koneksi muncul segera setelah layanan lolos pemeriksaan lokal, **sebelum** instalasi aplikasi. Setelah instalasi, Summary menambahkan status aplikasi.
5. Gunakan perangkat yang sudah diizinkan pada tailnet. Hentikan run saat selesai dan simpan pekerjaan sebelum runner sementara hilang.

Pakai GitHub-hosted runner hanya untuk pengembangan atau pengujian software yang terkait dengan repo. Untuk lab umum, gunakan host milik Anda yang terisolasi dan `runner_type=self-hosted`. Labelnya `wfs-windows`, `wfs-linux`, atau `wfs-macos`. Pasang dan autentikasi Tailscale lebih dulu di host itu, lalu set repository variable `WFS_DEDICATED_RUNNER=true`. Jangan jalankan paket ini di mesin utama yang sedang dipakai orang lain. Paket mengubah konfigurasi lab dan beberapa aplikasi OS dapat tetap terpasang pada host persisten. [Ketentuan GitHub Actions](https://docs.github.com/en/site-policy/github-terms/github-terms-for-additional-products-and-features#actions)

| Secret | Untuk apa |
| --- | --- |
| `TAILSCALE_AUTH_KEY` | Node GitHub-hosted, gunakan auth key ephemeral/tagged yang sesuai ACL. Alias lama `TAILSCALE_AUTHKEY` diterima |
| `RDP_PASSWORD` | Windows RDP, Linux XRDP, serta akun SSH dan autentikasi preview macOS |
| `VNC_PASSWORD` | Windows noVNC dan browser Selkies Linux. Password ini berbeda dari autentikasi Apple Screen Sharing |

Jangan taruh nilai secret pada input, URL, file repo, atau tangkapan layar Summary. Windows RDP memerlukan minimal 12 byte, tiga jenis karakter, dan password yang tidak memuat nama akun. Default `same_from_secret`. Mode `random_each_run` menurunkan password dari secret dan Run ID secara lokal, tidak menampilkannya di Summary. Lihat [cara menghitung password per-run](docs/OPERATIONS.md#password-per-run).

Hostname default `rdp-runner` dengan `same_each_run`. Jika ingin sesi paralel, pilih `unique_each_run` agar node memiliki sufiks run dan attempt. Pada self-hosted, alamat dan nama aktif berasal dari node Tailscale yang sudah ada. Selalu salin alamat aktual dari Summary. Sesi 1/3/6 jam tetap dibatasi waktu job dan menyisakan waktu cleanup, jadi enam jam bukan enam jam penuh setelah setup.

## Windows

### Upgrades from the uploaded Windows workflow

The user-supplied previous version, **Windows RDP with Apps**, was reviewed as a feature reference. The new version keeps its selectable desktop applications, Chrome extensions, IDE extension setup, desktop shortcuts, MetaTrader, and optional administrator access, while retaining Tailscale-only remote access, noVNC, timeout controls, and cleanup. This is an enhanced rebuild, not a byte-identical restoration.

- The Windows Administrator token is checked using SID **S-1-5-32-544** and PowerShell **WindowsBuiltInRole.Administrator**, rather than the localized display string.
- `rdp_user_role` is **standard** by default; choose **administrator** for the old workflow's privileged RDP account (UAC stays enabled). The temporary account is removed during cleanup.
- `desktop_profile` adds **balanced** (default) and **responsive** per-user visual preferences without disabling Defender, Firewall, or system services.
- Chrome's **Cookie-Editor** and **GoFullPage** remain managed-policy extensions. IDE extensions **OpenAI/Codex** and **Office Viewer** are scheduled for the actual RDP user's first login, with shortcuts for manual retry. Configured does not mean completed or verified.
- The separate **wfs-windows-apps** artifact is an offline application status dashboard; download it from the run's Artifacts section.


- `rdp` memakai **TCP 3389**, NLA, dan akun standar sementara `RDP`. Jalankan `mstsc /v:IP-TAILSCALE:3389` dari PC Windows. `/f` membuka mode layar penuh.
- `novnc` memakai TightVNC loopback plus bridge Python/noVNC di x64. Default **HTTP privat port 6082** melalui Tailscale, atau pilih `tailscale_https` untuk mencoba HTTPS port 443 lalu fallback TCP jika HTTPS tidak tersedia. Untuk `vnc_password_mode=same_from_secret`: jika `VNC_PASSWORD` berisi 8+ karakter ASCII huruf, angka, underscore atau hyphen, password VNC ialah **8 karakter pertama**. Jika secret memuat tanda baca atau Unicode, password VNC menjadi **8 karakter heksadesimal pertama SHA-256** dari string `wfs-windows:vnc-compat:v1:` diikuti isi secret. Secret asli tidak dicetak. Lihat perintah lokal di bawah.
- `both` menguji jalur RDP dan noVNC secara terpisah. Jika salah satu gagal, yang lulus tetap berjalan. Desktop console noVNC mungkin berbeda dari sesi RDP. Aktifkan scaling dengan URL Summary dan gunakan tombol fullscreen atau F11.
- Opsi runner mencakup 2025, 2022, latest, ARM64 untuk RDP, dan 2025 VS2026 sesuai ketersediaan runner akun. Pada GitHub-hosted, `windows-11-arm` + `novnc` atau `both` otomatis memakai **Windows Server 2025 x64** agar opsi akses yang dipilih tetap tersedia. Pergantian image tercatat di log dan Summary. Self-hosted ARM64 tetap pilih `rdp` atau gunakan host x64 untuk noVNC.
- Chrome, WinRAR, Node.js LTS, VS Code, Antigravity, CapCut, Shotcut, ArtCraft Launcher, MT4 Exness, MT5, 9Router, OmniRoute, Codex, Claude Code, Hermes, OpenClaw, dan OpenCode tersedia sebagai default atau pilihan. Policy **Cookie-Editor + GoFullPage** diterapkan, lalu cek ekstensi aktual di profil browser.
- Chrome/MSI memiliki jalur fallback vendor. Installer tertentu yang butuh profil user disiapkan untuk login RDP atau shortcut. **Pending interactive** berarti belum terbukti terpasang. Tidak ada login otomatis ke broker atau provider AI.

Di tab **Summary**, kartu koneksi muncul sebelum pemasangan aplikasi, termasuk perintah RDP layar penuh, tautan browser privat, dan hasil tiap pemeriksaan. Jika setup gagal, **Setup timeline** menandai tahap yang gagal, termasuk saat preflight belum menulis konfigurasi. Hasil aplikasi tampil terpisah agar timeout installer tidak disalahartikan sebagai kegagalan koneksi.

Untuk tampilan dashboard, unduh **`wfs-windows-connection`** dari bagian **Artifacts** pada run Windows, ekstrak ZIP, lalu buka HTML di browser. Dashboard dapat dibuka offline dan tetap menampilkan tahap yang gagal jika Tailscale gagal bergabung. Ini adalah rekaman saat setup, bukan status sesi secara langsung. Password dan auth key tidak disertakan.

## Linux

- Default **Ubuntu KDE + XRDP**, username **`RDP`** huruf besar. Jika prompt XRDP menampilkan pilihan sesi, pilih **Xorg**.
- `novnc` tetap nama input kompatibilitas. Browser sebenarnya memakai **Selkies Webtop**, bukan noVNC, dengan username default `wfs`. Gunakan HTTPS port **443** bila Serve tersedia atau **6082** di tailnet dengan sertifikat bawaan Webtop. Cek alamat sebelum menerima sertifikat.
- Mode `both` memakai satu container tetapi dua sesi desktop dengan profil berbeda. Ubuntu, Debian, Fedora, Alpine, dan Arch memakai Webtop native. **Arch dan Alpine KDE hanya browser**. Ubuntu LXQt tersedia untuk XRDP saja. **IGOS Nusantara** tetap opsi eksperimen ISO/QEMU melalui Xfce/RDP di runner self-hosted dengan ISO lokal.
- Gunakan Chromium yang tersedia lebih dulu, tanpa memasang Chrome. Kebijakan **Cookie-Editor + GoFullPage** diterapkan. Jika image Ubuntu tidak menyediakan Chromium, installer mencoba Chromium dari Playwright.
- Pilihan VS Code, Antigravity, Shotcut, router/agent, ArtCraft, bundle, MT4/MT5 Wine, dan WebTerminal tersedia sesuai distro. CapCut native berada di Windows. Instalasi GUI Wine ditandai interaktif, bukan diklaim otomatis.

## macOS

- Runner Apple Silicon/Intel macOS 15/26 sesuai label yang tersedia, bukan Hackintosh. Dari Windows PowerShell buka `ssh -p 2222 wfsremote@IP-TAILSCALE`. Cocokkan fingerprint di Summary sebelum menerima host key.
- Mode `both` tidak mematikan SSH jika Screen Sharing tidak tersedia. Apple VNC **port 5900** hanya dipublikasikan bila server yang sudah diaktifkan melalui metode yang diotorisasi menjawab RFB. RFB ready **tidak membuktikan login atau mouse/keyboard**.
- Preview **port 6081** memakai tombol **Capture one frame**, password, dan cooldown 60 detik. Ia hanya dapat mengambil gambar dari akun yang berhak dan berada di sesi console. Jika izin Screen Recording belum diberikan, preview menampilkan kegagalan, tidak menonaktifkan proteksi. [Panduan Apple](https://support.apple.com/en-me/guide/remote-desktop/apd8b1c65bd/mac)
- Opsi aplikasi VS Code, Codex, Claude Code, bundle developer/media, dan MetaTrader WebTerminal. WebTerminal tidak menjalankan EA desktop.

### Windows native RDP firewall and noVNC password

Perbaikan run [44957296327](https://github.com/wawan-wfs/RDP/actions/runs/44957296327):
- Firewall sekarang **tidak** mengikat aturan pada `-InterfaceAlias` dari adaptor virtual. Aturan allow TCP 3389 hanya menerima alamat lokal Tailscale dengan sumber `100.64.0.0/10`; IPv4 lain, IPv6, dan UDP 3389 diblokir. Defender, Windows Firewall, dan NLA tetap aktif. Cleanup memulihkan konfigurasi RDP bawaan.
- noVNC tidak gagal hanya karena secret mengandung `!`, `@`, atau Unicode. Jika format secret tidak kompatibel dengan VNCAuth, aplikasi otomatis memakai password ASCII hasil SHA-256. Untuk menghitung **password noVNC Anda sendiri** di PowerShell 7 tanpa menyebarkan secret ke log:

```powershell
$secret = Read-Host 'Masukkan nilai VNC_PASSWORD'
if ($secret -cmatch '^[A-Za-z0-9_-]{8,}$') {
    $vncPassword = $secret.Substring(0,8)
} else {
    $bytes = [Text.Encoding]::UTF8.GetBytes('wfs-windows:vnc-compat:v1:' + $secret)
    $vncPassword = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant().Substring(0,8)
}
Write-Host "Password noVNC: $vncPassword"
```

### Windows Tailscale IPv4 readiness

Jika Tailscale Action sudah terhubung tetapi `tailscale ip -4` belum menghasilkan IPv4, workflow kini menunggu dengan polling terbatas serta mencoba `tailscale status --json` (`Self.TailscaleIPs`). Hanya alamat IPv4 privat dalam `100.64.0.0/10` yang diterima. Diagnostik `WFS/TAILNET` dicetak ke log tanpa auth key atau alamat lain; bila tetap tidak tersedia, step **06** gagal dengan pesan spesifik. Ini menangani kegagalan run [44956502973](https://github.com/wawan-wfs/RDP/actions/runs/44956502973) yang berhenti setelah Tailscale berhasil connect namun IP belum terbaca.

## Pengujian

Mode **`validation_only=true`** tersedia di ketiga workflow. Mode ini tidak mengambil secret atau membuka port remote. Untuk tes lokal dari root paket:

```bash
python3 -m pip install -r tests/requirements.txt
python3 tests/test_workspaces.py
python3 windows/test_novnc.py
python3 windows/test_tailnet_ip.py
python3 tests/linux_mock.py
```

Untuk tes native Windows tambahkan `pwsh -File tests/verify-windows.ps1`. Prosedur acceptance lintas perangkat dan batasan masih perlu diuji di host asli ada di [OPERATIONS](docs/OPERATIONS.md).


> **Windows Legacy Base Enhanced:** Workflow Windows sekarang berbasis YAML `windows-rdp-with-apps (6).yml` yang diunggah, termasuk pilihan aplikasi/shortcut yang lengkap dan tambahan RDP/noVNC, dashboard, serta cleanup. [Lihat panduan dan batasan pengujian](docs/WINDOWS_LEGACY_BASE.md).
