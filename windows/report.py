"""Windows Actions job summary with separate connection and installer reports."""
import html
from ipaddress import ip_address
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

from shared.workspace import TAILNET, read_config, state_dir, windows_log

REMOTE = ("Tailnet", "Windows RDP", "Windows noVNC", "Windows HTTPS")
ICONS = {
    "ready": "✅ Ready", "installed": "✅ Installed", "configured": "🔧 Configured",
    "failed": "❌ Failed", "warning": "⚠️ Warning", "timed out": "⏱️ Timed out",
    "pending interactive": "🖱️ Finish in desktop", "unsupported": "➖ Unsupported",
    "skipped": "➖ Skipped", "unavailable": "⚠️ Unavailable",
}
GITHUB_STATES = {"success": "✅ Passed", "failure": "❌ Failed", "skipped": "➖ Skipped",
                 "cancelled": "⏹️ Cancelled"}
STAGES = (
    ("Source checkout", "WFS_CHECKOUT", "Check repository access and runner setup."),
    ("Python toolchain", "WFS_PYTHON", "Check setup-python and runner architecture."),
    ("Configuration", "WFS_PREFLIGHT", "Review the selected runner, access mode, and job annotation."),
    ("Native validation", "WFS_VALIDATION", "Open the validation step for the failing test."),
    ("Tailscale join", "WFS_TAILNET", "Verify the Tailscale auth key and its tag policy."),
    ("Remote readiness", "WFS_REMOTE", "Open the protocol setup step for the RDP or noVNC error."),
)


def md(value):
    return html.escape(str(value), quote=False).translate(str.maketrans({
        "|": "&#124;", "`": "&#96;", "*": "&#42;", "_": "&#95;", "[": "&#91;", "]": "&#93;", "\\": "&#92;",
    }))


def tailnet_ip(value):
    try:
        return ip_address(value) in TAILNET
    except ValueError:
        return False


def browser_link(detail):
    value = detail.partition(";")[0]
    if not re.fullmatch(r"https?://[a-z0-9.:-]+/vnc\.html#resize=scale&autoconnect=1&path=websockify", value):
        return ""
    url = urlsplit(value)
    if url.scheme == "http" and url.netloc.endswith(":6082") and tailnet_ip(url.hostname):
        return value
    if url.scheme == "https" and re.fullmatch(r"[a-z0-9.-]+\.ts\.net", url.netloc):
        return value
    return ""


def steps_table(outcomes, cfg):
    lines = ["| Stage | Result | Next step if failed |", "| --- | --- | --- |"]
    for name, key, hint in STAGES:
        result = outcomes.get(key, "")
        cell = GITHUB_STATES.get(result, "➖ Not run")
        if key == "WFS_TAILNET" and result == "skipped" and outcomes.get("WFS_REMOTE") in {"failure", "success"} and cfg.get("runner_type") == "self-hosted":
            cell = "🔗 Preconfigured tailnet"
        lines.append(f"| {name} | {cell} | {hint if result == 'failure' else '—'} |")
    return lines


def credential(cfg, role):
    secret = "RDP_PASSWORD" if role == "rdp" else "VNC_PASSWORD"
    mode = cfg.get("rdp_password_mode" if role == "rdp" else "vnc_password_mode")
    if mode == "random_each_run":
        return f"per-run password derived from `{secret}`"
    return f"`{secret}`" if role == "rdp" else f"first eight characters of `{secret}`"


