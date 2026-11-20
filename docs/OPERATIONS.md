# Operasi dan verifikasi

## Password per-run

Di mode default, gunakan secret sesuai protokol. Jangan cetak password dari runner. Untuk mode `random_each_run`, gunakan contoh PowerShell ini **di perangkat sendiri** dan ubah platform/role/Run ID. Pengisian master secret memakai prompt yang tidak menggemakan teks.

```powershell
$Platform = 'linux' # windows, linux, macos
$Role = 'rdp'      # Windows/Linux: rdp atau web; macOS: remote
$RunId = '123456789'
$Secure = Read-Host 'Masukkan nilai secret asal' -AsSecureString
$Raw = [Net.NetworkCredential]::new('', $Secure).Password
$Label = switch ($Platform) {
    'linux' { "wfs:${RunId}:${Role}" }
    'windows' { "wfs-windows:${RunId}:${Role}" }
    'macos' { "wfs-macos:${RunId}:remote" }
}
$Hmac = [Security.Cryptography.HMACSHA256]::new([Text.Encoding]::UTF8.GetBytes($Raw))
try {
    $Hex = ([BitConverter]::ToString($Hmac.ComputeHash([Text.Encoding]::UTF8.GetBytes($Label)))).Replace('-','').ToLowerInvariant()
    if ($Platform -eq 'windows' -and $Role -eq 'web') { $Hex.Substring(0,8) }
    elseif ($Platform -eq 'windows') { 'Wf!' + $Hex.Substring(0,21) }
    else { $Hex.Substring(0,24) }
} finally {
    $Hmac.Dispose()
    Remove-Variable Raw,Secure,Hex -ErrorAction SilentlyContinue
}
```

## Uji dari perangkat lain

| Jalur | Yang harus diuji dari perangkat tailnet |
| --- | --- |
| Windows RDP | Sambung dengan `mstsc`, cocokkan user, buka Notepad, cek input, shortcut, dan logoff |
| Windows noVNC | Gunakan URL Summary. Uji password salah dan benar, lihat console, lalu gerakkan mouse dan ketik |
| Linux XRDP | Cek sesi Xorg, desktop KDE/Xfce yang diharapkan, kapitalisasi login, dan peluncuran Chromium |
| Linux Selkies | Uji browser HTTPS, penolakan password salah, login benar, dan input. Pastikan mode both memang dua sesi |
| macOS SSH | Cocokkan fingerprint, masuk, lalu jalankan `id -un` |
| macOS VNC | Uji autentikasi Apple, tampilan Finder, lalu input pada sesi yang diotorisasi |
| macOS Preview | Coba tanpa password, kemudian autentikasi untuk klik **Capture one frame**. Preview bukan VNC dan tidak menerima input |

Lakukan juga pemeriksaan negatif dari jaringan di luar tailnet. Port workspace seharusnya tidak terbuka di sana. Periksa ACL tailnet dan perangkat node yang benar. Windows dan Linux memiliki dua arti port 6082. Windows memakai HTTP privat, Linux HTTPS.

## Troubleshooting singkat

- **Node tidak ditemukan**. Baca step Tailscale dan periksa jenis key, device approval, tag ACL, serta tailnet dari PC klien. Jangan pakai lagi IP run lama.
- **RDP invalid credentials**. Windows/Linux pakai nama login pada Summary. Pada Linux, `RDP` dan `rdp` berbeda. Windows gunakan format `.\RDP` bila klien mengirim domain lain.
- **HTTPS selkies warning**. Port 6082 membawa sertifikat internal Webtop, bukan sertifikat tailnet. Jika tidak bisa memastikan identitas endpoint, pilih jalur Serve HTTPS port 443 atau gunakan XRDP.
- **Aplikasi berjalan lambat**. Akses remote disiapkan dulu. Setelah aplikasi selesai, cek status per aplikasi. Timeout atau fallback interaktif tidak dianggap installed. Pada Windows, program per-user yang dipilih setelah login bisa memerlukan logout/login ulang untuk memicu tugas.
- **macOS preview 503 atau VNC hitam**. Lihat sesi console, izin Screen Recording, serta status Screen Sharing. Gunakan SSH untuk tetap bekerja. Jangan mencoba memberi izin GUI lewat skrip yang mengubah kebijakan privasi macOS.
- **Cleanup**. Jangan hanya menutup konsol runner. Cancel workflow setelah disconnect. Untuk self-hosted, repo ini hanya menutup listener/resource yang ia buat. Konfigurasi lab atau aplikasi yang memang dipasang mungkin perlu dibersihkan oleh admin.

## Sumber operasional

- [GitHub-hosted runner labels](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job)
- [Tailscale GitHub Action](https://tailscale.com/docs/integrations/github/github-action) dan [Serve](https://tailscale.com/docs/reference/tailscale-cli/serve)
- [LinuxServer Webtop](https://docs.linuxserver.io/images/docker-webtop/) dan [Selkies](https://docs.linuxserver.io/selkies/)
- [TightVNC MSI docs](https://www.tightvnc.com/docs.php) dan [noVNC releases](https://github.com/novnc/noVNC/releases)
- [Apple Remote Management](https://support.apple.com/en-me/guide/remote-desktop/apd8b1c65bd/mac)
