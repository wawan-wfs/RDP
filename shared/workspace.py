"""Pure validation, connection status, deadlines and diagnostics for WFS."""
import argparse
from datetime import datetime, timezone
import hashlib
import hmac
import html
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import sys
import tempfile
import time

APP_INPUTS = {
    "ide_choice": ("none", "antigravity", "vscode", "both"),
    "editor_choice": ("none", "capcut", "shotcut", "both"),
    "metatrader_choice": ("none", "mt4", "mt5", "both"),
    "router_choice": ("none", "9router", "omniroute", "both"),
    "coding_agent_choice": ("none", "codex", "claude", "both"),
    "ai_agent_choice": ("none", "hermes", "openclaw", "opencode", "both", "all"),
}
WINDOWS = ("windows-2025", "windows-latest", "windows-2022", "windows-11-arm", "windows-2025-vs2026")
WINDOWS_BROWSER_FALLBACK = "windows-2025"
MACS = ("macos-15", "macos-26", "macos-15-intel", "macos-26-intel")
TAILNET = ipaddress.ip_network("100.64.0.0/10")
STATE = {"ready", "configured", "failed", "timed out", "installed", "attempted",
         "pending interactive", "unsupported", "skipped", "unavailable", "warning"}


def state_dir():
    name = "wfs-remote-" + os.environ.get("GITHUB_RUN_ID", "local") + "-" + os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    return Path(os.environ.get("RUNNER_TEMP", ".")).resolve() / name


def pick(d, key, choices, default):
    v = d.get(key, default)
    if v not in choices:
        raise ValueError(f"Invalid {key}; allowed: {', '.join(map(str, choices))}")
    return v


def config(os_name, d, run_id="local", attempt="1", runner_arch=""):
    defaults = {"remote_access": {"windows": "rdp", "linux": "rdp", "macos": "both"}[os_name]}
    modes = ("ssh", "vnc", "both") if os_name == "macos" else ("rdp", "novnc", "both")
    c = {
        "platform": os_name, "run_id": run_id, "attempt": attempt,
        "remote_access": pick(d, "remote_access", modes, defaults["remote_access"]),
        "duration_hours": pick(d, "duration_hours", ("1", "3", "6"), "1" if os_name == "macos" else "6"),
        "runner_type": pick(d, "runner_type", ("github", "self-hosted"), "github"),
        "hostname_mode": pick(d, "hostname_mode", ("same_each_run", "unique_each_run"), "same_each_run"),
    }
    host = d.get("tailscale_hostname", "rdp-runner") or "rdp-runner"
    if not re.fullmatch(r"[a-z](?:[a-z0-9-]{0,38}[a-z0-9])?", host) or not re.fullmatch(r"(?:local|[0-9]+)", run_id) or not re.fullmatch(r"[0-9]+", attempt):
        raise ValueError("Invalid hostname or run identifier")
    c["hostname"] = host if c["hostname_mode"] == "same_each_run" else f"{host}-{run_id}-{attempt}"
    if len(c["hostname"]) > 63:
        raise ValueError("Tailscale hostname plus run suffix exceeds 63 characters")
    for key, values in APP_INPUTS.items():
        c[key] = pick(d, key, values, "none")
    for key in ("rdp_password_mode", "vnc_password_mode", "password_mode"):
        c[key] = pick(d, key, ("same_from_secret", "random_each_run"), "same_from_secret")
    c["install_artcraft"] = str(d.get("install_artcraft", os_name == "windows")).lower() == "true"
    c["apps_bundle"] = pick(d, "apps_bundle", ("none", "developer", "office", "media", "all"), "none")
    c["rdp_username"] = d.get("rdp_username", "RDP") or "RDP"
    c["web_username"] = d.get("web_username", "wfs") or "wfs"
    c["remote_username"] = d.get("remote_username", "wfsremote") or "wfsremote"
    for key in ("rdp_username", "web_username", "remote_username"):
        v = c[key]
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,19}", v) or v.lower() in {"root", "admin", "administrator", "runner", "runneradmin", "daemon", "nobody", "abc", "ubuntu"}:
            raise ValueError(f"Invalid or reserved {key}")
    if os_name == "windows":
        c["windows_version"] = pick(d, "windows_version", WINDOWS, WINDOWS[0])
        c["novnc_transport"] = pick(d, "novnc_transport", ("tailscale_tcp", "tailscale_https"), "tailscale_tcp")
        browser = c["remote_access"] in {"novnc", "both"}
        hosted = c["runner_type"] == "github"
        c["windows_fallback"] = hosted and browser and c["windows_version"] == "windows-11-arm"
        c["windows_effective_runner"] = (
            WINDOWS_BROWSER_FALLBACK if c["windows_fallback"] else c["windows_version"]
        ) if hosted else "self-hosted / wfs-windows"
        c["runner_arch"] = runner_arch.upper() if runner_arch.upper() in {"ARM64", "X64", "X86", "ARM"} else ""
        if browser and c["runner_arch"] and c["runner_arch"] != "X64":
            raise ValueError("Windows noVNC needs an x64 runner. Select RDP only or use an x64 Windows runner.")
    if os_name == "linux":
        c["distro"] = pick(d, "distro", ("ubuntu", "debian", "fedora", "arch", "alpine", "igos-nusantara"), "ubuntu")
        c["desktop"] = pick(d, "desktop", ("kde", "xfce", "mate", "i3", "lxqt"), "kde")
        c["transport"] = pick(d, "transport", ("auto", "tailnet_https", "tailnet_tls_tcp"), "auto")
        if c["desktop"] == "lxqt" and (c["distro"] != "ubuntu" or c["remote_access"] != "rdp"):
            raise ValueError("Ubuntu LXQt is an XRDP-only desktop")
        if (c["distro"] == "arch" or (c["distro"], c["desktop"]) == ("alpine", "kde")) and c["remote_access"] != "novnc":
            raise ValueError("Arch and Alpine KDE require Webtop browser mode")
        if c["distro"] == "igos-nusantara" and (c["desktop"] != "xfce" or c["remote_access"] != "rdp" or c["runner_type"] != "self-hosted"):
            raise ValueError("IGOS ISO lab requires dedicated self-hosted runner, Xfce, and RDP")
    if os_name == "macos":
        c["runner_label"] = pick(d, "runner_label", MACS, MACS[0])
        c["gui_preview"] = pick(d, "gui_preview", ("true", "false"), "true")
        c["trading_choice"] = pick(d, "trading_choice", ("none", "webterminal"), "none")
    return c


