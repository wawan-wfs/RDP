# Catatan pemulihan dari chat

Isi repo baru ini merupakan rekonstruksi dokumentasi dan diagnostik berdasarkan catatan percakapan. Nomor commit dan run di bawah adalah referensi historis repo lama. Akses ke source, log lengkap, dan hasil runtime lama tidak tersedia ketika repo baru dibuat.

## Windows Workspace

- Run lama `43440256689` dilaporkan berhenti di **Install Apps in Parallel**. Installer npm OmniRoute 3.8.53 tercatat mencapai batas waktu 20 menit pada langkah CLI, sebelum Tailscale dan RDP dimulai.
- Perbaikan di PR #6 dilaporkan memisahkan status installer dari penyiapan Tailscale/RDP. Timeout atau kegagalan per aplikasi masuk ke App Status dan tidak membatalkan inisialisasi koneksi. Regresi dilaporkan lulus pada run `43446498552`. Ini bukan bukti login RDP atau pemasangan OmniRoute di desktop.
- Catatan lama lain mencakup ArtCraft (commit `d3cbf1c`), shortcut desktop ganda, layar penuh, wallpaper hitam, dan verifikasi executable MetaTrader. Installer dan orkestrasi asli tidak dipulihkan.

## Linux Workspace

- Baseline lama memakai XRDP sebagai akses utama dan memberi pilihan akses web. Debian/Xfce, Chromium, hostname `rdp-runner`, Cookie-Editor, serta GoFullPage tercatat. Catatan awal memakai `rdp`; koreksi terakhir meminta `RDP` setelah login huruf kecil menghasilkan layar gelap pada setup saat itu.
- Commit lama `4eab54e` dilaporkan meluluskan regresi XRDP/PAM, beberapa aplikasi, dan Tailscale. Linux MT4/MT5 via Wine tidak dianggap selesai hanya karena executable tersedia.
- Uji penerimaan berikutnya: verifikasi akun PAM yang benar, login Xorg sampai desktop terlihat, lalu cek browser dan ekstensi dari sesi pengguna. Mode web dan provisioning paket tidak termasuk snapshot ini.

## macOS Workspace

- Bukti chat lama menunjukkan SSH berfungsi dan identitas konsol akhirnya sama dengan akun `wfsremote`. Sebelumnya ada ketidaksesuaian antara konsol dan akun SSH.
- Laporan lama mencatat respons RFB `003.889`, tipe keamanan `[30, 33, 36, 35]`, dan Apple authentication ditawarkan. Itu hanya bukti negosiasi, bukan login atau kontrol desktop.
- Finder dan Dock awalnya tidak terlihat dalam pemeriksaan sesi. Preview browser kemudian menunjukkan desktop, tetapi TigerVNC masih hitam atau hanya menampilkan kursor.
- Uji penerimaan berikutnya: dari klien di jaringan privat, cocokkan identitas konsol dengan akun yang diberi akses, lalu buktikan tampilan, klik, dan input keyboard melalui Screen Sharing. Skrip diagnostik baru tidak mengaktifkan layanan dan tidak menggantikan uji ini.