def access_summary(cfg, rows, outcomes):
    by_name = {name: (result, detail) for name, result, detail in rows if name in REMOTE}
    has_ready = any(by_name.get(name, ("", ""))[0] == "ready" for name in ("Windows RDP", "Windows noVNC"))
    missed_path = any(by_name.get(name, ("", ""))[0] == "failed" for name in ("Windows RDP", "Windows noVNC"))
    failure = any(outcomes.get(key) == "failure" for _, key, _ in STAGES)
    if failure:
        headline = "❌ Setup failed"
    elif has_ready:
        headline = "⚠️ One access path is ready" if missed_path else "✅ Ready to connect"
    elif outcomes.get("WFS_VALIDATION") == "success":
        headline = "✅ Native validation passed · no remote services started"
    else:
        headline = "➖ No endpoint verified"
    lines = ["# 🖥️ WFS Windows Workspace", "", f"> **{headline}**", ""]
    if cfg:
        lines += [
            f"**Runner** {md(cfg['windows_effective_runner'])} · {md(cfg['runner_arch'] or 'unknown architecture')}  ",
            f"**Access** {md(cfg['remote_access'].upper())} · **Node requested** `{md(cfg['hostname'])}` · **Session cap** {md(cfg['duration_hours'])} h",
            "",
        ]
        if cfg["windows_fallback"]:
            lines += ["> ℹ️ **Runner switched** · Windows 11 ARM64 → Windows Server 2025 x64. noVNC in this workflow requires x64.", ""]
    if has_ready:
        lines += ["## 🔗 Connect", "", "Use a device signed in to the same Tailscale network.", ""]
        rdp_state, rdp = by_name.get("Windows RDP", ("", ""))
        match = re.fullmatch(r"mstsc /v:([\d.]+):3389; user ([A-Za-z][A-Za-z0-9_-]{0,19}); NLA enabled", rdp)
        if rdp_state == "ready" and match and tailnet_ip(match[1]):
            lines += [
                "### Remote Desktop · RDP", "", "```powershell",
                f"mstsc /v:{match[1]}:3389 /f", "```", "",
                f"**Username** `{match[2]}` · **Password** {credential(cfg, 'rdp')}", "",
            ]
        web_state, web = by_name.get("Windows noVNC", ("", ""))
        link = browser_link(web)
        if web_state == "ready" and link:
            lines += [
                "### Browser desktop · noVNC", "",
                f"**[Open private desktop]({link})** · **Password** {credential(cfg, 'web')}", "",
                "noVNC controls the Windows console, which can differ from the RDP session.", "",
            ]
        lines += ["The checks confirm local protocol readiness. Interactive sign-in must be verified from your device.", ""]
    if by_name:
        lines += ["## 📡 Endpoint checks", "", "| Endpoint | Result | Detail |", "| --- | --- | --- |"]
        for name in REMOTE:
            if name in by_name:
                state, detail = by_name[name]
                lines.append(f"| {name} | {ICONS.get(state, md(state))} | {md(detail)} |")
        lines.append("")
    return "\n".join(lines + ["## 🧭 Setup timeline", "", *steps_table(outcomes, cfg), "", ""])


def apps_summary(rows, outcome):
    rows = sorted((row for row in rows if row[0] not in REMOTE), key=lambda row: row[0].casefold())
    done = sum(state in {"installed", "configured"} for _, state, _ in rows)
    pending = sum(state in {"pending interactive", "attempted"} for _, state, _ in rows)
    issues = sum(state in {"warning", "unavailable", "failed", "timed out"} for _, state, _ in rows)
    skipped = sum(state in {"unsupported", "skipped"} for _, state, _ in rows)
    lines = ["## 📦 Applications", "",
             f"> **{done} installed/configured** · **{pending} pending** · **{issues} with issues** · **{skipped} skipped**", ""]
    if outcome != "success":
        lines += [f"**Installer step** {GITHUB_STATES.get(outcome, 'Not completed')}. Review the installer log. A failed app does not invalidate the connection report.", ""]
    if not rows:
        return "\n".join(lines + ["No per-app results were recorded.", "", ""])
    lines += ["| Application | Result | Detail |", "| --- | --- | --- |"]
    for name, state, detail in rows:
        lines.append(f"| {md(name)} | {ICONS.get(state, md(state))} | {md(detail)} |")
    return "\n".join(lines + ["", ""])


def main(section):
    folder = state_dir()
    cfg = read_config() if (folder / "config.json").is_file() else {}
    rows = [json.loads(path.read_text(encoding="utf-8")) for path in (folder / "status").glob("*.json")]
    if section == "access":
        report = access_summary(cfg, rows, os.environ)
        failed = [name for name, key, _ in STAGES if os.environ.get(key) == "failure"]
        windows_log("Connection report", "failed" if failed else "configured",
                    "See job Summary" + (" | failed stage: " + ", ".join(failed) if failed else ""))
    else:
        outcome = os.environ.get("WFS_APP_OUTCOME", "")
        report = apps_summary(rows, outcome)
        windows_log("Application report", "configured", "See job Summary for the per-app results")
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as f:
        f.write(report)


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"access", "apps"}:
        raise SystemExit("usage: python -m windows.report {access|apps}")
    main(sys.argv[1])