def read_config():
    return json.loads((state_dir() / "config.json").read_text(encoding="utf-8"))


def derive(c, role, original):
    os_name = c["platform"]
    min_bytes = 12 if os_name in ("windows", "macos") and role != "web" else 8
    if len(original.encode()) < min_bytes or any(ord(x) < 32 or ord(x) == 127 for x in original):
        raise ValueError(f"Password for {role} needs {min_bytes}+ bytes and no control characters")
    mode = c["password_mode"] if os_name == "macos" else c["vnc_password_mode" if role == "web" else "rdp_password_mode"]
    if mode == "random_each_run":
        if os_name == "macos":
            label = f"wfs-macos:{c['run_id']}:remote"
        elif os_name == "linux":
            label = f"wfs:{c['run_id']}:{role}"
        else:
            label = f"wfs-windows:{c['run_id']}:{role}"
        digest = hmac.new(original.encode(), label.encode(), hashlib.sha256).hexdigest()
        return (digest[:8] if role == "web" else "Wf!" + digest[:21]) if os_name == "windows" else digest[:24]
    if os_name == "windows" and role == "web":
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,}", original):
            raise ValueError("Windows VNC_PASSWORD must use ASCII letters, digits, underscore or hyphen")
        return original[:8]
    if os_name == "windows" and role == "rdp":
        classes = sum(bool(re.search(pattern, original)) for pattern in ("[A-Z]", "[a-z]", "[0-9]", "[^A-Za-z0-9]"))
        if classes < 3 or c["rdp_username"].casefold() in original.casefold():
            raise ValueError("Windows RDP password must use 3 character classes and not contain the login name")
    return original


def show_status(rows, hostname=None):
    esc = lambda x: html.escape(x, quote=False).replace("|", "&#124;")
    parts = ["# WFS Remote Workspace", ""]
    if hostname:
        parts.extend([f"Tailnet hostname requested: **{esc(hostname)}**", ""])
    parts += ["| Component | Status | Detail |", "| --- | --- | --- |"]
    for name, state, detail in rows:
        parts.append(f"| {esc(name)} | **{esc(state)}** | {esc(detail)} |")
    return "\n".join(parts) + "\n\nOnly local protocol readiness is checked. Verify interactive login from a separate authorized tailnet device.\n"


def public_error(err):
    print(f"WFS: {err}" if isinstance(err, ValueError) else f"WFS: {type(err).__name__}; see step diagnostics.", file=sys.stderr)


