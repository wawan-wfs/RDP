"""Build an offline, secret-free connection snapshot for the Windows Actions run."""
from html import escape
import re

from windows.report import REMOTE, STAGES, access_state, browser_link, credential, tailnet_ip

STYLE = """
:root{color-scheme:dark;--bg:#080e19;--panel:#111c2e;--line:#283852;--text:#edf4ff;--muted:#aabbd4;--accent:#8ebcff;--ok:#73efcb;--bad:#ff9f91;--warn:#ffd18a}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 85% 0,#152f56 0,transparent 46%),var(--bg);
  color:var(--text);font:15px/1.55 system-ui,sans-serif}main{max-width:1040px;margin:auto;padding:36px 24px 44px}
a{color:var(--accent)}a:focus-visible{outline:2px solid var(--ok);outline-offset:5px}
header{position:relative;overflow:hidden;isolation:isolate;border:1px solid #37557d;border-radius:24px;
  padding:34px 40px;background:linear-gradient(115deg,#142642,#101c31 60%,#142743)}
header:after{content:"";position:absolute;z-index:-1;inset:0 0 0 50%;opacity:.25;
  background:repeating-linear-gradient(90deg,transparent 0 27px,#487cbe 28px 29px),repeating-linear-gradient(0deg,transparent 0 27px,#487cbe 28px 29px);
  mask-image:linear-gradient(90deg,transparent,#000)}
.brand{display:flex;align-items:center;gap:12px;font:650 12px/1.2 ui-monospace,monospace;letter-spacing:.17em;color:#a6caff}
.logo{display:inline-grid;grid-template-columns:repeat(2,7px);gap:3px;background:#203b5c;padding:8px;border:1px solid #47698e;border-radius:8px}
.logo i{width:7px;height:7px;background:var(--accent);border-radius:1px}.logo i:nth-child(2){background:var(--ok)}
h1{font-size:clamp(36px,6vw,64px);letter-spacing:-.057em;line-height:.99;margin:21px 0 12px}
h2{font-size:21px;letter-spacing:-.025em;margin:0 0 14px}h3{font-size:16px;margin:0 0 13px}p{margin:0}.muted{color:var(--muted)}
.meta{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:14px 0 0}
.tile,.panel,.banner{background:var(--panel);border:1px solid var(--line);border-radius:14px}
.tile{padding:12px 15px;overflow-wrap:anywhere}.tile small,.overline{display:block;color:var(--muted);font-size:10px;font-weight:700;letter-spacing:.12em;text-transform:uppercase}.tile b{display:block;margin-top:2px}
.banner{margin:16px 0;display:flex;align-items:center;gap:16px;padding:15px 18px;border-left:4px solid var(--accent)}
.pill{display:inline-block;padding:3px 10px;border:1px solid currentColor;border-radius:99px;font-size:11px;letter-spacing:.035em;font-weight:700;white-space:nowrap}
.ok{color:var(--ok)}.bad{color:var(--bad)}.warn{color:var(--warn)}.neutral{color:var(--muted)}
.banner.ok{border-left-color:var(--ok)}.banner.bad{border-left-color:var(--bad)}.banner.warn{border-left-color:var(--warn)}
.layout{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.14fr);gap:16px}
.panel{padding:20px 21px;min-width:0}.sub{background:#0a1424;border:1px solid var(--line);border-radius:11px;padding:13px;margin-top:10px}
code{font:13px ui-monospace,Consolas,monospace;overflow-wrap:anywhere;color:#c7e4ff}pre{white-space:pre-wrap;background:var(--bg);padding:11px;border-radius:8px;margin:0 0 8px}
.button{display:inline-block;background:#b2d1ff;color:#0b1930;font-weight:720;text-decoration:none;border-radius:8px;padding:7px 13px;margin-bottom:8px}
ol{list-style:none;padding:0;margin:0}li{padding:6px 0;display:flex;align-items:center;gap:10px;border-bottom:1px solid var(--line)}li:last-child{border:0}
.step{white-space:nowrap;color:var(--muted);font:12px ui-monospace,monospace}li strong{flex:1;font-size:13px}.hint{margin:12px 0 0}
footer{display:flex;justify-content:space-between;gap:8px;color:var(--muted);font-size:12px;padding:15px 2px 0}
@media(max-width:650px){main{padding:18px 13px}header{padding:25px 20px}.meta{grid-template-columns:repeat(2,minmax(0,1fr))}.layout{grid-template-columns:1fr}.banner,footer{align-items:flex-start}.banner{gap:9px}}
"""


