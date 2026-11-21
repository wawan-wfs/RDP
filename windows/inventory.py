"""Build the secret-free Windows app inventory HTML artifact."""
from collections import Counter
from html import escape
import json
import os
from pathlib import Path
import re

from shared.workspace import read_config, state_dir

STATE = {
    "installed": ("Installed", "ok"), "configured": ("Configured", "ok"),
    "ready": ("Ready", "ok"), "pending interactive": ("Finish after RDP login", "pending"),
    "attempted": ("Attempted", "pending"), "warning": ("Warning", "warn"),
    "failed": ("Failed", "bad"), "timed out": ("Timed out", "bad"),
    "unsupported": ("Unsupported", "muted"), "skipped": ("Skipped", "muted"),
    "unavailable": ("Unavailable", "warn"),
}
REMOTE = {"Tailnet", "Windows RDP", "Windows noVNC", "Windows HTTPS"}


def render(rows, cfg, run="local", attempt="1"):
    apps = sorted(((str(n), str(s), str(d)) for n, s, d in rows if n not in REMOTE),
                  key=lambda row: row[0].casefold())
    count = Counter(s for _, s, _ in apps)
    done = sum(count[s] for s in ("installed", "configured"))
    pending = sum(count[s] for s in ("pending interactive", "attempted"))
    issues = sum(count[s] for s in ("failed", "timed out", "warning", "unavailable"))
    skipped = sum(count[s] for s in ("unsupported", "skipped"))
    cards = []
    for name, state, detail in apps:
        label, color = STATE.get(state, ("Not verified", "muted"))
        cards.append(f'<article class="app"><header><h3>{escape(name)}</h3><span class="pill {color}">{escape(label)}</span></header><p>{escape(detail)}</p></article>')
    if not cards:
        cards = ['<article class="app"><h3>No application results yet</h3><p>Check the installer step for diagnostics.</p></article>']
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>WFS · Application Inventory</title>
<style>
:root{{color-scheme:dark;--bg:#09101c;--panel:#121f33;--line:#304761;--text:#edf6ff;--muted:#a9bad2;--accent:#89cbff;--ok:#77eac0;--warn:#ffe09c;--bad:#ffabb1}}
*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(ellipse at 15% -15%,#17385d 0,transparent 55%),var(--bg);color:var(--text);font:15px/1.55 system-ui,sans-serif}}
main{{max-width:1050px;margin:auto;padding:34px 22px 50px}}.hero{{border:1px solid #426489;border-radius:21px;background:linear-gradient(120deg,#193757,#0e1e34);padding:34px}}
.kicker{{font:700 11px ui-monospace,monospace;letter-spacing:.17em;color:var(--accent)}}h1{{font-size:clamp(30px,5vw,54px);line-height:1.03;margin:12px 0}}h3{{font-size:16px;margin:0}}
p{{color:var(--muted);margin:6px 0 0}}.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:18px 0 26px}}.stat,.app{{border:1px solid var(--line);border-radius:13px;background:var(--panel)}}
.stat{{padding:15px}}.stat b{{display:block;font-size:28px}}.stat span{{font-size:12px;color:var(--muted)}}.grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}}.app{{padding:18px}}
.app header{{display:flex;align-items:start;justify-content:space-between;gap:10px;flex-wrap:wrap}}.pill{{font-size:11px;border:1px solid currentColor;border-radius:30px;padding:3px 8px;white-space:nowrap}}
.ok{{color:var(--ok)}}.pending,.warn{{color:var(--warn)}}.bad{{color:var(--bad)}}.muted{{color:var(--muted)}}.foot{{font:12px ui-monospace,monospace;color:var(--muted);margin-top:24px}}
@media(max-width:640px){{main{{padding:16px 12px}}.hero{{padding:24px}}.stats{{grid-template-columns:repeat(2,1fr)}}.grid{{grid-template-columns:1fr}}}}
</style></head><body><main><section class="hero"><div class="kicker">WFS / REMOTE OPERATIONS · WINDOWS</div><h1>Application Inventory</h1>
<p>Installation snapshot for your temporary desktop. A scheduled installer is not the same as a verified installed app.</p></section>
<div class="stats"><div class="stat"><b>{done}</b><span>Installed / configured</span></div><div class="stat"><b>{pending}</b><span>Pending login</span></div>
<div class="stat"><b>{issues}</b><span>With issues</span></div><div class="stat"><b>{skipped}</b><span>Skipped</span></div></div>
<section class="grid" aria-label="Applications">{''.join(cards)}</section>
<div class="foot">Run {escape(run)} · Attempt {escape(attempt)} · Static snapshot, not live status · No passwords or tokens</div></main></body></html>'''


def main():
    s = state_dir()
    cfg = read_config() if (s / "config.json").exists() else {}
    records = s / "status"
    rows = [json.loads(f.read_text(encoding="utf-8")) for f in records.glob("*.json")] if records.exists() else []
    run, attempt = os.environ.get("GITHUB_RUN_ID", ""), os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    if not (re.fullmatch(r"\d+", run) and re.fullmatch(r"\d+", attempt)):
        raise ValueError("Invalid dashboard run identity")
    path = Path(os.environ["RUNNER_TEMP"]) / f"wfs-apps-{run}-{attempt}.html"
    path.write_text(render(rows, cfg, run, attempt), encoding="utf-8")
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as f:
        f.write("inventory=true\n")


if __name__ == "__main__":
    main()
