## 🪟 Windows: Legacy Base Enhanced (22 November 2026)

**Windows now uses the attached `windows-rdp-with-apps (6).yml` as its actual structural source**, not the earlier minimal rebuild. The original PowerShell application installer groups remain embedded in `.github/workflows/windows-remote-workspace.yml`: Chrome, WinRAR, Node LTS, Visual Studio Code, Antigravity, CapCut, Shotcut, MetaTrader 4/5, 9Router, OmniRoute, Codex, Claude Code, Hermes, OpenClaw, OpenCode, ArtCraft, per-user extension preparation, multi-worker installation with timeouts, and Public Desktop / Start Menu shortcuts. The source's legacy install steps are not claimed to have all passed on a Windows runner yet; GitHub Actions can still reject installer downloads or app-specific installers.

### New workflow options

| Option | Default | Notes |
|---|---|---|
| `remote_access` | `rdp` | `rdp`, `novnc`, `both`; two independent remote transports |
| `runner_type` | `github` | `self-hosted` requires an isolated and explicitly approved `wfs-windows` lab runner |
| `validation_only` | `false` | Static/Python/PowerShell checks without remote credentials or sessions |
| `rdp_username` | `RDP` | Temporary non-reserved Windows username |
| `rdp_user_role` | `administrator` | Mirrors old workflow's admin group membership, with UAC enabled; `standard` available |
| `desktop_profile` | `balanced` | `responsive` opts into the old Windows performance-tuning step |
| `vnc_password_mode` | `same_from_secret` | `random_each_run` derives an eight-character password using HMAC |
| `novnc_transport` | `tailscale_tcp` | Private TCP 6082; `tailscale_https` attempts MagicDNS HTTPS first |

**Only three workflows exist:** Windows, Linux and macOS. Their triggers are `workflow_dispatch` only. A push to `main` does not launch a runner.

### Safer setup and known failures fixed in code

1. RDP/noVNC is configured **before** the original legacy application installers. If one remote method fails, the other can still be used if it passes its own readiness checks. If both fail, application installation is skipped.
2. Windows Server 2025 rejected `New-NetFirewallRule` with invalid range syntax and virtual `-InterfaceAlias`. The new RDP path verifies Firewall **enabled + DefaultInboundAction Block**, disables broad built-in Remote Desktop allow rules, and installs only a TCP 3389 allow rule scoped to the assigned **Tailscale local IPv4** and sources in **100.64.0.0/10**. It preserves NLA and TLS.
3. noVNC previously returned MSI **1619** for TightVNC 2.8.90. The new code validates the downloaded file's MSI header and signature before installation, and attempts the signed WinGet `GlavSoft.TightVNC` package as fallback if necessary. It requires actual TightVNC service, local RFB protocol and loopback binding to pass; no false success is reported.
4. The `rdp_password_mode=random_each_run` password is now derived from `RDP_PASSWORD` rather than posted in logs. `VNC_PASSWORD` may contain symbols; for fixed mode an eight-character ASCII-compatible password is derived when the original secret is not VNCAuth-compatible. See the compatible-password procedure below.
5. Visual dashboards: a separate connection HTML snapshot is available **before** the large app installs, and a separate app status dashboard **after**. Status `configured`/`attempted` is not the same as verified installation.
6. On job cancellation or failure, the workflow attempts to restore saved RDP settings, remove its temporary account, stop owned noVNC processes, and restore the two Windows Installer policy values it changed. Tailscale action performs hosted-node cleanup; pre-existing self-hosted tailnet identities are not logged out.

### Required Repository Secrets

Set `TAILSCALE_AUTH_KEY`, `RDP_PASSWORD`, and (for noVNC) `VNC_PASSWORD` in Settings → Secrets and variables → Actions. **Do not paste passwords into workflow inputs or commit them to YAML.** For password derivation modes, the secret is still required as the cryptographic seed. Random mode is stable for the run ID; it is not automatically displayed in any log.

To compute the eight-character noVNC password for fixed-secret mode locally (never in GitHub logs):

```powershell
$secret = Read-Host 'Input your VNC_PASSWORD secret'
if ($secret -cmatch '^[A-Za-z0-9_-]{8,}$') {
  $password = $secret.Substring(0,8)
} else {
  $inputBytes = [Text.Encoding]::UTF8.GetBytes('wfs-windows:vnc-compat:v1:' + $secret)
  $password = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($inputBytes)).ToLowerInvariant().Substring(0,8)
}
Write-Host "noVNC password: $password"
```