def render(cfg, rows, outcomes, run, attempt):
    kind, title, hint = access_state(rows, outcomes)
    tone = {"CAUTION": "bad", "TIP": "ok", "WARNING": "warn"}.get(kind, "neutral")
    by_name = {name: (status, detail) for name, status, detail in rows if name in REMOTE}
    tiles = "".join(
        f'<div class="tile"><small>{name}</small><b>{escape(str(value))}</b></div>'
        for name, value in (
            ("Runner", cfg.get("windows_effective_runner", "Not initialized")),
            ("Architecture", cfg.get("runner_arch") or "—"),
            ("Access mode", cfg.get("remote_access", "—").upper()),
            ("Tailnet node requested", cfg.get("hostname", "—")),
        )
    )
    state = {"success": ("ok", "Passed"), "failure": ("bad", "Failed"),
             "skipped": ("neutral", "Skipped"), "cancelled": ("warn", "Cancelled")}
    stages = []
    failure_hint = ""
    for i, (name, key, help_text) in enumerate(STAGES, 1):
        condition = outcomes.get(key)
        mood, label = state.get(condition, ("neutral", "Not run"))
        if key == "WFS_TAILNET" and condition == "skipped" and cfg.get("runner_type") == "self-hosted" and outcomes.get("WFS_REMOTE") in {"success", "failure"}:
            mood, label = "ok", "Preconfigured"
        if not failure_hint and condition == "failure":
            failure_hint = f'<p class="muted hint">{escape(help_text)}</p>'
        stages.append(f'<li><span class="step">{i:02d}</span><strong>{name}</strong><span class="pill {mood}">{label}</span></li>')
    access = []
    rdp_status, rdp = by_name.get("Windows RDP", ("", ""))
    match = re.fullmatch(r"mstsc /v:([\d.]+):3389; user ([A-Za-z][A-Za-z0-9_-]{0,19}); NLA enabled", rdp)
    if rdp_status == "ready" and match and tailnet_ip(match[1]):
        access.append(f'<div class="sub"><h3>Remote Desktop · RDP</h3><pre><code>mstsc /v:{match[1]}:3389 /f</code></pre><p class="muted">Username <code>{match[2]}</code> · {escape(credential(cfg, "rdp").replace(chr(96), ""))}</p></div>')
    web_status, web = by_name.get("Windows noVNC", ("", ""))
    link = browser_link(web)
    if web_status == "ready" and link:
        access.append(f'<div class="sub"><h3>Browser desktop · noVNC</h3><a class="button" href="{escape(link)}">Open private desktop →</a><p class="muted">{escape(credential(cfg, "web").replace(chr(96), ""))}</p></div>')
    for label in ("Windows RDP", "Windows noVNC"):
        if by_name.get(label, ("", ""))[0] == "failed":
            access.append(f'<div class="sub"><h3>{label}</h3><p class="bad">Protocol check failed. See step 06 in GitHub Actions.</p></div>')
    if not access:
        access.append('<div class="sub"><h3>No connection published</h3><p class="muted">This run did not verify an endpoint. Use the setup timeline to locate the failing step.</p></div>')
    note = '<p class="muted hint">ARM64 was requested with noVNC. The runner switched to Windows Server 2025 x64.</p>' if cfg.get("windows_fallback") else ""
    repo = outcomes.get("GITHUB_REPOSITORY", "")
    source_link = (f'<a href="https://github.com/{repo}/actions/runs/{run}">Open Actions run →</a>'
                   if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+", repo)
                   and re.fullmatch(r"[0-9]+", run) else "")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>WFS · Windows Workspace</title><style>{STYLE}</style></head><body><main>
<header><div class="brand"><span class="logo" aria-hidden="true"><i></i><i></i><i></i><i></i></span>WFS / REMOTE OPERATIONS</div>
<h1>Windows Workspace</h1><p class="muted">Connection snapshot &nbsp;·&nbsp; Private Tailscale network</p></header>
<section class="meta" aria-label="Workspace configuration">{tiles}</section>
<div class="banner {tone}"><span class="pill {tone}">{escape(title)}</span><p class="muted">{escape(hint.replace("**", ""))}</p></div>
<div class="layout">
<section class="panel"><span class="overline">01 / Access</span><h2>Connection endpoints</h2>
<p class="muted">Use an authorized device on the same tailnet.</p>{"".join(access)}{note}</section>
<section class="panel"><span class="overline">02 / Diagnostics</span><h2>Setup timeline</h2><ol>{"".join(stages)}</ol>{failure_hint}</section>
</div><footer><span>Run {escape(run)} · Attempt {escape(attempt)} · Snapshot, not live status</span>{source_link}</footer>
</main></body></html>
"""
