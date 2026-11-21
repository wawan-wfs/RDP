"""Resolve verified private Tailscale IPv4 after the GitHub action connects.

Only an address is sent to stdout. Diagnostics go to stderr so the
PowerShell assignment and downstream IPv4 validator remain deterministic.
"""
import ipaddress
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

TAILNET = ipaddress.IPv4Network("100.64.0.0/10")


def private_ip(value):
    try:
        ip = ipaddress.ip_address(value.strip())
        return str(ip) if isinstance(ip, ipaddress.IPv4Address) and ip in TAILNET else None
    except (ValueError, AttributeError):
        return None


def from_cli(output):
    for candidate in output.splitlines():
        address = private_ip(candidate)
        if address:
            return address
    return None


def from_status(output):
    try:
        state = json.loads(output)
    except (TypeError, ValueError):
        return None
    if not isinstance(state, dict) or state.get("BackendState") != "Running":
        return None
    self_node = state.get("Self")
    if not isinstance(self_node, dict):
        return None
    for candidate in self_node.get("TailscaleIPs", []):
        if isinstance(candidate, str):
            address = private_ip(candidate)
            if address:
                return address
    return None


def invoke(binary, *args):
    try:
        completed = subprocess.run((binary, *args), text=True, capture_output=True,
                                   timeout=9, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return completed.stdout if completed.returncode == 0 else None


def query(binary):
    raw = invoke(binary, "ip", "-4")
    if raw:
        address = from_cli(raw)
        if address:
            return address, "tailscale ip -4"
    status = invoke(binary, "status", "--json")
    if status:
        address = from_status(status)
        if address:
            return address, "tailscale status --json"
    return None, None


def resolve(binary, attempts=20, interval=3, sleeper=time.sleep):
    for i in range(attempts):
        address, source = query(binary)
        if address:
            print(f"[WFS/TAILNET] Private IPv4 verified via {source}", file=sys.stderr, flush=True)
            return address
        if i in (0, 4, 9, 14):
            print(f"[WFS/TAILNET] Awaiting private IPv4: attempt {i + 1}/{attempts}",
                  file=sys.stderr, flush=True)
        if i + 1 < attempts:
            sleeper(interval)
    return None


def main():
    binary = shutil.which("tailscale") or shutil.which("tailscale.exe")
    if os.name == "nt" and not binary:
        fallback = Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Tailscale" / "tailscale.exe"
        if fallback.is_file():
            binary = str(fallback)
    if not binary:
        print("::error title=WFS Tailnet::Tailscale CLI not found on this runner", file=sys.stderr)
        return 1
    address = resolve(binary)
    if not address:
        print("::error title=WFS Tailnet::Tailscale setup completed but no verified "
              "100.64.0.0/10 IPv4 was returned during the retry window. "
              "Check Tailscale status and Windows service state in the runner logs.",
              file=sys.stderr)
        return 1
    print(address, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