For the per-run mode, compute the HMAC using the run ID and role; the derivation is documented in `shared/workspace.py`. You can alternatively use a compatible fixed `VNC_PASSWORD` to avoid extra calculation.

### Validation and limitations

- Local: `python tests/test_windows_legacy.py`, `python windows/test_tailnet_ip.py`, `python windows/test_novnc.py`, and `python tests/test_workspaces.py` (after `pip install -r tests/requirements.txt`). On a Windows runner, validation also parses scripts via `tests/verify-windows.ps1`.
- On GitHub choose **Run workflow** from **`main`**. Use `validation_only=true` first. Then choose `remote_access=rdp` with the minimal app selection to verify interactive RDP, and only then add optional apps or both protocols. Existing failed run logs refer to older commits and cannot validate these changes.
- The Windows-only GitHub-hosted runner has finite GitHub Actions session/runtime limits; a successful local TCP/RFB probe does not prove interactive logon, mouse, video, or GPU stability. Verify those using a separate device on the same tailnet.
- GUI installers/Chrome policies are external components; some may be interactive or require first login. Preserve complete application error logs, do not mark an app installed simply because the installer exited successfully.
- For general-purpose or long-running Windows laboratories, prefer your dedicated self-hosted runner and review GitHub's permitted Actions usage.
### Run 44961301879: Windows ARM64 Firewall profile fix

The latest run succeeded at Tailscale and created the temporary RDP account, but failed because a Windows Firewall profile did not report the required inbound-blocking default. On **disposable GitHub-hosted** Windows runners only, the RDP setup now snapshots the existing profile settings, temporarily enables all profiles with default inbound **Block**, verifies the effective ActiveStore state, and restores the original locally-restorable settings during cleanup. On self-hosted machines, the workflow continues to **fail closed** with a diagnostic rather than altering global firewall policy automatically. RDP port 3389 remains restricted to the assigned Tailscale local IP and Tailnet remote addresses, with NLA and TLS retained.

`NotConfigured` is not a restorable local value for `Set-NetFirewallProfile`; if an original profile had this GPO-only value, the cleanup preserves the stricter inbound Block state on the disposable hosted runner and logs a warning. No public RDP listener is intentionally opened. This code change has not been verified with a new live GitHub Actions RDP session.


### App availability and workflow identity batch · 22 November 2026

- The Actions display name is restored to **WFS Windows Remote Workspace**, while the user-provided legacy YAML remains the implementation base.
- Windows ARM64 is retained for RDP-only sessions without optional apps. If desktop apps, AI tools, ArtCraft, or browser desktop are selected, hosted runs automatically use **Windows 2025 x64** for broader installer compatibility; the preflight notice displays the fallback.
- The prior CapCut 9.4 hard-code is replaced with latest-catalog WinGet installation under the RDP account. ArtCraft resolves the **latest official GitHub release** and checks the matching SHA256SUMS before installing; no version is hard-coded.
- MT4/MT5 now request explicit installation folders and verify terminal executables. VS Code has an official Microsoft signed system-installer fallback. Claude Code can fall back to the official npm package when the native installer fails.
- OmniRoute desktop is now attempted from the verified official GitHub portable asset in addition to the existing CLI. If the release lacks a verifiable SHA256 digest, it is **not** installed and the status is reported separately; no unsigned download is silently trusted.
- Antigravity's RDP launcher no longer attempts to install extensions at each launch. Shortcuts are created in the Public Desktop/Start Menu without doubling the RDP-user desktop shortcut.
- The app audit records selected applications individually, with executable-present or missing status; a successful worker step does not imply an interactive app launch. The HTML dashboard now includes these app records.
- The Summary/HTML connection report shows **Tailscale IPv4, hostname, RDP command, user, and noVNC link when available**, never a password.
- Group timeout is lowered from 20 to 12 minutes. This is an upper bound, not proof that all installers succeed; failed installers remain visible for diagnosis.

Local regression coverage: tests/test_windows_legacy.py, tests/test_app_audit.py, tests/test_dashboard_connections.py, tests/test_windows_upgrade.py, and the existing workspace suites. Native PowerShell parsing and actual app launch on a new Windows runner still require a workflow run.

