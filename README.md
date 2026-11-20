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

- `rdp` memakai **TCP 3389**, NLA, dan akun standar sementara `RDP`. Jalankan `mstsc /v:IP-TAILSCALE:3389` dari PC Windows. `/f` membuka mode layar penuh.
- `novnc` memakai TightVNC loopback plus bridge Python/noVNC. Pilih x64. Default **HTTP privat port 6082** melalui Tailscale, atau pilih `tailscale_https` untuk mencoba HTTPS port 443 lalu fallback TCP jika HTTPS tidak tersedia. Windows noVNC memakai 8 karakter ASCII pertama dari secret. Untuk mode ini, gunakan password unik.
- `both` menguji jalur RDP dan noVNC secara terpisah. Jika salah satu gagal, yang lulus tetap berjalan. Desktop console noVNC mungkin berbeda dari sesi RDP. Aktifkan scaling dengan URL Summary dan gunakan tombol fullscreen atau F11.
- Opsi runner mencakup 2025, 2022, latest, ARM64 untuk RDP, dan 2025 VS2026 sesuai ketersediaan runner akun.
- Chrome, WinRAR, Node.js LTS, VS Code, Antigravity, CapCut, Shotcut, ArtCraft Launcher, MT4 Exness, MT5, 9Router, OmniRoute, Codex, Claude Code, Hermes, OpenClaw, dan OpenCode tersedia sebagai default atau pilihan. Policy **Cookie-Editor + GoFullPage** diterapkan, lalu cek ekstensi aktual di profil browser.
- Chrome/MSI memiliki jalur fallback vendor. Installer tertentu yang butuh profil user disiapkan untuk login RDP atau shortcut. **Pending interactive** berarti belum terbukti terpasang. Tidak ada login otomatis ke broker atau provider AI.

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

## Pengujian

Mode **`validation_only=true`** tersedia di ketiga workflow. Mode ini tidak mengambil secret atau membuka port remote. Untuk tes lokal dari root paket:

```bash
python3 -m pip install -r tests/requirements.txt
python3 tests/test_workspaces.py
python3 windows/test_novnc.py
python3 tests/linux_mock.py
```

Untuk tes native Windows tambahkan `pwsh -File tests/verify-windows.ps1`. Prosedur acceptance lintas perangkat dan batasan masih perlu diuji di host asli ada di [OPERATIONS](docs/OPERATIONS.md).