def windows_log(component, state, detail):
    level = {"ready": "PASS", "installed": "PASS", "failed": "FAIL", "timed out": "WARN",
             "warning": "WARN", "unavailable": "WARN", "unsupported": "SKIP", "skipped": "SKIP"}.get(state, "INFO")
    stamp = datetime.now(timezone.utc).strftime("%H:%M:%SZ")
    line = f"[{stamp}] [{level:4}] {component} | {detail}"
    # Native Windows stdout may still use a legacy code page when redirected.
    print(line.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8"), flush=True)


def main(args=None):
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("init")
    q.add_argument("platform", choices=("windows", "linux", "macos"))
    q = sub.add_parser("get"); q.add_argument("key")
    q = sub.add_parser("password"); q.add_argument("role", choices=("rdp", "web", "remote", "preview"))
    q = sub.add_parser("status"); q.add_argument("name"); q.add_argument("state", choices=sorted(STATE)); q.add_argument("detail")
    q = sub.add_parser("ip"); q.add_argument("value")
    q = sub.add_parser("tcp"); q.add_argument("host"); q.add_argument("port", type=int); q.add_argument("--prefix", default="")
    sub.add_parser("summary")
    sub.add_parser("hold")
    sub.add_parser("path")
    u = p.parse_args(args)
    s = state_dir()
    if u.cmd == "init":
        event = Path(os.environ["GITHUB_EVENT_PATH"])
        try:
            cfg = config(u.platform, json.loads(event.read_text(encoding="utf-8-sig")).get("inputs") or {},
                         os.environ["GITHUB_RUN_ID"], os.environ.get("GITHUB_RUN_ATTEMPT", "1"),
                         os.environ.get("RUNNER_ARCH", ""))
        except ValueError as err:
            if u.platform == "windows":
                message = str(err).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
                print(f"::error title=WFS workspace configuration::{message}", flush=True)
            raise
        s.mkdir(mode=0o700, exist_ok=False)
        cfg["started"] = int(time.time())
        (s / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
        with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as f:
            f.write(f"WFS_STATE={s}\nWFS_HOSTNAME={cfg['hostname']}\n")
        if u.platform == "windows":
            print("::group::WFS / Windows configuration", flush=True)
            windows_log("Runner", "configured", f"{cfg['windows_effective_runner']} / {cfg['runner_arch'] or 'architecture not reported'}")
            windows_log("Session", "configured", f"{cfg['remote_access']} | {cfg['hostname']} | up to {cfg['duration_hours']}h")
            print("::endgroup::", flush=True)
            if cfg["windows_fallback"]:
                print("::notice title=WFS runner compatibility::Windows 11 ARM64 was requested with noVNC. This run uses Windows Server 2025 x64 to keep the selected access mode.", flush=True)
    elif u.cmd == "path":
        print(s)
    elif u.cmd == "get":
        value = read_config()[u.key]
        print(str(value).lower() if isinstance(value, bool) else value)
    elif u.cmd == "password":
        key = {"rdp": "RDP_PASSWORD", "web": "VNC_PASSWORD", "remote": "RDP_PASSWORD", "preview": "RDP_PASSWORD"}[u.role]
        role = "remote" if u.role == "preview" else u.role
        print(derive(read_config(), role, os.environ.get(key, "")))
    elif u.cmd == "status":
        if not s.is_dir():
            return 1
        row = [u.name, u.state, u.detail]
        if any(re.search(r"[\x00-\x1f\x7f]", field) for field in row) or len(u.detail) > 500:
            raise ValueError("Invalid status message")
        if os.environ.get("WFS_WINDOWS_LOG") == "1":
            # GUI and CLI installers run in parallel. Separate atomic records avoid shared append races.
            records = s / "status"
            records.mkdir(exist_ok=True)
            dest = records / (hashlib.sha256(u.name.encode()).hexdigest() + ".json")
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=records, delete=False) as f:
                f.write(json.dumps(row, ensure_ascii=False))
            Path(f.name).replace(dest)
            windows_log(*row)
        else:
            with (s / "status.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    elif u.cmd == "summary":
        if s.is_dir():
            ledger = s / "status.jsonl"
            rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()] if ledger.exists() else []
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
                f.write(show_status(rows, read_config()["hostname"]))
    elif u.cmd == "ip":
        ip = ipaddress.ip_address(u.value.strip())
        if ip not in TAILNET:
            raise ValueError("Not a Tailscale IPv4 address")
        print(ip)
    elif u.cmd == "tcp":
        with socket.create_connection((u.host, u.port), timeout=2) as sock:
            if u.prefix:
                data = bytearray()
                while len(data) < len(u.prefix):
                    block = sock.recv(len(u.prefix) - len(data))
                    if not block:
                        break
                    data += block
                if data != u.prefix.encode():
                    raise ValueError("Protocol banner missing or unexpected")
    elif u.cmd == "hold":
        c = read_config()
        # Leave time for always() cleanup within the 360-minute Actions job.
        end = min(time.time() + int(c["duration_hours"]) * 3600, c["started"] + 345 * 60)
        if c["platform"] == "windows":
            deadline = datetime.fromtimestamp(end, timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
            windows_log("Session", "ready", f"Closes by {deadline} | connection details in Summary | cancel the run to stop early")
        else:
            print("Workspace ready; use the job Summary. Cancel the workflow to stop early.", flush=True)
        while time.time() < end:
            time.sleep(min(45, max(0, end-time.time())))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError) as e:
        public_error(e)
        sys.exit(1)