### noVNC timeout isolation and firewall restore (22 Nov 2026)

Live run [45006971739](https://github.com/wawan-wfs/RDP/actions/runs/45006971739) verified Windows RDP NLA, but the combined setup step was stopped after 22 minutes while starting noVNC after the Python bridge dependencies were installed. The precise blocking operation was not recorded in the old log. The workflow now separates the **both** mode into an RDP-primary step (7-minute cap) and an optional noVNC step (5-minute cap) so a web desktop timeout cannot prevent RDP application installation. An explicit failed noVNC ledger entry is written when the optional step fails, even on a GitHub-hosted timeout. The noVNC-only option remains strict: its own readiness must pass.

Extra stage markers before task registration, launch, probe, and tailnet relay will pinpoint a future noVNC hang. Cleanup now passes `'True'` / `'False'` string enum values to `Set-NetFirewallProfile -Enabled` instead of PowerShell Booleans (which the Windows cmdlet refused). If the original inbound action was `NotConfigured`, the hosted runner preserves Block and reports this limitation.

This improves failure isolation and diagnostics; it does not establish successful interactive browser control until verified in a new live run.


### Informasi koneksi dan password acak (22 November 2026)

Tahap **06c** kini menampilkan log `[WFS/ACCESS]` yang memuat jenis koneksi, IP Tailscale yang terverifikasi, hostname, MagicDNS bila tersedia, perintah RDP fullscreen, username, status dan URL noVNC, serta mode password. Job Summary dan HTML dashboard juga mencantumkan detail koneksi, tetapi tanpa password.

Input baru `reveal_random_password` memiliki default `false` untuk mencegah kebocoran kredensial. Saat `true` dan `rdp_password_mode` atau `vnc_password_mode` dipilih `random_each_run`, step **06c2** menampilkan password untuk endpoint yang benar-benar berstatus `ready` di **Job Summary saja**. Nilai secret sumber tetap tidak dicetak, password fixed-mode tidak ditampilkan, dan password tidak dimasukkan ke log biasa ataupun artefak HTML. Siapa saja dengan izin melihat run GitHub Actions dapat melihat password jika opsi ini diaktifkan.


### Audit aplikasi lengkap pada run #45010869094

Run tersebut berstatus **cancelled** karena sesi aktif dihentikan, bukan karena tahap installer sukses penuh. Artefak `wfs-windows-apps-1` menunjukkan 5 executable installed/detected (VS Code, Chrome, WinRAR, Node.js, OmniRoute Desktop), 3 configured (Antigravity IDE, 9Router, RDP role), dan 11 aplikasi lain tidak terdeteksi.

Penyebab dari log: GUI worker menghabiskan ~5 menit pada Antigravity, ~5 menit pada VS Code, lalu gagal pada CapCut karena PowerShell 5.1 menghasilkan native argument `install--id`. Akibat rethrow CapCut, task GUI berhenti sebelum Shotcut/MT4/MT5. CLI worker menghabiskan waktu pada npm OmniRoute dan dihentikan setelah 12 menit, sehingga Codex, Claude, Hermes, OpenClaw dan OpenCode tidak mendapat kesempatan selesai. ArtCraft mengembalikan error binary missing setelah MSI task.

Perbaikan: instalasi Shotcut/MT4/MT5 diprioritaskan sebelum IDE/CapCut; CapCut mengirim argumen native eksplisit, tanpa variabel otomatis `$args`; kegagalan optional app tidak memutus grup; OmniRoute Desktop (rilis resmi portabel) tidak lagi membutuhkan paket npm dengan native build berat; npm sekarang punya batas waktu per paket (165s) agar tidak menghabiskan waktu semua CLI; dan grup memiliki batas waktu lebih realistis untuk pilihan `both/all`, dengan audit executable tetap menjadi ukuran sebenarnya. Belum ada run baru yang memverifikasi seluruh pemasangan.


### Latest BOTH run: noVNC diagnosis + access details in main log

The run `45197537658` reports **RDP ready, noVNC failed**. Its browser stage was a continue-on-error step, and the generic failure recorder previously overwrote the more useful stage-specific reason. The new browser phase records its exact setup stage before failure; the recorder preserves that reason. noVNC's maximum step duration was increased to 12 minutes for first-time MSI/WinGet installation, and the bridge now reuses the setup-python runtime rather than creating a second virtual environment. If noVNC fails, the verified RDP endpoint and apps continue independently.

At step 18 (session keep-alive), a fresh **[WFS/ACCESS]** card repeats IP, hostname, MagicDNS, mode, RDP command, username, noVNC link/status and password mode directly in the visible log. Secret values remain excluded from the regular log and HTML artifact. Interactive desktop control still must be checked from an authorized tailnet client.


### Missing application recovery on the BOTH run (45197537658)

Six requested executables were not detected: CapCut, ArtCraft Launcher, Codex CLI, OpenCode, OpenClaw and 9Router. Step 13c fetches the latest official ArtCraft portable ZIP if the MSI has not produced an executable, verifying the release SHA256SUMS before extracting it. Step 13d retries missing npm CLI commands individually via the installed Node runtime with bounded 145-second attempts and leaves others running when one fails. CapCut may need an interactive per-user installation if its silent installer cannot run on the hosted Windows desktop.


### CapCut user-profile fallback

CapCut in the latest BOTH run did not have a verified executable after a headless user-scope install. The new 13e step checks the selected RDP user's profile and, if missing, creates a Startup shortcut that attempts WinGet installation only inside that user's real login session. It also adds **Install or Repair CapCut for RDP** to the common Start Menu. A per-user log is written under `%LOCALAPPDATA%\WFS\CapCut-Install.log`. Until the executable is actually detected, the app inventory reports **pending interactive**, not installed. This fallback is for cases where Windows headless silent installation cannot complete; it does not guarantee success until verified.


When the RDP session ends, cleanup removes the temporary CapCut login/start-menu shortcuts and retry script on hosted or reused machines, so they do not remain configured for unrelated users. The local workflow schema test uses a YAML loader that preserves the literal `on:` key.


### Run 45208451244 — fail-fast noVNC handshake repair

This completed BOTH-mode run showed RDP ready and noVNC failed, despite GitHub Actions marking the job successful. The TightVNC installation, localhost:5900 RFB probe, noVNC frontend, aiohttp dependency and background HTTP listener 6081 all succeeded. The previous `test_novnc.py --live` hung for 12 minutes at WebSocket/RFB verification. We replaced only the *live* smoke probe with a standard-library HTTP + RFC6455 upgrade + RFB-banner check, with a 25-second external timeout. Six mock-socket regression tests and a local integration test against the real aiohttp bridge plus mock VNC server passed. Interactive screen control and Tailscale Serve still need verification on the next hosted Windows run.

The same run's application artifact listed Chrome, WinRAR, Node.js, ArtCraft Launcher as detected. Other optional apps were not selected, rather than failed; app output now prints requested choices clearly.


### CLI recovery and validation hardening (24 November 2026)

No newer Windows run was available after the bounded noVNC probe fix. Source audit found invalid PowerShell variable interpolation (`$name:`) in the CLI recovery script, corrected to `${name}:`. Both primary and recovery npm installs now use Node/npm-cli.js directly, and recovery checks each CLI with a bounded `--version` probe. Claude npm fallback is included when the native per-user executable is absent. Shortcut and report paths include the shared CLI prefix and OmniRoute Desktop. Pending interactive apps no longer inflate executable counts. Validation-only runs check every regression suite independently, including the upgrade and dashboard tests, so an earlier failure is not masked by a later success. Live Windows validation remains pending.


The WebSocket probe now handles split RFB greetings, continuation frames and ping/pong, and the bridge caps TCP shutdown at three seconds. An early access card immediately after primary readiness prints the IP, hostname, and RDP command before optional browser setup; final reports still distinguish pending from failed noVNC. New regression fixtures cover the split greeting cases.


### Private Serve mapping gate (24 November 2026)

The browser setup now requires three bounded checks: TightVNC's local-only RFB listener, a local HTTP/WebSocket/RFB handshake, and the actual Tailscale Serve status JSON (TCP/6082 or HTTPS/443). The mapping must target loopback `127.0.0.1:6081`, and public Funnel must remain disabled. The generated noVNC URL is only labeled ready after these checks. The route is registered for cleanup before verification to prevent orphaned mappings. 11 pure regression tests validate valid and invalid Serve configurations; a live Windows session has not verified the new gate yet.
